"""world.py — 世界模型（P2）

维护对外部环境的理解。
从预测器 + 记忆固化中提取规律，形成对世界的模型。
输出 state/world_model.json
"""
import json
import os

STATE_DIR = os.environ.get("STATE_DIR", "state")
WORLD_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "world_model.json")


class WorldModel:
    def __init__(self, config):
        self.active_hours = []  # 推断的活跃时段
        self.event_rate_estimate = 0.0  # 事件率估计
        self.day_count = 0
        self.learned_patterns = []  # 学到的规律描述

    def update(self, predictor, memory_semantic, sim_time):
        """从预测器和记忆固化中提取世界规律。"""
        if not predictor.converged():
            return
        counts = predictor.counts
        total = sum(counts)
        if total == 0:
            return
        # 活跃时段：计数超过均值的小时
        mean = total / 24.0
        self.active_hours = [h for h, c in enumerate(counts) if c > mean * 1.2]
        # 事件率估计（每小时）
        self.event_rate_estimate = total / 24.0
        self.day_count = int(sim_time / 86400.0) + 1

        # 规律描述
        if self.active_hours:
            pattern = f"事件主要发生在 {self.active_hours[0]}:00-{self.active_hours[-1]}:00"
            if pattern not in self.learned_patterns:
                self.learned_patterns.append(pattern)

    def snapshot(self):
        return {
            "active_hours": self.active_hours,
            "event_rate_per_hour": round(self.event_rate_estimate, 2),
            "day_count": self.day_count,
            "learned_patterns": self.learned_patterns,
        }

    def load(self):
        if not os.path.exists(WORLD_PATH):
            return False
        with open(WORLD_PATH) as f:
            d = json.load(f)
        self.active_hours = d.get("active_hours", [])
        self.event_rate_estimate = d.get("event_rate_per_hour", 0.0)
        self.day_count = d.get("day_count", 0)
        self.learned_patterns = d.get("learned_patterns", [])
        return True

    def save(self):
        os.makedirs(os.path.dirname(WORLD_PATH), exist_ok=True)
        with open(WORLD_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)
