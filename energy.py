"""energy.py — 匮乏身体：每日能量预算

思考有成本。能量按天配给，被动消耗与唤醒度成正比，探索行动额外扣费。
耗尽 → 低功率模式（tick 变慢、唤醒被压低），次日唤醒时补满。
这是"欲望"的物理载体：预算有限，必须在'现在做'和'留着'之间取舍。
"""
import json
import os

ENERGY_PATH = os.path.join(os.path.dirname(__file__), os.environ.get("STATE_DIR", "state"), "energy.json")


class Energy:
    def __init__(self, config):
        e = config["energy"]
        self.budget = e["daily_budget"]
        self.passive = e["passive_drain_per_hour_base"]
        self.arousal_factor = e["drain_arousal_factor"]
        self.explore_cost = e["exploration_cost"]
        self.low_power_frac = e["low_power_fraction"]
        self.level = self.budget
        self.low_power = False

    def step(self, dt_hours, arousal):
        drain = (self.passive + self.arousal_factor * float(arousal) * self.passive) * dt_hours
        self.level = max(0.0, self.level - drain)
        self.low_power = bool(self.level < self.budget * self.low_power_frac)

    def can_afford(self, cost):
        return self.level >= cost

    def spend(self, cost):
        if not self.can_afford(cost):
            return False
        self.level -= cost
        return True

    def refill(self):
        self.level = self.budget

    def snapshot(self):
        lvl = float(self.level)
        return {
            "level": round(lvl, 3),
            "budget": self.budget,
            "fraction": round(lvl / self.budget, 4),
            "low_power": self.low_power,
        }

    def save(self):
        os.makedirs(os.path.dirname(ENERGY_PATH), exist_ok=True)
        with open(ENERGY_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)

    def load(self):
        if not os.path.exists(ENERGY_PATH):
            return False
        with open(ENERGY_PATH) as f:
            d = json.load(f)
        self.level = float(d.get("level", self.budget))
        self.low_power = bool(d.get("low_power", False))
        return True
