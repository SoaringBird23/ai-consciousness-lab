"""dialogue.py — P19 对话状态向量（多轮）

问题：系统当前「检索靠自身状态、发声靠听者效果」，**不依赖对话伙伴的上一轮** → 不会对话。
做法：维护一个**多轮对话状态向量 D**（稀疏、按轮衰减），由**双方**每一轮更新；
     系统发声/检索的候选按与 D 的关联加权 ⇒ 回应**受近几轮**（不只上一轮）驱动。

- D 的键空间 = 实听「词」（词表来自环境侧无监督新词发现 corpus/lexicon.json）。
- 每轮：先整体衰减（半衰期 half_life_turns 轮），再把本轮各词计入 D。
- 关联 rel(text) = 候选各词在 D 中的平均权重（无词 → 0）。
- 对照 shuffle：把每轮词替换为**同数量的随机词表词**——幅值/衰减结构不变，
  但「轮↔词」关联被打断 ⇒ 关联应变为无信息。

零幻觉：D 只由听过的词构成；不生成任何新词。
"""
import json
import os
import random

_ROOT = os.path.dirname(os.path.abspath(__file__))
TURNS_PATH = os.path.join(_ROOT, os.environ.get("STATE_DIR", "state"),
                          "dialogue_turns.jsonl")


def load_words(path):
    full = path if os.path.isabs(path) else os.path.join(_ROOT, path)
    if not os.path.exists(full):
        return set(), 4
    with open(full, encoding="utf-8") as f:
        d = json.load(f)
    return set(d.get("words", [])), int(d.get("params", {}).get("MAXLEN", 4))


class DialogueState:
    def __init__(self, config):
        cfg = config.get("dialogue", {})
        self.enabled = bool(cfg.get("enabled", False))
        self.shuffle = bool(cfg.get("shuffle", False))
        self.half_life_turns = float(cfg.get("half_life_turns", 3.0))
        self.min_weight = float(cfg.get("min_weight", 0.02))
        self.lexicon, self.maxlen = set(), 4
        self.d = {}                 # word -> 衰减权重
        self.n_turns = 0
        self.n_self = 0
        self.n_partner = 0
        self.last_partner_text = None   # P19b：伙伴紧邻上一轮（去回声用）
        if self.enabled:
            self.lexicon, self.maxlen = load_words(
                cfg.get("lexicon_file", "corpus/lexicon.json"))
            # shuffle 抽样池：排序缓存。集合迭代顺序受 PYTHONHASHSEED 影响、跨进程不确定，
            # 排序后抽样分布不变、但结果可复现（shuf 对照臂必须可复现）。
            self._lex_pool = tuple(sorted(self.lexicon))

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

    def _decay(self):
        fac = 0.5 ** (1.0 / max(1e-6, self.half_life_turns))
        if fac >= 1.0:
            return
        drop = []
        for k in self.d:
            v = self.d[k] * fac
            if v < self.min_weight:
                drop.append(k)
            else:
                self.d[k] = v
        for k in drop:
            del self.d[k]

    def observe_turn(self, text, speaker="partner", sim_time=None):
        """记录一轮（partner=照护者，self=系统发声）。先衰减再计入。"""
        if not self.enabled or not text:
            return
        self._decay()
        self.n_turns += 1
        if speaker == "self":
            self.n_self += 1
        else:
            self.n_partner += 1
            self.last_partner_text = text
        words = self.segment(text)
        if self.shuffle and words:
            # 对照：同数量随机词表词替换——保留幅值结构、打断轮↔词关联
            pool = self._lex_pool
            words = [random.choice(pool) for _ in words] if pool else words
        for w in words:
            self.d[w] = self.d.get(w, 0.0) + 1.0
        # 轮次日志（原始文本，供分析：轮次邻接性/多轮链）
        try:
            os.makedirs(os.path.dirname(TURNS_PATH), exist_ok=True)
            with open(TURNS_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": sim_time, "speaker": speaker,
                                    "text": text}, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def relevance(self, text):
        """候选 text 与当前对话状态的关联（各词 D 权重的均值）。"""
        if not self.enabled:
            return 0.0
        words = self.segment(text)
        if not words:
            return 0.0
        return sum(self.d.get(w, 0.0) for w in words) / len(words)

    # ---- 持久化 ----
    def snapshot(self):
        return {"n_turns": self.n_turns, "n_self": self.n_self,
                "n_partner": self.n_partner, "d": self.d}

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
            self.d = {k: float(v) for k, v in d.get("d", {}).items()}
            self.n_turns = int(d.get("n_turns", 0))
            self.n_self = int(d.get("n_self", 0))
            self.n_partner = int(d.get("n_partner", 0))
            return True
        except Exception:
            return False
