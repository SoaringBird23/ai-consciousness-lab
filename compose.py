"""compose.py — P18 词级组合（零幻觉=词法级，重组=句法级）

原则（用户 2026-10-07 定的 R3/C1 原则，P18 沿用）：
  - 零幻觉**只在词法级**：组合出的每一段都必须是**系统实听过**的词；
  - 重组是**句法级**：允许把听过的词按新顺序拼成**整体从未逐字听过**的序列。

机制：
  - 词表 lexicon 来自环境语料的无监督「新词发现」（tools/build_words.py），
    是照护者语言的词库（世界属性）；系统运行时只学「词→词」相继。
  - 在线：每听到一句 → 切词 → 记相邻词对（词二元表）。
  - 组合：以当前**检索胜者**（其本身已由 P14 意图选择挑出）为锚，取其末尾词，
    按词二元表逐词抽后继拼 k 个词 → 新词序。局部有据（相邻词对听过），
    整体新（整串未逐字听过）。

对照臂 shuffle：词表相同（词法纯净性不受影响），但把「词→词」关联破坏——
抽后继时从**实听词表**均匀随机取，而非按词二元表 ⇒ 结构指标应回落。
"""
import json
import os
import random

_ROOT = os.path.dirname(os.path.abspath(__file__))


def load_lexicon(path):
    full = path if os.path.isabs(path) else os.path.join(_ROOT, path)
    if not os.path.exists(full):
        return set(), 4
    with open(full, encoding="utf-8") as f:
        d = json.load(f)
    maxlen = int(d.get("params", {}).get("MAXLEN", 4))
    return set(d.get("words", [])), maxlen


class WordComposer:
    def __init__(self, config):
        cfg = config.get("word_compose", {})
        self.enabled = bool(cfg.get("enabled", False))
        self.shuffle = bool(cfg.get("shuffle", False))
        self.chain_len = int(cfg.get("chain_len", 2))
        self.lexicon, self.maxlen = set(), 4
        self.bigram = {}          # 词 -> {后继词: 计数}
        self.seen = set()         # 实听过的**整句**（判「整体新」）
        self.heard_words = set()  # 实听过的**词**（零幻觉词法级硬约束 + shuffle 采样池）
        self.n_learned = 0
        self.n_composed = 0
        self.n_novel = 0
        if self.enabled:
            self.lexicon, self.maxlen = load_lexicon(
                cfg.get("lexicon_file", "corpus/lexicon.json"))

    # ---- 切词：最长匹配；未命中单字保留（也是听过的）----
    def segment(self, text):
        out, i, L = [], 0, len(text)
        while i < L:
            hit = None
            for ln in range(min(self.maxlen, L - i), 1, -1):
                if text[i:i + ln] in self.lexicon:
                    hit = text[i:i + ln]
                    break
            if hit:
                out.append(hit)
                i += len(hit)
            else:
                out.append(text[i])
                i += 1
        return out

    def learn(self, text):
        """听到一句：切词、更新词二元表与实听词表。"""
        if not self.enabled or not text:
            return
        self.seen.add(text)
        words = self.segment(text)
        for w in words:
            self.heard_words.add(w)
        for a, b in zip(words, words[1:]):
            row = self.bigram.setdefault(a, {})
            row[b] = row.get(b, 0) + 1
        self.n_learned += 1

    def _successor(self, w):
        if self.shuffle:
            pool = self.heard_words or self.lexicon
            return random.choice(tuple(pool)) if pool else None
        row = self.bigram.get(w)
        if not row:
            return None
        pop = list(row.keys())
        wts = [row[k] for k in pop]
        return random.choices(pop, weights=wts, k=1)[0]

    def compose(self, anchor_text):
        """以检索胜者为锚，拼一条新词序。返回 dict 或 None（无法组合时）。"""
        if not self.enabled or not anchor_text:
            return None
        words = self.segment(anchor_text)
        if not words:
            return None
        seq = list(words)
        for _ in range(self.chain_len):
            nxt = self._successor(seq[-1])
            if nxt is None:
                break
            seq.append(nxt)
        if len(seq) <= len(words):
            return None                      # 未拼出新词（锚无后继）→ 退回原句
        text = "".join(seq)
        pairs = list(zip(seq, seq[1:]))
        real = sum(1 for a, b in pairs if b in self.bigram.get(a, {}))
        novel = text not in self.seen
        self.n_composed += 1
        self.n_novel += 1 if novel else 0
        return {"text": text, "words": seq, "anchor": anchor_text, "novel": novel,
                "n_pairs": len(pairs), "n_pairs_real": real,
                "purity": sum(1 for w in seq if w in self.heard_words) / len(seq)}

    # ---- 持久化 ----
    def snapshot(self):
        # 优化：不持久化 seen（可达 7 万串）——它等价于 set(记忆里的整句)，
        # 载入时由 Language.load 从 memory 重建，避免每心跳重排大集合。
        return {"enabled": self.enabled, "shuffle": self.shuffle,
                "chain_len": self.chain_len,
                "bigram": self.bigram,
                "heard_words": sorted(self.heard_words),
                "n_learned": self.n_learned, "n_composed": self.n_composed,
                "n_novel": self.n_novel}

    def save(self, path):
        if not self.enabled:
            return
        full = path if os.path.isabs(path) else os.path.join(_ROOT, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False)

    def load(self, path):
        full = path if os.path.isabs(path) else os.path.join(_ROOT, path)
        if not self.enabled or not os.path.exists(full):
            return False
        try:
            with open(full, encoding="utf-8") as f:
                d = json.load(f)
            self.bigram = {k: dict(v) for k, v in d.get("bigram", {}).items()}
            self.heard_words = set(d.get("heard_words", []))
            # 兼容旧快照：若含 seen 则用之；否则由调用方从 memory 重建
            self.seen = set(d.get("seen", []))
            self.n_learned = int(d.get("n_learned", 0))
            self.n_composed = int(d.get("n_composed", 0))
            self.n_novel = int(d.get("n_novel", 0))
            return True
        except Exception:
            return False
