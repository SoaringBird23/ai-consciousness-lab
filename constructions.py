"""constructions.py — P20 构造语法：理解句式，重组词句

目标（用户 2026-10-18 的要求）：
  不是“检索一句听过的话”，也不是“词二元接龙”，而是
  ① 听懂一句没听过的话：把它切分成**听过的句式（construction）+ 槽位填充**；
  ② 回答/接话时：拿一个听过的句式，把槽位换成**当前语境下合适的、实听过的词**，
     得到整体没听过、但每个词和每个句式都听过的句子。

原则（沿用 R3/C1 的零幻觉约束）：
  - 词法级零幻觉：输出里每个词都必须是系统实听过的（word_count>0）；
  - 句法级重组：句式必须是实听过的（frame 在 frames 里），但填充词可以换；
  - 不调用任何 LLM，不生成任何没听过的词。
  推论：这套东西能“理解结构、重组表达”，但它的世界只有标量场与八维身体状态，
  没有对象/指称世界；所以它能答“这是什么形状”的**句式**，不能保证答对**事实**。
  这一点写进输出，不假装。

机制：
  - 词表：环境侧无监督新词发现（corpus/lexicon.json），这里只做最长匹配切词；
  - 句式：每听到一句，把其中每个词依次挖空，记 (带空句式 -> 填充词分布)；
  - 理解：对输入做跨度解析（DP），用听过的句式覆盖尽可能长的片段；
  - 问答：疑问句 → 用“问句本身”当答句模板，挖掉疑问词，填一个语境合适的实词；
  - 陈述：选一个与对方话题/当前状态相容的句式，填槽后说出；
  - 语义：词向量=共现分布（窗口 2）+ 听到时的身体状态均值 + 世界场均值；
    填槽打分 = 槽位类别概率 + 与上下文的 PMI + 话题相关 + 状态相容 + 世界相容。
"""
import json
import math
import os
import random
import re
from collections import Counter, defaultdict

_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LEXICON = os.path.join(_ROOT, "corpus", "lexicon.json")

# 封闭类功能词：只用于识别疑问/语气与句式签名，不作为内容词。
# 这是一个很小的“先天功能词表”（人类婴儿也先掌握这类词），不是语法规则库。
FUNCTION_WORDS = set("""
的 了 吗 嘛 么 呢 吧 啊 呀 哦 喔 啦 着 过 地 得 之 其 所 而 与 及 或
我 你 他 她 它 我们 你们 他们 咱们 自己 大家
这 那 这个 那个 这些 那些 这里 那里 这儿 那儿 这样 那样 这么 那么
是 不 没 没有 别 不要 就 都 也 还 又 很 太 最 更 再 才 只 才
和 跟 给 把 被 让 对 从 到 在 有 会 能 可以 要 想 应该
什么 谁 哪 哪里 哪儿 为什么 怎么 怎么样 多少 几 多久 多大
好不好 是不是 对不对 有没有 会不会 行不行 可不可以 要不要 能不能
一 二 三 四 五 六 七 八 九 十 个 只 件 张 本 支 条 棵 朵 颗 块 点
其他 别的 一样 各种 所有 每个 有些 哪些 某种 这种 那种 哪种
""".split())
WH_WORDS = ("什么", "谁", "哪里", "哪儿", "哪", "为什么", "怎么", "怎么样",
            "多少", "几", "多久", "多大")
YESNO_WORDS = ("吗", "嘛", "么", "好不好", "是不是", "对不对", "有没有",
               "会不会", "行不行", "可不可以", "要不要", "能不能")
GREETINGS = ("你好", "您好", "早安", "早上好", "晚安", "再见", "拜拜", "嗨", "哈喽")
LOCATION_HINTS = ("这里", "那里", "这儿", "那儿", "上面", "下面", "里面", "外面",
                  "旁边", "床上", "桌上", "地上", "家里", "公园", "学校")
SPLIT_CUES = tuple(sorted(set(WH_WORDS) | set(YESNO_WORDS), key=len, reverse=True))


def _now():  # 仅给日志/模型元数据用，不参与语义
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Tokenizer:
    """最长匹配切词；疑问/语气词若被包在更长的词里，先切出来。

    例：'苹果在哪里' → ['苹果', '在', '哪里']；'什么形状' → ['什么', '形状']。
    这样问句模板才能对齐到 '在 _' / '这 是 _' 这类句式。
    """

    def __init__(self, lexicon_path=DEFAULT_LEXICON):
        self.words, self.maxlen = set(), 4
        if lexicon_path and os.path.exists(lexicon_path):
            with open(lexicon_path, encoding="utf-8") as f:
                d = json.load(f)
            self.words = set(d.get("words", []))
            self.maxlen = int(d.get("params", {}).get("MAXLEN", 4))
        # 单字也要能切（语料里未登录字当作一个词）
        self._cues = SPLIT_CUES

    def _split_cue(self, tok):
        if tok in self._cues or len(tok) <= 1:
            return [tok]
        for cue in self._cues:
            if cue in tok:
                i = tok.index(cue)
                left, right = tok[:i], tok[i + len(cue):]
                out = []
                if left:
                    out.extend(self._split_cue(left))
                out.append(cue)
                if right:
                    out.extend(self._split_cue(right))
                return out
        return [tok]

    def segment(self, text):
        text = (text or "").strip()
        raw, i, L = [], 0, len(text)
        while i < L:
            hit = None
            for ln in range(min(self.maxlen, L - i), 1, -1):
                if text[i:i + ln] in self.words:
                    hit = text[i:i + ln]
                    break
            if hit:
                raw.append(hit)
                i += len(hit)
            else:
                raw.append(text[i])
                i += 1
        out = []
        for t in raw:
            out.extend(self._split_cue(t))
        out = [t for t in out if t and not t.isspace()]
        # 合并被切开的疑问词：['多','大']→['多大']，['为','什么']→['为什么']
        merged, i = [], 0
        cues = set(WH_WORDS) | set(YESNO_WORDS)
        while i < len(out):
            hit = None
            for ln in (3, 2):
                if i + ln <= len(out):
                    j = "".join(out[i:i + ln])
                    if j in cues:
                        hit = (j, ln)
                        break
            if hit:
                merged.append(hit[0])
                i += hit[1]
            else:
                merged.append(out[i])
                i += 1
        return merged


