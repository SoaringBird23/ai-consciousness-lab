"""semantics.py — P16 指称落地（referent grounding）

对每个片段型 w 维护在线指称表 P(φ_class | w)：
  φ = 外部世界场 milieu.field（∈[0,1]），二值化后作为「世界类」。
  cls=1 表示 field>threshold（HIGH）；cls=0 表示 ≤threshold（LOW）。

- 学习：每次听到 w 时，把当时的真实 φ 类累加进 P(φ|w)。零生成、零幻觉。
- shuffle 臂（内容对照）：把 w 的 φ 替换为一个**随机历史 φ**，破坏 w↔φ 的对应，
  词表保持完整（分析器仍能识别 world 词），但关联被摧毁 → 应回落到 chance。

落盘：
  semantics.json    —— 指称表快照（w → [n_low, n_high]）
  grounding.jsonl   —— 逐次绑定 {"t","w","phi","field"}（分析器据此做留出解码）
"""
import json
import os
import random

STATE_DIR = os.environ.get("STATE_DIR", "state")
_ROOT = os.path.dirname(__file__)
SEM_PATH = os.path.join(_ROOT, STATE_DIR, "semantics.json")
GRD_PATH = os.path.join(_ROOT, STATE_DIR, "grounding.jsonl")


class Semantics:
    def __init__(self, config):
        cfg = config.get("semantics", {})
        self.enabled = bool(cfg.get("enabled", False))
        self.shuffle = bool(cfg.get("shuffle", False))
        self.threshold = float(cfg.get("phi_threshold", 0.5))
        self.table = {}          # w -> [n_low, n_high]
        self.n_bind = 0

    def phi_class(self, field):
        return 1 if float(field) > self.threshold else 0

    def bind(self, text, world_field, sim_time):
        """听到片段 text 时调用：把当前世界类累加进指称表，并落盘一条绑定记录。"""
        if not self.enabled or text is None or world_field is None:
            return
        true_cls = self.phi_class(world_field)
        # shuffle 臂（内容对照）：把 w 的 φ 替换为与内容无关的均匀随机类，
        # 破坏 w↔φ 的对应。词表保持完整，但关联被摧毁 → 应回落到 chance。
        cls = random.getrandbits(1) if self.shuffle else true_cls
        row = self.table.setdefault(text, [0, 0])
        row[cls] += 1
        self.n_bind += 1
        try:
            os.makedirs(os.path.dirname(GRD_PATH), exist_ok=True)
            with open(GRD_PATH, "a") as f:
                f.write(json.dumps({"t": round(sim_time, 1), "w": text, "phi": cls,
                                    "field": round(float(world_field), 4)},
                                   ensure_ascii=False) + "\n")
        except Exception:
            pass

    def snapshot(self):
        return {"enabled": self.enabled, "shuffle": self.shuffle,
                "threshold": self.threshold, "n_bind": self.n_bind,
                "table": self.table}

    def save(self):
        if not self.enabled:
            return
        os.makedirs(os.path.dirname(SEM_PATH), exist_ok=True)
        with open(SEM_PATH, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)

    def load(self):
        if not self.enabled or not os.path.exists(SEM_PATH):
            return False
        try:
            with open(SEM_PATH, encoding="utf-8") as f:
                d = json.load(f)
            self.table = {k: list(v) for k, v in d.get("table", {}).items()}
            self.n_bind = int(d.get("n_bind", 0))
            return True
        except Exception:
            return False
