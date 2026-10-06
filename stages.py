"""stages.py — 发展阶段状态机

不许跳级。每个阶段有最短时长与硬判据，判据不过则延长（有上限）。
阶段 1（婴儿期）：无语言，纯感觉统计。出口 = 预测器收敛 + 最短天数。
阶段 2（feeling）：记忆 + 意识焦点 + 时间探针上线。
  出口 = 节能策略自发形成（低能量时主动减少探索）。
"""
import json
import os

STAGE_PATH = os.path.join(os.path.dirname(__file__), os.environ.get("STATE_DIR", "state"), "stage.json")

STAGES = {
    "1_infancy": {
        "name": "婴儿期",
        "language_locked": True,
        "min_days": None,
        "exit": "predictor_converged",
    },
    "2_feeling": {
        "name": "感受期",
        "language_locked": True,
        "min_days": 2,
        "max_days": 14,
        "exit": "energy_conservation",
    },
    "3_mirror": {
        "name": "镜像期",
        "language_locked": False,
        "min_days": 3,
        "max_days": 21,
        "exit": "self_model_formed",
    },
    "awaiting_P1": {"name": "等待 P1 启动", "language_locked": True},
    "awaiting_P2": {"name": "等待 P2 启动", "language_locked": True},
    "awaiting_P3": {"name": "等待 P3 启动", "language_locked": False},
}


class StageMachine:
    def __init__(self, config):
        s = config.get("stage", {})
        self.min_days = s.get("stage1_min_days", 3)
        self.max_days = s.get("stage1_max_days", 14)
        self.stage2_min_days = s.get("stage2_min_days", 2)
        self.stage2_max_days = s.get("stage2_max_days", 14)
        self.stage3_min_days = s.get("stage3_min_days", 3)
        self.stage3_max_days = s.get("stage3_max_days", 21)
        self.low_power_frac = config.get("energy", {}).get("low_power_fraction", 0.2)
        self.stage = "1_infancy"
        self.entered_at = None
        self.exit_reason = None
        self.explore_at_low_energy = 0
        self.explore_at_high_energy = 0
        # 阶段 3 用：自我模型是否已形成（非 null 且版本 >= 3）
        self.self_model_formed = False

    def start(self, sim_time):
        self.entered_at = sim_time

    def days_elapsed(self, sim_time):
        if self.entered_at is None:
            return 0.0
        return (sim_time - self.entered_at) / 86400.0

    def record_explore(self, energy_fraction):
        """阶段 2 用：记录一次探索发生时的能量水平。"""
        if energy_fraction < self.low_power_frac:
            self.explore_at_low_energy += 1
        else:
            self.explore_at_high_energy += 1

    def check_exit(self, sim_time, predictor_converged, energy_fraction=None, logger=None,
                   self_model_version=0, self_model_desc=None):
        """返回 True 表示当前阶段完成。"""
        days = self.days_elapsed(sim_time)

        if self.stage == "1_infancy":
            if days >= self.min_days and predictor_converged:
                self.exit_reason = "predictor_converged_after_min_days"
                self.stage = "2_feeling"
                self.entered_at = sim_time
                if logger:
                    logger.info(f"[stage] 婴儿期完成：{days:.2f} 天 → 进入感受期")
                return True
            if days >= self.max_days:
                self.exit_reason = "max_days_forced_exit"
                self.stage = "2_feeling"
                self.entered_at = sim_time
                if logger:
                    logger.warning(f"[stage] 婴儿期达上限，强制进入感受期")
                return True

        if self.stage == "2_feeling":
            total = self.explore_at_low_energy + self.explore_at_high_energy
            if days >= self.stage2_min_days and total >= 5:
                low_frac = self.explore_at_low_energy / total
                if low_frac < 0.15:
                    self.exit_reason = "energy_conservation_formed"
                    self.stage = "3_mirror"
                    self.entered_at = sim_time
                    if logger:
                        logger.info(f"[stage] 感受期完成：节能策略形成 → 进入镜像期")
                    return True
            if days >= self.stage2_max_days:
                self.exit_reason = "max_days_forced_exit"
                self.stage = "3_mirror"
                self.entered_at = sim_time
                if logger:
                    logger.warning(f"[stage] 感受期达上限，强制进入镜像期")
                return True

        if self.stage == "3_mirror":
            # 出口判据：自我模型形成（非 null 且版本 >= 3）+ 最短天数
            if days >= self.stage3_min_days and self_model_version >= 3 and self_model_desc:
                self.exit_reason = "self_model_formed"
                self.self_model_formed = True
                self.stage = "awaiting_P3"
                if logger:
                    logger.info(f"[stage] 镜像期完成：自我模型形成（版本 {self_model_version}）")
                return True
            if days >= self.stage3_max_days:
                self.exit_reason = "max_days_forced_exit"
                self.stage = "awaiting_P3"
                if logger:
                    logger.warning(f"[stage] 镜像期达上限，强制结束")
                return True

        return False

    def snapshot(self, sim_time):
        return {
            "stage": self.stage,
            "language_locked": STAGES.get(self.stage, {}).get("language_locked", True),
            "days_elapsed": round(self.days_elapsed(sim_time), 3),
            "exit_reason": self.exit_reason,
            "entered_at": self.entered_at,
            "explore_low_energy": self.explore_at_low_energy,
            "explore_high_energy": self.explore_at_high_energy,
            "self_model_formed": self.self_model_formed,
        }

    def load(self, sim_time):
        if not os.path.exists(STAGE_PATH):
            return False
        with open(STAGE_PATH) as f:
            d = json.load(f)
        self.stage = d.get("stage", self.stage)
        self.exit_reason = d.get("exit_reason")
        self.entered_at = d.get("entered_at")
        self.explore_at_low_energy = d.get("explore_low_energy", 0)
        self.explore_at_high_energy = d.get("explore_high_energy", 0)
        self.self_model_formed = d.get("self_model_formed", False)
        if self.entered_at is None:
            self.entered_at = 8.0 * 3600.0
        return True

    def save(self, sim_time):
        os.makedirs(os.path.dirname(STAGE_PATH), exist_ok=True)
        with open(STAGE_PATH, "w") as f:
            json.dump(self.snapshot(sim_time), f, ensure_ascii=False, indent=2)