class ConstructionGrammar:
    MIN_FRAME_N = 2
    MIN_FRAME_FILLERS = 2
    MAX_SPAN = 7

    def __init__(self, lexicon_path=DEFAULT_LEXICON):
        self.tok = Tokenizer(lexicon_path)
        # frame(tuple with one '_') -> {"n": float, "fillers": Counter}
        self.frames = {}
        self.frame_state = {}       # frame -> [sum8(numpy-free list), n]
        self.frame_world = {}       # frame -> [sum, n]
        self.word_count = Counter()
        self.word_state = {}        # w -> [sum8, n]
        self.word_world = {}        # w -> [sum, n]
        self.cooc = defaultdict(Counter)   # w -> Counter(context w)（对称）
        self.seq = defaultdict(Counter)    # w -> Counter(后继 w)（有向，词序用）
        self.sig_trans = defaultdict(Counter)  # 句式签名 -> 后继句式签名
        self.seen = set()           # 实听过的整句（join 后）
        self.n_utt = 0
        self.meta = {"built_at": _now(), "n_utt": 0, "n_frames": 0}
        self._index = None          # literal(tuple) -> set(hole positions)
        self._gen_frames = None
        self._frame_prior = None
        self._frame_static = {}
        self._literal_frames = defaultdict(list)
        self._frames_sorted = []

    # ---------------- 学习 ----------------
    def signature(self, tokens):
        """句式签名：功能词保留，内容词统一为 '_'。用于学习话轮/话语相继。"""
        return tuple(w if w in FUNCTION_WORDS else "_" for w in tokens)

    @staticmethod
    def _swap_person(tokens):
        """你↔我 全句互换：问“你…”答“我…”，问“我…”答“你…”。"""
        out = []
        for w in tokens:
            if w == "你":
                out.append("我")
            elif w == "我":
                out.append("你")
            else:
                out.append(w)
        return out

    @staticmethod
    def _normalize_yesno_token(w):
        """A不A → A：饿不饿→饿，好不好→好，是不是→是。"""
        if len(w) == 3 and w[1] == "不" and w[0] == w[2]:
            return w[0]
        return w

    def _add_state(self, table, key, vec, weight):
        row = table.get(key)
        if row is None:
            row = [[0.0] * len(vec), 0.0]
            table[key] = row
        for i, v in enumerate(vec):
            row[0][i] += float(v) * weight
        row[1] += weight

    def learn(self, text, state=None, world=None, prev_sig=None, weight=1.0,
              learn_transition=True, add_seen=True):
        tokens = self.tok.segment(text)
        if not tokens:
            return None
        sig = self.signature(tokens)
        self.n_utt += weight
        if add_seen:
            self.seen.add("".join(tokens))
        # 词频、状态、世界
        for w in tokens:
            self.word_count[w] += weight
            if state is not None:
                self._add_state(self.word_state, w, state, weight)
            if world is not None:
                row = self.word_world.get(w)
                if row is None:
                    row = [0.0, 0.0]
                    self.word_world[w] = row
                row[0] += float(world) * weight
                row[1] += weight
        # 共现（窗口 2，按距离加权）+ 有向相邻（词序/类别中心词用）
        for i, a in enumerate(tokens):
            for j in range(i + 1, min(len(tokens), i + 3)):
                b = tokens[j]
                if a == b:
                    continue
                self.cooc[a][b] += weight / (j - i)
                self.cooc[b][a] += weight / (j - i)
        for a, b in zip(tokens, tokens[1:]):
            if a != b:
                self.seq[a][b] += weight
        # 句式（每个位置挖一次空）
        if len(tokens) >= 2:
            for i in range(len(tokens)):
                frame = tuple(tokens[:i]) + ("_",) + tuple(tokens[i + 1:])
                st = self.frames.get(frame)
                if st is None:
                    st = {"n": 0.0, "fillers": Counter()}
                    self.frames[frame] = st
                st["n"] += weight
                st["fillers"][tokens[i]] += weight
                if state is not None:
                    self._add_state(self.frame_state, frame, state, weight)
                if world is not None:
                    row = self.frame_world.get(frame)
                    if row is None:
                        row = [0.0, 0.0]
                        self.frame_world[frame] = row
                    row[0] += float(world) * weight
                    row[1] += weight
        # 话语相继：上一句签名 -> 本句签名（来自同一会话的相邻话语）
        if learn_transition and prev_sig is not None:
            self.sig_trans[prev_sig][sig] += weight
        return sig

    def observe_state(self, text, state=None, world=None, weight=1.0):
        """只更新「词/句式 ↔ 身体状态/世界」的绑定，不重复计语言结构。

        用于：结构统计来自完整语料，状态绑定来自系统真实听到的轨迹
        （linguistic_memory.json）。两者相加时不会把词频翻倍。
        """
        tokens = self.tok.segment(text)
        if not tokens:
            return
        for w in tokens:
            if state is not None:
                self._add_state(self.word_state, w, state, weight)
            if world is not None:
                row = self.word_world.get(w)
                if row is None:
                    row = [0.0, 0.0]
                    self.word_world[w] = row
                row[0] += float(world) * weight
                row[1] += weight
        if len(tokens) >= 2:
            for i in range(len(tokens)):
                frame = tuple(tokens[:i]) + ("_",) + tuple(tokens[i + 1:])
                if state is not None and frame in self.frames:
                    self._add_state(self.frame_state, frame, state, weight)
                if world is not None and frame in self.frames:
                    row = self.frame_world.get(frame)
                    if row is None:
                        row = [0.0, 0.0]
                        self.frame_world[frame] = row
                    row[0] += float(world) * weight
                    row[1] += weight

    def add_transition(self, prev_sig, sig, weight=1.0):
        if prev_sig is not None and sig is not None:
            self.sig_trans[prev_sig][sig] += weight

    def finalize(self, min_n=None, min_fillers=None, min_literal=1):
        """剪枝 + 建索引。只有“至少一个实词位置 + 至少两种填充”的句式可用于解析。"""
        min_n = self.MIN_FRAME_N if min_n is None else min_n
        min_fillers = self.MIN_FRAME_FILLERS if min_fillers is None else min_fillers
        keep = {}
        for fr, st in self.frames.items():
            n_lit = sum(1 for w in fr if w != "_")
            if st["n"] >= min_n and len(st["fillers"]) >= min_fillers and n_lit >= min_literal:
                keep[fr] = st
        self.frames = keep
        self._index = defaultdict(set)
        for fr in self.frames:
            literal = tuple(w for w in fr if w != "_")
            # 单空句式：literal + hole 位置即可唯一确定 frame
            pos = fr.index("_")
            self._index[literal].add(pos)
        self._gen_frames = [fr for fr in self.frames
                            if 2 <= len(fr) <= 9 and "_" in fr
                            and sum(1 for w in fr if w != "_") >= 1]
        self._frame_prior = {}
        self._frame_static = {}
        self._literal_frames = defaultdict(list)
        self.word_frames = defaultdict(Counter)
        self.char_in_words = Counter()
        for w, c in self.word_count.items():
            if len(w) == 1:
                continue
            for ch in set(w):
                self.char_in_words[ch] += c
        for fr, st in self.frames.items():
            self._frame_prior[fr] = math.log1p(st["n"]) * math.log1p(len(st["fillers"]))
            self._frame_static[fr] = (0.55 * math.log1p(st["n"])
                                      + 0.45 * math.log1p(len(st["fillers"]))
                                      - 0.12 * abs(len(fr) - 4))
            for w in fr:
                if w != "_":
                    self._literal_frames[w].append(fr)
            for w, c in st["fillers"].items():
                self.word_frames[w][fr] += c
        self._frames_sorted = sorted(self.frames,
                                     key=lambda f: -self._frame_static.get(f, 0.0))
        self.meta.update({"n_utt": self.n_utt, "n_frames": len(self.frames),
                          "n_words": len(self.word_count)})

    # ---------------- 理解：跨度解析 ----------------
    def _match_span(self, span):
        """返回该跨度上所有可匹配的 (frame, score)。"""
        out = []
        n = len(span)
        if n < 2:
            return out
        for pos in range(n):
            literal = span[:pos] + span[pos + 1:]
            if literal in self._index:
                fr = span[:pos] + ("_",) + span[pos + 1:]
                if fr in self.frames:
                    st = self.frames[fr]
                    specificity = 1.0 + 0.55 * (n - 2)
                    score = (math.log1p(st["n"]) * math.log1p(len(st["fillers"]))
                             * specificity)
                    out.append((fr, score))
        return out

    def parse(self, tokens):
        """区间 DP：先最大化结构覆盖（听懂多少），再在同覆盖率下取更可靠的句式。"""
        m = len(tokens)
        if m == 0:
            return []
        cov = [0] * (m + 1)
        sc = [0.0] * (m + 1)
        back = [None] * (m + 1)
        for i in range(m):
            # 未解析单字/词：覆盖 0，低分；仍保留为话题
            if cov[i] > cov[i + 1] or (cov[i] == cov[i + 1] and sc[i] + 0.08 > sc[i + 1]):
                cov[i + 1] = cov[i]
                sc[i + 1] = sc[i] + 0.08
                back[i + 1] = (i, None)
            for j in range(i + 2, min(m, i + self.MAX_SPAN) + 1):
                span = tuple(tokens[i:j])
                for fr, fsc in self._match_span(span):
                    c = cov[i] + (j - i)
                    s2 = sc[i] + fsc
                    if c > cov[j] or (c == cov[j] and s2 > sc[j]):
                        cov[j] = c
                        sc[j] = s2
                        back[j] = (i, fr)
        inst = []
        j = m
        while j > 0:
            i, fr = back[j]
            if fr is not None:
                span = tuple(tokens[i:j])
                hole = fr.index("_")
                inst.append({"frame": fr, "span": (i, j), "filler": span[hole],
                             "text": "".join(span)})
            j = i
        inst.reverse()
        return inst

    def understand(self, text, state=None, world=None, recent_topics=None):
        tokens = self.tok.segment(text)
        inst = self.parse(tokens)
        covered = set()
        for it in inst:
            covered.update(range(*it["span"]))
        conf = len(covered) / len(tokens) if tokens else 0.0
        # 疑问/语气识别（封闭类线索）
        wh_i = next((i for i, w in enumerate(tokens) if w in WH_WORDS), None)
        yesno = (any(w in YESNO_WORDS for w in tokens) or any(
            len(w) == 3 and w[1] == "不" and w[0] == w[2] for w in tokens)
            or any(len(w) >= 2 and w[0] == w[-1] and "不" in w for w in tokens)
            or bool(re.search(r"(.)不\1", text)))
        if any(w in GREETINGS for w in tokens) or tokens[:2] == ["你", "好"]:
            act = "greeting"
        elif wh_i is not None:
            act = "wh_question"
        elif yesno:
            act = "yesno_question"
        elif (tokens and tokens[-1] in ("吧", "啊", "呀")
              and (tokens[0] in ("你", "我们", "咱们")
                   or tokens[0].startswith("我们") or tokens[0].startswith("咱们"))):
            act = "imperative"
        else:
            act = "statement"
        content = [w for w in tokens if w not in FUNCTION_WORDS]
        # 去重保序
        topics = list(dict.fromkeys(content + list(recent_topics or [])))
        # 话题的状态/世界均值
        topic_state = [0.0] * 8
        tw = 0.0
        for w in topics:
            row = self.word_state.get(w)
            if row and row[1] > 0:
                for k in range(8):
                    topic_state[k] += row[0][k] / row[1] * 1.0
                tw += 1.0
        if tw > 0:
            topic_state = [v / tw for v in topic_state]
        else:
            topic_state = list(state) if state is not None else None
        topic_world = None
        vals = []
        for w in topics:
            row = self.word_world.get(w)
            if row and row[1] > 0:
                vals.append(row[0] / row[1])
        if vals:
            topic_world = sum(vals) / len(vals)
        return {"text": text, "tokens": tokens, "constructions": inst,
                "coverage": round(conf, 4), "speech_act": act,
                "wh_index": wh_i, "topics": content, "topic_state": topic_state,
                "topic_world": topic_world, "signature": self.signature(tokens)}

    # ---------------- 语义打分 ----------------
    def _vec_cos(self, ca, cb):
        if not ca or not cb:
            return 0.0
        keys = set(ca) & set(cb)
        if not keys:
            return 0.0
        num = sum(ca[k] * cb[k] for k in keys)
        da = math.sqrt(sum(v * v for v in ca.values()))
        db = math.sqrt(sum(v * v for v in cb.values()))
        return num / (da * db) if da and db else 0.0

    def _pmi(self, a, b):
        if a == b:
            return 3.0
        ca = self.word_count.get(a, 0.0)
        cb = self.word_count.get(b, 0.0)
        cab = self.cooc.get(a, {}).get(b, 0.0)
        if ca <= 0 or cb <= 0 or cab <= 0 or self.n_utt <= 0:
            return -0.5
        return math.log((cab * self.n_utt + 1.0) / (ca * cb + 1.0))

    def _state_fit(self, w, state):
        if state is None:
            return 0.0
        row = self.word_state.get(w)
        if not row or row[1] <= 0:
            return 0.0
        mean = [v / row[1] for v in row[0]]
        d = sum(abs(mean[i] - float(state[i])) for i in range(min(8, len(state)))) / 8.0
        return 1.0 - d

    def _world_fit(self, w, world):
        if world is None:
            return 0.0
        row = self.word_world.get(w)
        if not row or row[1] <= 0:
            return 0.0
        return 1.0 - min(1.0, abs(row[0] / row[1] - float(world)))

    def _topic_fit(self, w, topics):
        if not topics:
            return 0.0
        s = 0.0
        for t in topics[:6]:
            if w == t:
                s += 2.0
            else:
                s += max(-0.5, min(2.0, self._pmi(w, t)))
        return s / min(6, len(topics))

    def _role_sim(self, w, anchor):
        """两个词在「句式槽位」上的分布相似度（分布语义的句法侧）。

        '哪里' 与 '这里/上面/下面' 都出现在 '在_ ' 槽里 → 相似度高；
        回答 '在哪里' 时用这个把候选拉向地点词，而不是动作词。
        """
        if not anchor or w == anchor:
            return 1.0 if w == anchor else 0.0
        a = self.word_frames.get(w)
        b = self.word_frames.get(anchor)
        if not a or not b:
            return 0.0
        return self._vec_cos(a, b)

    def _candidate_words(self, frame, topics, state, world, limit=120, anchor=None):
        """槽位候选：该句式实听填充词 + 与上下文高度共现的词 + 话题词。"""
        st = self.frames[frame]
        fillers = st["fillers"]
        lit = [w for w in frame if w != "_"]
        scores = Counter()
        for w, c in fillers.items():
            scores[w] += 1.6 + 0.8 * math.log1p(c)
        ctx = Counter()
        for lw in lit:
            for w, c in self.cooc.get(lw, {}).items():
                ctx[w] += c * (1.0 if lw != "_" else 0.0)
        for w, c in ctx.most_common(limit):
            scores[w] += 0.55 * math.log1p(c)
        for w in topics:
            if w in self.word_count and w not in FUNCTION_WORDS:
                scores[w] += 1.0
        # 去掉功能词、疑问词（疑问词不能拿来回答）
        out = []
        for w in scores:
            # 输出槽位只放实词：功能词、疑问词、疑问词组成的短语一律不填
            if w in FUNCTION_WORDS:
                continue
            if any(cue in w for cue in WH_WORDS) or any(cue in w for cue in YESNO_WORDS):
                continue
            out.append(w)
        return out[:limit + 40]

    def _score_filler(self, w, frame, topics, state, world, avoid, anchor=None,
                      context=None):
        st = self.frames[frame]
        fill = st["fillers"]
        in_cat = fill.get(w, 0.0)
        lit = [x for x in frame if x != "_"]
        ctx = list(dict.fromkeys(lit + [x for x in (context or [])
                                        if x not in FUNCTION_WORDS and x != "_"]))
        pmi = 0.0
        for lw in ctx:
            pmi += self._pmi(w, lw)
        pmi = pmi / max(1, len(ctx))
        # 句式越具体（字面词多、槽位类别窄），类别先验越可信；
        # 泛化句式（' _ 了'）更多依赖搭配与话题，避免把"拿了"填进"去哪儿了"。
        lit_n = max(1, len(lit))
        cat_w = 3.0 * (0.55 + 0.45 * lit_n) / (1.0 + 0.12 * math.log1p(len(fill)))
        s = (cat_w * math.log1p(in_cat)
             + 1.05 * pmi
             + 1.5 * self._topic_fit(w, topics)
             + 0.5 * self._state_fit(w, state)
             + 0.2 * self._world_fit(w, world)
             + 0.1 * math.log1p(self.word_count.get(w, 0.0)))
        if anchor:
            s += 1.6 * self._role_sim(w, anchor)
        if len(w) == 1:
            s -= 0.9          # 单字多为切词碎片，优先成词
            if self.char_in_words.get(w, 0) > 4 * max(1.0, self.word_count.get(w, 0)):
                s -= 1.4
        if w in avoid:
            s -= 2.0
        return s

    def _frame_score(self, frame, und, state, world, recent_topics):
        topics = list(und.get("topics", [])) + list(recent_topics or [])
        lit = [w for w in frame if w != "_"]
        align = sum(1.6 for t in topics[:6] if t in lit)
        # 槽位能否承接话题：查 word_frames（O(1)），不再遍历全部填充词
        slot_topic = sum(0.5 for t in topics[:4]
                         if frame in self.word_frames.get(t, {}))
        trans = self.sig_trans.get(und.get("signature"), {}).get(self.signature(frame), 0.0)
        s = (self._frame_static.get(frame, 0.0) + align
             + 0.5 * slot_topic + 0.9 * math.log1p(trans))
        if state is not None:
            s += 0.35 * self._state_fit_sig(frame, state)
        return s

    def _state_fit_sig(self, frame, state):
        row = self.frame_state.get(frame)
        if not row or row[1] <= 0 or state is None:
            return 0.0
        mean = [v / row[1] for v in row[0]]
        d = sum(abs(mean[i] - float(state[i])) for i in range(8)) / 8.0
        return 1.0 - d

    # ---------------- 生成 ----------------
    def _fit_length(self, tokens, max_len=9):
        return tokens and len(tokens) <= max_len

    def _gen_from_frame(self, frame, und, state, world, recent_topics, rng,
                        require_topic=False, avoid=(), anchor=None, context=None,
                        ban=None):
        cands = self._candidate_words(frame, und.get("topics", []), state, world,
                                      anchor=anchor)
        if ban:
            cands = [w for w in cands if w not in ban]
        if not cands:
            return None
        # 地点疑问：槽位必须更像地点（用角色分布学出来的相似度过滤），
        # 否则“小狗在声音”这种搭配会被共现拉进来。
        if anchor in ("哪里", "哪儿", "哪"):
            loc = [w for w in cands if w in LOCATION_HINTS]
            if not loc:
                loc = [w for w in cands if self._role_sim(w, anchor) >= 0.12]
            if loc:
                cands = loc
        if und.get("age_q"):
            age = [w for w in cands if "岁" in w or w in ("长大", "大")
                   or (self._pmi(w, "大") > 0.8 and len(w) >= 2)]
            if age:
                cands = age
        # “今天天气怎么样”：槽位词必须和话题有搭配，不能填“算了”
        if anchor and anchor not in WH_WORDS and anchor not in ("怎么样", "怎么"):
            cands = [w for w in cands if w != anchor]
            if anchor in self.word_count:
                fit = [w for w in cands if self._pmi(w, anchor) > 0.25]
                if fit:
                    cands = fit
        ctx = context if context is not None else und.get("tokens", [])
        scored = [(self._score_filler(w, frame, und.get("topics", []), state,
                                      world, avoid, anchor, ctx), w) for w in cands]
        scored.sort(reverse=True)
        topics = set(und.get("topics", []))
        pool = scored[:12]
        if require_topic:
            pool = [x for x in pool if x[1] in topics] or pool
        # 带温度的采样：不总是同一句（人也不总是说同一句）
        top = pool[:8]
        if not top:                  # 候选被话题/禁用词过滤空（P20 崩溃修复）
            return None
        weights = [math.exp((sc - top[0][0]) / 0.55) for sc, _ in top]
        filler = rng.choices([w for _, w in top], weights=weights, k=1)[0]
        # 单空句式：把 '_' 换掉
        out = []
        for w in frame:
            if w == "_":
                if filler in FUNCTION_WORDS:
                    return None
                out.append(filler)
            else:
                out.append(w)
        return {"tokens": out, "frame": frame, "filler": filler,
                "score": top[0][0], "text": "".join(out)}

    def _followup_question(self, und, rng):
        """把对方的话变成一句追问：换人称 + 加疑问尾（都是听过的词）。"""
        toks = [w for w in und.get("tokens", [])
                if w not in YESNO_WORDS and w not in ("吧", "呀", "哦", "啦")]
        # “你看/你听”是唤起注意，不是命题的一部分；追问时去掉
        if len(toks) >= 3 and toks[0] in ("你", "我") and toks[1] in ("看", "听"):
            toks = toks[2:]
        elif len(toks) >= 2 and toks[0] in ("你看", "你听", "你看啊", "来", "快"):
            toks = toks[1:]
        if not toks:
            return None
        if any(w in ("你", "我") for w in toks):
            toks = self._swap_person(toks)
        if "吗" in self.word_count:
            out = toks + ["吗"]
        elif "是不是" in self.word_count:
            out = ["是不是"] + toks
        elif "对不对" in self.word_count:
            out = toks + ["对不对"]
        else:
            return None
        if not self._fit_length(out, 9) or not self._valid_output(
                out, partner=und.get("text"), allow_question=True):
            return None
        return {"tokens": out, "frame": None, "filler": None, "score": 0.0,
                "text": "".join(out), "answer_mode": "followup"}

    def _valid_output(self, toks, partner=None, allow_question=False):
        if not toks or len(toks) > 9:
            return False
        if not all(w in self.word_count for w in toks):
            return False
        if not allow_question and any(w in WH_WORDS or w in YESNO_WORDS
                                      for w in toks):
            return False
        # 防复读机：相邻重复词（'这 是 这 是'）
        for a, b in zip(toks, toks[1:]):
            if a == b and a not in ("好", "嗯", "啦"):
                return False
        if partner is not None and "".join(toks) == partner:
            return False
        return True

    def _assemble(self, prefix, gen, suffix):
        # 类别中心词冗余：这是三角形 + 形状 → 这是三角形；我叫雪儿 + 名字 → 我叫雪儿
        if suffix and suffix[0] in ("形状", "颜色", "名字", "东西") and gen.get("filler"):
            if (len(gen["filler"]) >= 2
                    or (suffix[0] == "名字" and "叫" in gen["tokens"])):
                suffix = list(suffix[1:])
        out = list(prefix) + list(gen["tokens"]) + list(suffix)
        if not self._fit_length(out, 9):
            return None
        if not self._valid_output(out):
            return None
        return {"tokens": out, "frame": gen.get("frame"), "filler": gen.get("filler"),
                "score": gen.get("score", 0.0), "text": "".join(out),
                "answer_mode": "wh_template"}

    def _answer_whoami(self, und):
        """“你是谁”：用照护者实际用过的自称/称呼，而不是语料里的“公主”。"""
        toks = und.get("tokens", [])
        if not (toks[:3] == ["你", "是", "谁"] or "你是谁" in und.get("text", "")):
            return None
        for text in ("我是宝宝", "我是小朋友", "我是我"):
            ts = self.tok.segment(text)
            if ts and all(w in self.word_count for w in ts):
                return {"tokens": ts, "frame": None, "filler": None,
                        "score": 0.0, "text": "".join(ts),
                        "answer_mode": "whoami"}
        return None

    def _answer_name(self, und):
        """“你叫什么名字”：没有名字就说没有——不拿语料里的书名冒充自己。"""
        for text in ("我没有名字", "我不知道", "我是宝宝"):
            toks = self.tok.segment(text)
            if toks and all(w in self.word_count for w in toks):
                return {"tokens": toks, "frame": None, "filler": None,
                        "score": 0.0, "text": "".join(toks),
                        "answer_mode": "name_unknown"}
        return None

    def _answer_action(self, und, state, world, recent_topics, rng, avoid):
        """“它在干什么/你在做什么”：把‘干/做’归一成‘在’，再填动作槽。

        ‘在干’在语料里是一个词，直接替换疑问词会得到“它在干小猫”。
        这里做一步句法归一：它 + 在干 + 什么 → 它 + 在 + _。
        """
        toks = und["tokens"]
        wi = und.get("wh_index")
        if wi is None or wi == 0:
            return None
        left = toks[wi - 1]
        if not any(v in left for v in ("干", "做")):
            return None
        variants = ([self._swap_person(toks), toks]
                    if any(w in ("你", "我") for w in toks) else [toks])
        for v in variants:
            wi2 = v.index(left)
            prefix = v[:wi2]
            for verb in ("在",):
                tmpl = tuple(prefix + [verb, "_"])
                if tmpl not in self.frames:
                    continue
                ban = set(LOCATION_HINTS) | {
                    w for w in self.word_count
                    if any(ch in w for ch in "园家校店院面边里外")}
                g = self._gen_from_frame(tmpl, und, state, world, recent_topics,
                                         rng, avoid=set(avoid), anchor=None,
                                         context=v, ban=ban)
                if not g:
                    continue
                out = list(prefix) + [verb, g["filler"]]
                if self._valid_output(out, partner=und.get("text")):
                    return {"tokens": out, "frame": tmpl,
                            "filler": g["filler"], "score": g.get("score", 0.0),
                            "text": "".join(out),
                            "answer_mode": "action_template"}
        return None

    def _direct_substitute(self, und, state, world, recent_topics, rng, avoid):
        """把问句里的疑问词直接换成一个实词——用对方给的句法，不要求整句听过。

        这是“重组”的核心：句式框架来自对方的话，填充词必须是听过的，
        并且至少与一个相邻实词有搭配（PMI>0.3），否则不成立。
        """
        toks = und["tokens"]
        wi = und.get("wh_index")
        if wi is None:
            return None
        wh = toks[wi]
        variants = [toks]
        if any(w in ("你", "我") for w in toks):
            variants = [self._swap_person(toks), toks]
        topics = und.get("topics", [])
        base_tmpl = tuple(toks[:wi] + ["_"] + toks[wi + 1:])
        for v in variants:
            left = v[wi - 1] if wi > 0 else None
            right = v[wi + 1] if wi + 1 < len(v) else None
            tmpl = tuple(v[:wi] + ["_"] + v[wi + 1:])
            # 人称互换后模板可能没见过（"你长大了"→"我长大了"）：
            # 槽位类别从原模板借过来，避免答成"我大了"。
            tmpls = [t for t in (tmpl, base_tmpl) if t in self.frames]
            if tmpls:
                cands = []
                for t in tmpls:
                    for w in self._candidate_words(t, topics, state, world,
                                                   anchor=(wh if wh in WH_WORDS else None)):
                        if w not in cands:
                            cands.append(w)
            else:
                pool = Counter()
                for nb in (left, right):
                    if nb and nb in self.cooc:
                        row = self.cooc[nb]
                        for w, c in row.most_common(120):
                            pool[w] += c
                        # 高频不等于合适：把与邻词高搭配的少见词也放进候选
                        hi = sorted(((self._pmi(w, nb), w, c)
                                     for w, c in row.items() if c >= 1),
                                    reverse=True)[:120]
                        for p, w, c in hi:
                            if p > 0.2:
                                pool[w] += max(1.0, c * 0.5)
                if not pool:
                    for w, c in self.word_count.most_common(500):
                        pool[w] = c
                cands = [w for w in pool if w not in FUNCTION_WORDS
                         and w not in WH_WORDS and w not in YESNO_WORDS]
            # 疑问类型过滤
            if wh in ("哪里", "哪儿", "哪"):
                loc = [w for w in cands if w in LOCATION_HINTS]
                if not loc:
                    loc = [w for w in cands if self._role_sim(w, wh) >= 0.12]
                if loc:
                    cands = loc
            if wh == "多大":
                age = [w for w in cands if "岁" in w or w in ("长大", "大")]
                if age:
                    cands = age
            # 类别中心词的形态线索：形状词多带“形”，颜色词多带“色”
            if right == "形状":
                shape = [w for w in cands if "形" in w]
                if not shape:
                    shape = [w for w in cands if w in ("方", "圆", "三角", "正方")]
                if shape:
                    cands = shape
            if right == "颜色":
                color = [w for w in cands if "色" in w or w in (
                    "红", "黄", "蓝", "绿", "黑", "白", "紫", "灰", "粉", "橙")]
                if color:
                    cands = color
            scored = []
            for w in cands:
                if w in (left, right) or w in v:
                    continue
                in_cat = 0.0
                for t in tmpls:
                    in_cat += self.frames[t]["fillers"].get(w, 0.0)
                pl = self._pmi(w, left) if left else -0.5
                pr = self._pmi(w, right) if right else -0.5
                pmi = max(pl, pr)
                if in_cat <= 0 and pmi < 0.3:
                    continue
                # 右邻是类别中心词（什么形状/什么颜色/什么名字）：必须与中心词搭配
                if (right and right not in FUNCTION_WORDS and wh in ("什么", "哪个", "哪种")):
                    # 类别中心词必须在词序上也成立：三角形+形状（对），
                    # 而不是“形状真漂亮”这种反向共现
                    before = self.seq.get(w, {}).get(right, 0.0)
                    if before <= 0 and self._pmi(w, right) <= 1.0:
                        continue
                sc = (2.4 * math.log1p(in_cat) + 1.2 * pmi
                      + 0.9 * self._topic_fit(w, topics)
                      + 0.4 * self._state_fit(w, state)
                      + 0.2 * self._world_fit(w, world)
                      + 0.1 * math.log1p(self.word_count.get(w, 0.0)))
                if wh in ("哪里", "哪儿", "哪"):
                    sc += 1.8 * self._role_sim(w, wh)
                if len(w) == 1:
                    sc -= 1.6
                    if self.char_in_words.get(w, 0) > 4 * max(1.0, self.word_count.get(w, 0)):
                        sc -= 1.5
                if w in avoid:
                    sc -= 2.0
                scored.append((sc, w))
            if not scored:
                continue
            scored.sort(reverse=True)
            top = scored[:6]
            wts = [math.exp((sc - top[0][0]) / 0.5) for sc, _ in top]
            filler = rng.choices([w for _, w in top], weights=wts, k=1)[0]
            out = list(v[:wi]) + [filler] + list(v[wi + 1:])
            # 类别中心词冗余：这是紫 + 颜色（紫是单字保留）；这是三角形 + 形状（删）
            if right in ("形状", "颜色", "名字", "东西") and len(filler) >= 2:
                out = out[:wi + 1] + out[wi + 2:]
            if not self._valid_output(out, partner=und.get("text")):
                continue
            return {"tokens": out, "frame": tmpl if tmpl in self.frames else None,
                    "filler": filler, "score": top[0][0], "text": "".join(out),
                    "answer_mode": "question_template"}
        return None

    def _answer_wh(self, und, state, world, recent_topics, rng, avoid):
        """问句当答句模板：挖掉疑问词，填一个语境合适的实词。

        优先整句模板；整句没见过时，逐步裁掉句首/句尾的修饰成分，
        找「疑问词附近的那个句式」，填好后把裁掉的部分原样拼回。
        例：苹果在哪里 → 苹果 + 在_ → 苹果在这里
        """
        toks = list(und["tokens"])
        wi = und.get("wh_index")
        if wi is None:
            return None
        wh = toks[wi]
        topics = und.get("topics", [])
        wa = self._answer_whoami(und)
        if wa:
            return wa
        if "名字" in toks or "叫什么" in und.get("text", ""):
            nm = self._answer_name(und)
            if nm:
                return nm
        # “在干什么/做什么”：先把动词归一成“在”，再填动作槽
        if wh == "什么":
            a = self._answer_action(und, state, world, recent_topics, rng, avoid)
            if a:
                return a
        # 先试“直接槽位替换”（用对方的句法，不要求整句听过）
        if wh != "为什么":
            d = self._direct_substitute(und, state, world, recent_topics, rng, avoid)
            if d:
                return d
        # 疑问词较泛（什么/谁）时，用话题词当角色锚：问“什么形状”应填形状词
        anchor = wh
        if wh in ("什么", "谁", "几", "多少", "怎么样", "怎么", "多大") and topics:
            anchor = topics[-1]
        if wh == "多大":
            und = dict(und)
            und["age_q"] = True
        if wh == "为什么":
            anchor = None
            if ("因为", "_") in self.frames:
                g = self._gen_from_frame(("因为", "_"), und, state, world,
                                         recent_topics, rng,
                                         avoid=set(avoid) | set(toks),
                                         anchor=None)
                if g:
                    content = [w for w in toks if w not in FUNCTION_WORDS]
                    out = list(g["tokens"])
                    if content and content[-1] not in out:
                        out.append(content[-1])
                    if self._fit_length(out, 9) and self._valid_output(
                            out, partner=und.get("text")):
                        return {"tokens": out, "frame": ("因为", "_"),
                                "filler": g["filler"], "score": g.get("score", 0.0),
                                "text": "".join(out),
                                "answer_mode": "why_because"}
        # 候选模板：整句 → 裁句尾 → 裁句首 → 两边都裁
        cands = []
        variants = [toks]
        if any(w in ("你", "我") for w in toks):
            variants = [self._swap_person(toks), toks]
        for v in variants:
            cands.append(([], v[:wi] + ["_"] + v[wi + 1:], []))
            for cut in range(len(v) - 1, wi, -1):       # 裁句尾
                cands.append(([], v[:wi] + ["_"] + v[wi + 1:cut], v[cut:]))
            for st in range(1, wi + 1):                 # 裁句首
                cands.append((v[:st], v[st:wi] + ["_"] + v[wi + 1:], []))
                for cut in range(len(v) - 1, wi, -1):   # 两边都裁
                    cands.append((v[:st], v[st:wi] + ["_"] + v[wi + 1:cut],
                                  v[cut:]))
        seen_tmpl = set()
        for prefix, tmpl, suffix in cands:
            tmpl = tuple(tmpl)
            if tmpl in seen_tmpl or tmpl not in self.frames:
                continue
            seen_tmpl.add(tmpl)
            if not all(w in self.word_count for w in prefix + suffix):
                continue
            # 槽位如果就是原疑问词的位置，anchor 用疑问词本身（角色类别）
            g = self._gen_from_frame(tmpl, und, state, world, recent_topics, rng,
                                     avoid=set(avoid) | set(toks), anchor=anchor)
            if not g:
                continue
            out = self._assemble(prefix, g, suffix)
            if out:
                out["score"] = g.get("score", 0.0) + 1.0 * len(prefix + suffix)
                return out
        # 最后兜底：找与问句共享字面词、且能填话题的句式
        best = None
        ranked, seen = [], set()
        for w in toks:
            for frame in self._literal_frames.get(w, ()):
                if frame in seen:
                    continue
                seen.add(frame)
                ov = sum(1 for x in frame if x != "_" and x in toks)
                if ov:
                    ranked.append((ov, frame))
        ranked.sort(key=lambda x: -x[0])
        for ov, frame in ranked[:20]:
            g = self._gen_from_frame(frame, und, state, world, recent_topics, rng,
                                     avoid=set(avoid) | set(toks), anchor=anchor)
            if not g:
                continue
            out = self._assemble([], g, [])
            if out:
                out["score"] = g.get("score", 0.0) + 1.2 * ov
                out["answer_mode"] = "stitch"
                if best is None or out["score"] > best["score"]:
                    best = out
        return best

    def _answer_imperative(self, und, state, world, recent_topics, rng):
        for text in ("好呀", "好的", "好", "嗯", "我们走吧", "走吧", "可以"):
            toks = self.tok.segment(text)
            if toks and all(w in self.word_count for w in toks):
                return {"tokens": toks, "frame": None, "filler": None,
                        "score": 0.0, "text": "".join(toks),
                        "answer_mode": "imperative"}
        return None

    def _answer_praise(self, und):
        text = und.get("text", "")
        if not any(w in text for w in ("真棒", "好棒", "真乖", "好乖", "厉害",
                                       "聪明", "漂亮", "能干", "好孩子")):
            return None
        for c in ("谢谢", "谢谢你", "嗯", "是吗", "真的吗"):
            toks = self.tok.segment(c)
            if toks and all(w in self.word_count for w in toks):
                return {"tokens": toks, "frame": None, "filler": None,
                        "score": 0.0, "text": "".join(toks),
                        "answer_mode": "praise"}
        return None

    def _paraphrase(self, und, state, world, recent_topics, rng):
        """接话变体：换人称、加语气词、加应答词——每个词都听过。"""
        toks = list(und.get("tokens", []))
        if not toks:
            return None
        # “你看/你听”是唤起注意，不是命题；去掉再换人称
        if len(toks) >= 3 and toks[0] in ("你", "我") and toks[1] in ("看", "听"):
            toks = toks[2:]
        elif len(toks) >= 2 and toks[0] in ("你看", "你听"):
            toks = toks[1:]
        # 人称互换（陈述句里对方说“我”，回应通常说“你”）
        if any(w in ("你", "我") for w in toks):
            toks = self._swap_person(toks)
        particles = [p for p in ("呀", "哦", "啦", "呢", "吧")
                     if p in self.word_count]
        if particles and toks[-1] not in particles and rng.random() < 0.65:
            toks.append(rng.choice(particles))
        if rng.random() < 0.30:
            for c in ("嗯", "对呀", "对", "哦"):
                if c in self.word_count:
                    toks = [c] + toks
                    break
        if not self._valid_output(toks, partner=und.get("text")):
            return None
        return {"tokens": toks, "frame": None, "filler": None,
                "score": 0.0, "text": "".join(toks), "answer_mode": "paraphrase"}

    def _answer_yesno(self, und, state, world, recent_topics, rng):
        """是非问：去掉句末语气词，'你'→'我'，加一个实听过的应答词。"""
        raw = list(und["tokens"])
        # 跨词 A不A：饿 不 饿 → 饿；好不好 → 好
        collapsed, i = [], 0
        while i < len(raw):
            if (i + 2 < len(raw) and raw[i + 1] == "不"
                    and raw[i] == raw[i + 2]):
                # 三词 A不A（你 饿 不 饿）是谓语，保留 A；
                # 单词 A不A（好不好）在句末是问句标签，删掉。
                collapsed.append(raw[i])
                i += 3
            elif (len(raw[i]) == 3 and raw[i][1] == "不"
                  and raw[i][0] == raw[i][2]):
                if i != len(raw) - 1:
                    collapsed.append(raw[i][0])
                i += 1
            else:
                collapsed.append(raw[i])
                i += 1
        toks = [w for w in collapsed if w and w not in YESNO_WORDS]
        if not toks:
            return None
        if any(w in ("你", "我") for w in toks):
            toks = self._swap_person(toks)
        if not all(w in self.word_count for w in toks):
            return None
        # 应答词必须实际听过；没有就不加（不发明“对/是”）
        cue = None
        for c in ("嗯", "对", "是", "好", "对呀", "对啊"):
            if c in self.word_count:
                cue = c
                break
        if cue and rng.random() < 0.7:
            toks = [cue] + toks
        if not self._fit_length(toks):
            return None
        return {"tokens": toks, "frame": None, "filler": None,
                "score": 0.0, "text": "".join(toks), "answer_mode": "yesno_echo"}

    def _answer_greeting(self, und, state, world, recent_topics, rng):
        # 优先用实听过的问候句式；否则用听过的“你 好 呀”类片段
        for text in ("你好呀", "你好", "你 好", "早", "嗯 你 好"):
            toks = self.tok.segment(text)
            if toks and all(w in self.word_count for w in toks):
                return {"tokens": toks, "frame": None, "filler": None,
                        "score": 0.0, "text": "".join(toks), "answer_mode": "greeting"}
        return None

    def respond(self, text, state=None, world=None, recent_topics=None,
                rng=None, avoid=(), temperature=0.55):
        rng = rng or random.Random()
        und = self.understand(text, state=state, world=world,
                              recent_topics=recent_topics)
        avoid = set(avoid)
        act = und["speech_act"]
        if act == "greeting":
            g = self._answer_greeting(und, state, world, recent_topics, rng)
            if g:
                return und, g
        if act == "wh_question":
            g = self._answer_wh(und, state, world, recent_topics, rng, avoid)
            if g:
                return und, g
        if act == "yesno_question":
            g = self._answer_yesno(und, state, world, recent_topics, rng)
            if g and self._valid_output(g["tokens"], partner=text, allow_question=False):
                return und, g
        if act == "imperative":
            g = self._answer_imperative(und, state, world, recent_topics, rng)
            if g:
                return und, g
        pr = self._answer_praise(und)
        if pr is not None:
            return und, pr
        # 陈述/答不出来：句式接话 + 接话变体，取更像人的那个
        topics = list(und.get("topics", [])) + list(recent_topics or [])
        # 候选句式只取「话题词出现在字面或槽位里」的，避免每次遍历 1.7 万句式
        cand_frames = set()
        for t in topics[:8]:
            cand_frames.update(self._literal_frames.get(t, ()))
            cand_frames.update(self.word_frames.get(t, {}).keys())
        if not cand_frames:
            cand_frames = set(self._frames_sorted[:400])
        else:
            cand_frames = set(sorted(cand_frames,
                                     key=lambda f: -self._frame_static.get(f, 0.0))[:800])
        scored = []
        for frame in cand_frames:
            lit = [w for w in frame if w != "_"]
            if not lit:
                continue
            sc = self._frame_score(frame, und, state, world, recent_topics)
            if topics and any(t in lit for t in topics[:4]):
                sc += 0.8
            scored.append((sc, frame))
        scored.sort(key=lambda x: -x[0])
        best = None
        partner_content = [w for w in und.get("tokens", [])
                           if w not in FUNCTION_WORDS]
        last_content = partner_content[-1] if partner_content else None
        for sc, frame in scored[:24]:
            if sc < -0.5:
                continue
            # 只有一个实词的陈述句不做句式接话（否则会接出“你看它在干难过”）
            if len(partner_content) < 2:
                continue
            topics_in = set(und.get("topics", []))
            g = self._gen_from_frame(frame, und, state, world, recent_topics,
                                     rng, require_topic=bool(topics_in), avoid=avoid)
            if not g:
                continue
            if not self._valid_output(g["tokens"], partner=text):
                continue
            # 陈述接话：必须带进至少一个「对方没说过的实词」，否则只是复读
            partner_toks = set(und.get("tokens", []))
            partner_content = [w for w in und.get("tokens", [])
                               if w not in FUNCTION_WORDS]
            overlap = set(g["tokens"]) & set(partner_content)
            # 陈述接话至少接住对方两个实词（话题+谓语），否则就是答非所问
            if len(overlap) < min(2, len(partner_content)):
                continue
            # 词序不能颠倒：接住的实词在答句里的相对顺序应与原句一致
            g_order = [w for w in g["tokens"] if w in overlap]
            p_order = [w for w in partner_content if w in overlap]
            if g_order != p_order:
                continue
            # 必须接住对方的谓语/最后实词，不能只抓一个话题词
            if last_content and last_content not in g["tokens"]:
                continue
            new_content = [w for w in g["tokens"]
                           if w not in partner_toks and w not in FUNCTION_WORDS
                           and len(w) >= 2]
            if not new_content and len(overlap) < 2:
                continue
            # 仍要求与对方话题有某种联系
            if topics_in and not (set(g["tokens"]) & topics_in) and sc < 2.0:
                continue
            g["score"] = sc + 0.5 * g["score"]
            g["answer_mode"] = "frame"
            if best is None or g["score"] > best["score"]:
                best = g
            if best["score"] > 3.0:
                break
        para = self._paraphrase(und, state, world, recent_topics, rng)
        follow = self._followup_question(und, rng)
        if follow is not None and rng.random() < 0.42:
            return und, follow
        if para is not None and (best is None or rng.random() < 0.80):
            return und, para
        if best is not None:
            return und, best
        if para is not None:
            return und, para
        # 最保守：一个实听过的应答词（不生成、不冷场）
        for c in ("嗯", "哦", "对呀", "对", "好", "是呀", "这样啊"):
            toks = self.tok.segment(c)
            if toks and all(w in self.word_count for w in toks):
                return und, {"tokens": toks, "frame": None, "filler": None,
                             "score": 0.0, "text": "".join(toks),
                             "answer_mode": "backchannel"}
        return und, None

    # ---------------- 持久化 ----------------
    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        frames = {}
        for fr, st in self.frames.items():
            frames["\u0001".join(fr)] = {"n": st["n"],
                                         "fillers": dict(st["fillers"])}
        d = {
            "meta": self.meta,
            "frames": frames,
            "word_count": dict(self.word_count),
            "word_state": {k: v for k, v in self.word_state.items()},
            "word_world": {k: v for k, v in self.word_world.items()},
            "cooc": {k: dict(v) for k, v in self.cooc.items()},
            "seq": {k: dict(v) for k, v in self.seq.items()},
            "sig_trans": {"\u0001".join(k):
                          {"\u0001".join(k2): v2 for k2, v2 in v.items()}
                          for k, v in self.sig_trans.items()},
            "frame_state": {"\u0001".join(k): v for k, v in self.frame_state.items()},
            "frame_world": {"\u0001".join(k): v for k, v in self.frame_world.items()},
            "seen": sorted(self.seen)[:200000],
            "n_utt": self.n_utt,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)

    @classmethod
    def load(cls, path, lexicon_path=DEFAULT_LEXICON):
        g = cls(lexicon_path)
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        g.meta = d.get("meta", {})
        g.frames = {}
        for k, st in d.get("frames", {}).items():
            g.frames[tuple(k.split("\u0001"))] = {
                "n": st["n"], "fillers": Counter(st["fillers"])}
        g.word_count = Counter(d.get("word_count", {}))
        g.word_state = d.get("word_state", {})
        g.word_world = d.get("word_world", {})
        g.cooc = defaultdict(Counter)
        for k, v in d.get("cooc", {}).items():
            g.cooc[k] = Counter(v)
        g.seq = defaultdict(Counter)
        for k, v in d.get("seq", {}).items():
            g.seq[k] = Counter(v)
        g.sig_trans = defaultdict(Counter)
        for k, v in d.get("sig_trans", {}).items():
            g.sig_trans[tuple(k.split("\u0001"))] = Counter(
                {tuple(k2.split("\u0001")): v2 for k2, v2 in v.items()})
        g.frame_state = {tuple(k.split("\u0001")): v
                         for k, v in d.get("frame_state", {}).items()}
        g.frame_world = {tuple(k.split("\u0001")): v
                         for k, v in d.get("frame_world", {}).items()}
        g.seen = set(d.get("seen", []))
        g.n_utt = d.get("n_utt", g.meta.get("n_utt", 0))
        g.finalize()
        return g
