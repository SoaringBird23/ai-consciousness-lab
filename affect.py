"""affect.py — 痛 / 乐（P5：把"匮乏"与"满足"显式化为两个内部状态）

设计纪律（与项目既有原则一致）：

1. **零外部奖赏**。痛与乐不是实验者发下的分数，而是由候选体自身的状态
   变量与能量预算算出的内部量。环境通过改变它的处境（剥夺/丰富）间接
   影响它们，而不是直接喂一个 reward 标量。这是"活着"与"讨分"的分界。
2. **积分量，不是瞬时读数**。若直接令 distress=f(能量, s4) 就只是现有变量
   的改名，测不出新东西。两者各自带时间常数、有惯性。
3. **负性偏差**：痛升得快、落得慢；乐起得慢、退得快。
4. **默认关闭**。affect.enabled=false 时 step() 直接返回、反馈增益为 0，
   系统行为与改动前一致——在跑的线不受影响。

状态索引（中性代号，见 config.variable_mapping）：
    s[0]=s1 唤醒  s[1]=s2 效价  s[2]=s3 疲劳  s[3]=s4 紧张
    s[4]=s5 注意  s[5]=s6 记忆  s[6]=s7 预测误差  s[7]=s8 无聊
睡眠压力不在状态向量里，由调用方单独传入。

反馈通道（唯一）由 config.affect.k_affect 控制，默认 0.0：
    痛高 → s4 紧张抬升、s8 无聊被压缩（注意力收窄）
    乐高 → s4 松弛
k_affect=0 时只记录不接线，用作 H2 的"记录但断开"对照臂。
"""
import json
import os

STATE_DIR = os.environ.get("STATE_DIR", "state")
AFFECT_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "affect.json")


def _clip(x, lo=0.0, hi=1.0):
    return lo if x < lo else (hi if x > hi else x)


class Affect:
    def __init__(self, config):
        a = config.get("affect", {})
        self.enabled = bool(a.get("enabled", False))
        # ---- 痛：匮乏 + 张紧 + 睡眠压力 ----
        self.w_energy = float(a.get("w_energy", 0.5))
        self.w_tension = float(a.get("w_tension", 0.3))
        self.w_sleep = float(a.get("w_sleep", 0.2))
        self.tau_up = float(a.get("tau_up_hours", 0.5))       # 升：快
        self.tau_down = float(a.get("tau_down_hours", 6.0))   # 落：慢
        # ---- 乐：能量充裕 + 不无聊 + 不紧张 ----
        self.e_w_energy = float(a.get("ease_w_energy", 0.4))
        self.e_w_boredom = float(a.get("ease_w_boredom", 0.35))
        self.e_w_calm = float(a.get("ease_w_calm", 0.25))
        self.e_tau_up = float(a.get("ease_tau_up_hours", 3.0))      # 起：慢
        self.e_tau_down = float(a.get("ease_tau_down_hours", 0.75))  # 退：快
        # ---- 反馈增益（0 = 只记录不接线）----
        self.k_affect = float(a.get("k_affect", 0.0))
        # 状态
        self.distress = 0.0
        self.ease = 0.0
        self.drive_distress = 0.0
        self.drive_ease = 0.0
        self.n_steps = 0

    # ---- 逐步积分 ----
    def step(self, dt_hours, s, energy_frac, sleep_pressure, asleep):
        """推进一个 tick。睡中不更新（痛与乐都暂停——睡眠是复位期）。"""
        if not self.enabled or asleep:
            return
        d_drive = _clip(self.w_energy * (1.0 - float(energy_frac))
                        + self.w_tension * float(s[3])
                        + self.w_sleep * float(sleep_pressure))
        e_drive = _clip(self.e_w_energy * float(energy_frac)
                        + self.e_w_boredom * (1.0 - float(s[7]))
                        + self.e_w_calm * (1.0 - float(s[3])))

        # 痛：升快落慢
        tau = self.tau_up if d_drive > self.distress else self.tau_down
        self.distress = _clip(self.distress + (d_drive - self.distress) * dt_hours / tau)
        # 乐：起慢退快
        tau_e = self.e_tau_up if e_drive > self.ease else self.e_tau_down
        self.ease = _clip(self.ease + (e_drive - self.ease) * dt_hours / tau_e)

        self.drive_distress = round(d_drive, 4)
        self.drive_ease = round(e_drive, 4)
        self.n_steps += 1

    # ---- 反馈强度（供 background.receive_affect 使用）----
    def feedback(self):
        """返回 (痛偏置 d, 乐偏置 e)，各 0..1；未越过 0.5 的一侧为 0。"""
        if not self.enabled or self.k_affect == 0.0:
            return 0.0, 0.0
        d = max(0.0, self.distress - 0.5) * 2.0
        e = max(0.0, self.ease - 0.5) * 2.0
        return d, e

    def snapshot(self):
        return {
            "enabled": self.enabled,
            "distress": round(self.distress, 4),
            "ease": round(self.ease, 4),
            "drive_distress": self.drive_distress,
            "drive_ease": self.drive_ease,
            "k_affect": self.k_affect,
            "n_steps": self.n_steps,
        }

    def save(self):
        os.makedirs(os.path.dirname(AFFECT_PATH), exist_ok=True)
        with open(AFFECT_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)

    def load(self):
        if not os.path.exists(AFFECT_PATH):
            return False
        with open(AFFECT_PATH) as f:
            d = json.load(f)
        self.distress = float(d.get("distress", 0.0))
        self.ease = float(d.get("ease", 0.0))
        self.n_steps = int(d.get("n_steps", 0))
        return True
