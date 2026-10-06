#!/usr/bin/env python3
"""build_corpus.py — 从 CHILDES 中文语料库构建照护者语料

背景：系统原有的照护者语料是硬编码在 language.py 里的 55 条短句。扩容需要
真实照护者语言，而不是实验者编的"教材"——课程表就是提示词，违反项目硬约束。

数据源：CHILDES / TalkBank 的 Mandarin 语料（繁体整包），转简体后抽取
成人（母亲/父亲/主试/祖辈）对儿童说的话。

CHAT 格式要点：
  *MOT:\t拿 過 來 .          ← 主层：说话人 + 话语（汉字按词以空格分隔）
  %mor:\t...                 ← 形态层，丢弃
  %gra:\t...                 ← 句法层，丢弃
  %spa:\t$NIA:RP             ← 语用层，保留用于后续分池

用法：
    ./venv/bin/python tools/build_corpus.py                 # 统计 + 初版语料
    ./venv/bin/python tools/build_corpus.py --min 2 --max 8
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys

from opencc import OpenCC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "corpus_raw", "childes")
OUT_DIR = os.path.join(ROOT, "corpus")

# 成人说话人代号（儿童 CHI 与同胞不计——那是同龄人语言，不是照护者语言）
ADULT_CODES = {"MOT", "FAT", "INV", "GRA", "GRM", "GRF", "AUN", "UNC", "CAR"}

# CHAT 标注清洗规则（顺序敏感）
_TERMINATORS = re.compile(r"[.?!]+\s*$")
_TIMESTAMP = re.compile(r"\s*\d+_\d+\s*$")            # 行尾对齐时间戳 186292_188363
_PLACEHOLDER = re.compile(r"孩名|姓名|人名|地名|机构名|学校名|园名")  # 匿名化占位符
_ZERO_MARK = re.compile(r"\b0[a-z]+")                 # 0word：零标记（未说出）
_UNINTELIGIBLE = re.compile(r"\b(xxx|yyy|www)\b")     # 无法辨认：整句丢弃
_NONVERBAL = re.compile(r"&=?[a-zA-Z:]+")             # &=laugh 之类
_PAUSE = re.compile(r"\((\.|\.\.|\.\.\.)\)")          # (.) (..) (...)
_PAREN_KEEP = re.compile(r"\(([^()]*)\)")             # (么) → 么（保留内容）
_BRACKET = re.compile(r"\[[^\]]*\]")                  # [/] [//] [= x] [* x]
_RETRACE = re.compile(r"\+\S*")                       # +/. +//. +... +" +^
_ANGLE = re.compile(r"[<>{}]")
_QUOTE = re.compile(r"[\"“”]")
_EVENTS = re.compile(r"\b(?:x|y|w)(?:xx|yy|ww)?\b")
_DASH = re.compile(r"(?<=\S)-(?=\s|$)")
_LATIN = re.compile(r"[0-9A-Za-z]")                   # 残留拼音/数字：丢弃
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
                  r"\U00020000-\U0003ffff]")
# 末道归一：只保留汉字（清掉残余的 : ] 等结构符号；不跨字合并，只删除）
_NON_CJK_STRIP = re.compile(r"[^\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
                            r"\U00020000-\U0003ffff]")
_SPACES = re.compile(r"\s+")
# 话轮内分句边界：‡（短停顿）、„（长停顿/引语）、半角与全角逗号分号
_CLAUSE_SPLIT = re.compile(r"[‡„“”]|[,，;；]")


def split_utterance(raw):
    """把一条 CHAT 主层话语按分句边界切成若干片段（原始形式，未清洗）。"""
    t = _TIMESTAMP.sub("", raw.strip())
    return [p for p in (s.strip() for s in _CLAUSE_SPLIT.split(t)) if p]


def clean_piece(t, cc):
    """清洗单个片段；返回自然书写短语，或 None 表示作废。"""
    if not t or _UNINTELIGIBLE.search(t) or _PLACEHOLDER.search(t):
        return None
    t = _ZERO_MARK.sub("", t)
    t = _NONVERBAL.sub("", t)
    t = t.replace("&", "")              # CHAT 的 & 前缀（&=笑 已去除，此处清 &嗯/&哎）
    t = _PAUSE.sub("", t)
    t = _PAREN_KEEP.sub(r"\1", t)       # (么) → 么：保留内容，去掉括号
    t = _BRACKET.sub("", t)
    t = _RETRACE.sub("", t)
    t = _ANGLE.sub("", t)
    t = _QUOTE.sub("", t)
    t = _EVENTS.sub("", t)
    t = _DASH.sub("", t)
    t = _TERMINATORS.sub("", t)
    t = _SPACES.sub(" ", t).strip()
    if not t:
        return None
    t = cc.convert(t)                   # 繁体 → 简体（在合词前做，边界一致）
    t = t.replace(" ", "")              # CHAT 已分词，合并为自然书写形式
    if not t or _LATIN.search(t):       # 残留拉丁/数字 → 丢弃
        return None
    t = _NON_CJK_STRIP.sub("", t)       # 末道归一：只保留汉字
    if not t or not _CJK.search(t):     # 归一后为空（纯符号）→ 丢弃
        return None
    return t


def iter_cha(src_dir):
    for base, _dirs, files in os.walk(src_dir):
        for fn in files:
            if fn.endswith(".cha"):
                yield os.path.join(base, fn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=2, help="最短字数（合词后）")
    ap.add_argument("--max", type=int, default=8, help="最长字数（合词后）")
    ap.add_argument("--top", type=int, default=20, help="样例打印条数")
    ap.add_argument("--min-session", type=int, default=5,
                    help="会话至少含多少个不同短语才保留（话题连续需足够素材）")
    args = ap.parse_args()

    if not os.path.isdir(SRC_DIR):
        print("找不到语料源目录：%s（先解压 CHILDES 包）" % SRC_DIR)
        return 1
    cc = OpenCC("t2s")

    freq = collections.Counter()
    speaker_count = collections.Counter()
    spa_count = collections.Counter()
    sessions = []                 # 每份 .cha = 一次会话（P7 的话题单元）
    raw_lines = 0
    dropped = collections.Counter()
    n_files = 0

    for path in iter_cha(SRC_DIR):
        n_files += 1
        cur_spa = None
        session = collections.Counter()
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("@"):
                    continue
                if line.startswith("%spa:"):
                    cur_spa = line[len("%spa:"):].strip()
                    continue
                if not line.startswith("*"):
                    continue
                raw_lines += 1
                head, _, body = line[1:].partition(":")
                code = head.strip().split("-")[0].upper()
                if code not in ADULT_CODES:
                    dropped["非成人说话人"] += 1
                    cur_spa = None
                    continue
                speaker_count[code] += 1
                for piece in split_utterance(body):
                    txt = clean_piece(piece, cc)
                    if not txt:
                        dropped["清洗后作废"] += 1
                        continue
                    n = len(txt)
                    if n < args.min:
                        dropped["过短"] += 1
                    elif n > args.max:
                        dropped["过长"] += 1
                    else:
                        freq[txt] += 1
                        session[txt] += 1
                        if cur_spa:
                            spa_count[cur_spa.split(":")[0]] += 1
                cur_spa = None
        if len(session) >= args.min_session:
            sessions.append(session)

    os.makedirs(OUT_DIR, exist_ok=True)
    lengths = collections.Counter(len(t) for t in freq.elements())
    total_tokens = sum(freq.values())

    stats = {
        "source": "CHILDES/TalkBank Mandarin (Traditional bulk set)",
        "source_zip_sha256": _sha256(os.path.join(ROOT, "corpus_raw",
                                                  "childes_mandarin_zh_traditional.zip")),
        "n_files": n_files,
        "n_utterance_lines": raw_lines,
        "adult_utterances_kept": total_tokens,
        "distinct_phrases": len(freq),
        "length_filter": [args.min, args.max],
        "dropped": dict(dropped),
        "speaker_counts": dict(speaker_count.most_common()),
        "top_spa": dict(spa_count.most_common(10)),
        "length_distribution": dict(sorted(lengths.items())),
    }
    corpus = [{"text": t, "count": c} for t, c in freq.most_common()]
    with open(os.path.join(OUT_DIR, "caregiver_corpus.json"), "w") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=1)

    # 会话索引（P7 话题连续用）：[[ [phrase, count], ... ], ...]
    # 单元是"会话"而非相邻句：可行性探测显示相邻转移过稀（核心 5000 条中仅
    # 1000 条有重复后继），一阶马尔可夫链学不到结构；会话是语料自带的时间分组。
    sess_out = [[[t, c] for t, c in s.items()] for s in sessions]
    with open(os.path.join(OUT_DIR, "caregiver_sessions.json"), "w") as f:
        json.dump({"min_session": args.min_session, "sessions": sess_out},
                  f, ensure_ascii=False)
    sess_utt = sum(sum(s.values()) for s in sessions)
    sizes = sorted(len(s) for s in sessions)
    stats["n_sessions"] = len(sessions)
    stats["session_min_phrases"] = args.min_session
    stats["session_utterance_coverage"] = round(sess_utt / max(1, total_tokens), 4)
    stats["session_size_median"] = sizes[len(sizes) // 2] if sizes else 0
    with open(os.path.join(OUT_DIR, "stats.json"), "w") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print("会话索引：%d 个会话（每个 ≥%d 个不同短语），覆盖 %.1f%% 的话语，中位规模 %d 条"
          % (len(sessions), args.min_session,
             100 * sess_utt / max(1, total_tokens), stats["session_size_median"]))

    print("扫描 .cha 文件 %d 个，主层话语 %d 条" % (n_files, raw_lines))
    print("成年照护者话语 %d 条 → 去重后 %d 个短语（长度 %d–%d 字）"
          % (total_tokens, len(freq), args.min, args.max))
    print("丢弃统计:", dict(dropped))
    print("说话人:", dict(speaker_count.most_common(6)))
    print("长度分布:", dict(sorted(lengths.items())))
    print()
    print("最高频 %d 条：" % args.top)
    for t, c in freq.most_common(args.top):
        print("  %5d  %s" % (c, t))

    # 随机抽样（中段，避免只看高频）；顺带体检异常字符
    import random
    mid = [t for t in freq if len(t) >= 4]
    random.seed(7)
    print()
    print("随机抽样 24 条：")
    for t in random.sample(mid, min(24, len(mid))):
        print("  %s" % t)
    bad = [t for t in freq if not all("\u4e00" <= ch <= "\u9fff" for ch in t)]
    print()
    print("含非汉字字符的短语: %d 条（示例 %s）" % (len(bad), bad[:8]))
    print()
    print("输出 → corpus/stats.json, corpus/caregiver_corpus.json")
    return 0


def _sha256(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
