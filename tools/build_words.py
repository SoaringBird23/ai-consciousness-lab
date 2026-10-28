"""tools/build_words.py — P18 词表构建（无监督「新词发现」，无词典、无 LLM）

从 CHILDES 短语语料中学习一个「词」表，供 P18 词级组合使用。
方法（经典无监督中文分词，Jin & Tanaka-Ishii 2006 一脉）：
  候选 n-gram（2≤len≤4）须同时满足三条：
    ① 频率  freq(w) ≥ MIN_FREQ          —— 常见
    ② 内聚  cohesion(w) ≥ MIN_PMI       —— 内部结合紧（min over splits 的 PMI）
    ③ 自由度 freedom(w) ≥ MIN_ENTROPY   —— 左右邻字足够多样（能独立成词）
  再按「最长优先 + 分数降序」归并成词表，并用最长匹配切分全部短语。

输出：
  corpus/lexicon.json        —— {"words": [...], "params": {...}, "stats": {...}}
  corpus/caregiver_words.json—— [[[word, ...], phrase_count], ...]（切分后的短语，供核对）

注意：这是环境侧（照护者语言）的「词库」，与语料一样属世界属性；系统运行时只
组合**它自己听过**的词（在线词二元表），零幻觉在词法级仍成立。
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MIN_FREQ = 15
MIN_PMI = 4.5
MIN_ENTROPY = 1.5
MAXLEN = 4


def load_corpus(path):
    with open(path, encoding="utf-8") as f:
        return [(str(r["text"]).strip(), int(r.get("count", 1)))
                for r in json.load(f) if str(r.get("text", "")).strip()]


def count_substrings(phrases):
    """加权统计所有 1..MAXLEN 子串频率（按短语 count 加权）。含单字，供 PMI 用。"""
    freq = Counter()
    for text, c in phrases:
        L = len(text)
        for i in range(L):
            freq[text[i]] += c                       # 单字（PMI 的分母需要）
            for j in range(i + 2, min(i + MAXLEN, L) + 1):
                freq[text[i:j]] += c
    return freq


def count_neighbors(phrases, freq):
    """对频率达标的候选，统计左右邻字（加权），用于分支熵。"""
    left = defaultdict(Counter)
    right = defaultdict(Counter)
    for text, c in phrases:
        L = len(text)
        for i in range(L):
            for j in range(i + 2, min(i + MAXLEN, L) + 1):
                w = text[i:j]
                if freq.get(w, 0) < MIN_FREQ:
                    continue
                if i - 1 >= 0:
                    left[w][text[i - 1]] += c
                if j < L:
                    right[w][text[j]] += c
    return left, right


def entropy(counter):
    tot = sum(counter.values())
    if tot <= 0:
        return 0.0
    h = 0.0
    for v in counter.values():
        p = v / tot
        h -= p * math.log2(p)
    return h


def min_pmi(w, freq, total):
    """min over splits 的 PMI（bits）：log2[ P(w) / (P(a)P(b)) ]。"""
    best = float("inf")
    for k in range(1, len(w)):
        a, b = w[:k], w[k:]
        fa, fb, fw = freq.get(a, 0), freq.get(b, 0), freq.get(w, 0)
        if fa <= 0 or fb <= 0 or fw <= 0:
            return -1.0
        pa, pb, pw = fa / total, fb / total, fw / total
        best = min(best, math.log2(pw / (pa * pb)))
    return best if best != float("inf") else -1.0


def discover(phrases, verbose=True):
    freq = count_substrings(phrases)
    total = sum(freq[c] for c in freq if len(c) == 1)  # 单字总频次
    if total <= 0:
        total = sum(freq.values())
    left, right = count_neighbors(phrases, freq)
    cands = []
    for w, f in freq.items():
        if len(w) < 2 or f < MIN_FREQ:
            continue
        coh = min_pmi(w, freq, total)
        if coh < MIN_PMI:
            continue
        fr = min(entropy(left.get(w, Counter())), entropy(right.get(w, Counter())))
        if fr < MIN_ENTROPY:
            continue
        # 分数：频率×(内聚+自由度)，偏向高内聚/高自由
        score = math.log2(f) * (coh + fr)
        cands.append((w, f, coh, fr, score))
    if verbose:
        print(f"  候选（通过三阈值）: {len(cands)}")
        cands_sorted = sorted(cands, key=lambda x: -x[4])
        print("  分数 top-30:")
        for w, f, coh, fr, sc in cands_sorted[:30]:
            print(f"    {w!r:8s} freq={f:6d} pmi={coh:5.2f} ent={fr:4.2f} score={sc:6.2f}")
    # 归并：长词优先排序（词表冗余无害，不做覆盖剪枝——避免误删合法短词）
    cands.sort(key=lambda x: (-len(x[0]), -x[4]))
    words = [w for w, f, coh, fr, sc in cands]
    return words, freq, {"n_candidates": len(cands), "total_chars": total}


def segment(text, lexicon, maxlen=MAXLEN):
    """最长匹配切词，未命中的单字作 1-gram 保留。"""
    out, i, L = [], 0, len(text)
    while i < L:
        hit = None
        for ln in range(min(maxlen, L - i), 1, -1):
            if text[i:i + ln] in lexicon:
                hit = text[i:i + ln]
                break
        if hit:
            out.append(hit)
            i += len(hit)
        else:
            out.append(text[i])
            i += 1
    return out


def main():
    cpath = os.path.join(ROOT, "corpus", "caregiver_corpus.json")
    phrases = load_corpus(cpath)
    print(f"载入短语 {len(phrases)} 型，总 token≈{sum(len(t) * c for t, c in phrases)}")
    words, freq, stats = discover(phrases)
    lex = set(words)
    seg = [[segment(t, lex), c] for t, c in phrases]
    # 词长分布 / 覆盖
    seg_tokens = sum(len(s) * c for s, c in seg)
    multi = [s for s, c in seg for _ in range(1) if len(s) > 1]
    print(f"词表大小: {len(lex)}；切分后平均每句 {seg_tokens / sum(c for _, c in seg):.2f} 词")
    out = {
        "words": sorted(lex),
        "params": {"MIN_FREQ": MIN_FREQ, "MIN_PMI": MIN_PMI,
                   "MIN_ENTROPY": MIN_ENTROPY, "MAXLEN": MAXLEN},
        "stats": {**stats, "n_words": len(lex)},
    }
    with open(os.path.join(ROOT, "corpus", "lexicon.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    with open(os.path.join(ROOT, "corpus", "caregiver_words.json"), "w", encoding="utf-8") as f:
        json.dump(seg, f, ensure_ascii=False)
    print("落盘: corpus/lexicon.json, corpus/caregiver_words.json")
    print("样例切分：", ["/".join(s) for s, _ in seg[:8]])


if __name__ == "__main__":
    main()
