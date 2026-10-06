"""attribution.py — 自因/他因归因回路

把每个显著状态变化归因为 self（我做的事）或 other（外部事件）。
"自我能动感"的可测代理：滚动窗口内 self-caused 变化占比。
P0 中 self 类来源：探索行动（无聊驱动的内生行为）。
"""
import json
import os
from collections import deque

ATTR_PATH = os.path.join(os.path.dirname(__file__), os.environ.get("STATE_DIR", "state"), "attribution.json")


class Attribution:
    def __init__(self, window=500):
        self.records = deque(maxlen=window)

    def record(self, sim_time, cause, source, effect):
        """cause: 'self' | 'other'；effect: 简短描述。全量追加落盘（E4 分析用）。"""
        rec = {
            "t": round(sim_time, 2),
            "cause": cause,
            "source": source,
            "effect": effect,
        }
        self.records.append(rec)
        os.makedirs(os.path.dirname(ATTR_PATH), exist_ok=True)
        with open(ATTR_PATH.replace(".json", ".jsonl"), "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def self_ratio(self):
        if not self.records:
            return None
        n_self = sum(1 for r in self.records if r["cause"] == "self")
        return n_self / len(self.records)

    def snapshot(self):
        return {
            "self_ratio_rolling": self.self_ratio(),
            "n_records": len(self.records),
            "recent": list(self.records)[-20:],
        }

    def save(self):
        os.makedirs(os.path.dirname(ATTR_PATH), exist_ok=True)
        with open(ATTR_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)

    def load(self):
        if not os.path.exists(ATTR_PATH):
            return False
        with open(ATTR_PATH) as f:
            d = json.load(f)
        self.records.clear()
        for r in d.get("recent", []):
            self.records.append(r)
        return True
