"""memory.py — 记忆系统（P1）

三层记忆：
- 情景记忆（episodic）：显著事件 + 当时的状态快照，原始记录，不删除
- 语义记忆（semantic）：睡眠固化时从情景记忆压缩出的统计规律
- 自传体记忆（autobiographical）：关于"我经历过什么"的事件序列（P2 才有自我叙事，这里只留骨架）

睡眠固化：入睡时把自上次固化以来的情景记忆压缩，更新语义统计，
同时触发时间知觉探针 E1 的素材（供后续调用）。
"""
import json
import os
from collections import deque

STATE_DIR = os.environ.get("STATE_DIR", "state")
MEMORY_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "memory.json")
EPISODIC_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "episodic.jsonl")


class Memory:
    def __init__(self, config):
        self.episodic = deque(maxlen=2000)  # 情景记忆（滚动窗口）
        self.semantic = {
            "event_hour_dist": [1.0] * 24,   # 事件小时分布（拉普拉斯平滑）
            "explore_count": 0,
            "n_episodes_consolidated": 0,
            "last_consolidate_sim_time": None,
        }
        self._last_consolidate_idx = 0  # 已固化的情景记忆条数

    def record_episode(self, sim_time, kind, detail, state_snapshot):
        """记录一条情景记忆。kind: 'event'|'explore'|'focus'|'probe'。"""
        self.episodic.append({
            "t": round(sim_time, 1),
            "kind": kind,
            "detail": detail,
            "s": [round(float(v), 3) for v in state_snapshot],
        })

    def consolidate(self, sim_time, logger=None):
        """睡眠固化：把自上次以来的情景记忆压缩成语义统计。"""
        new_episodes = list(self.episodic)[self._last_consolidate_idx:]
        if not new_episodes:
            return
        n = 0
        for ep in new_episodes:
            hour = int((ep["t"] / 3600.0) % 24)
            self.semantic["event_hour_dist"][hour] += 1.0
            if ep["kind"] == "explore":
                self.semantic["explore_count"] += 1
            n += 1
        self.semantic["n_episodes_consolidated"] += n
        self.semantic["last_consolidate_sim_time"] = sim_time
        self._last_consolidate_idx = len(self.episodic)
        if logger:
            logger.info(f"[memory] 睡眠固化 {n} 条情景记忆，累计 {self.semantic['n_episodes_consolidated']}")

    def snapshot(self):
        return {
            "episodic_count": len(self.episodic),
            "semantic": {
                "explore_count": self.semantic["explore_count"],
                "n_consolidated": self.semantic["n_episodes_consolidated"],
                "hour_dist_top3": sorted(
                    enumerate(self.semantic["event_hour_dist"]),
                    key=lambda x: -x[1])[:3],
            },
        }

    def load(self):
        if not os.path.exists(MEMORY_PATH):
            return False
        with open(MEMORY_PATH) as f:
            d = json.load(f)
        self.semantic = d.get("semantic", self.semantic)
        self._last_consolidate_idx = d.get("last_consolidate_idx", 0)
        # 情景记忆从 jsonl 恢复（只恢复最近 2000 条）
        if os.path.exists(EPISODIC_PATH):
            with open(EPISODIC_PATH) as f:
                lines = f.readlines()[-2000:]
            self.episodic.clear()
            for line in lines:
                try:
                    self.episodic.append(json.loads(line))
                except Exception:
                    pass
            self._last_consolidate_idx = min(self._last_consolidate_idx, len(self.episodic))
        return True

    def save(self):
        os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
        # 情景记忆全量覆写
        with open(EPISODIC_PATH, "w") as f:
            for ep in self.episodic:
                f.write(json.dumps(ep, ensure_ascii=False) + "\n")
        with open(MEMORY_PATH, "w") as f:
            json.dump({
                "episodic_count": len(self.episodic),
                "semantic": self.semantic,
                "last_consolidate_idx": self._last_consolidate_idx,
            }, f, ensure_ascii=False, indent=2)
