"""predictor.py — 事件预测器（婴儿期的"世界规律学习"）

在线学习事件出现时刻的小时分布（拉普拉斯平滑的直方图），
惊奇 = -log2 p(事件所在小时)。婴儿期出口判据：惊奇运行均值收敛。
"""
import json
import math
import os

PREDICTOR_PATH = os.path.join(os.path.dirname(__file__), os.environ.get("STATE_DIR", "state"), "predictor.json")


class EventPredictor:
    def __init__(self, config, rng):
        p = config["predictor"]
        self.n_bins = p["hour_bins"]
        self.window = p["surprise_window"]
        self.eps = p["convergence_epsilon"]
        self.max_surprise = p["convergence_max_surprise_bits"]
        self.rng = rng
        self.counts = [1.0] * self.n_bins  # 拉普拉斯先验
        self.total = float(self.n_bins)
        self.surprises = []  # 最近 window 条惊奇值
        # 优化：增量维护最近 window / 2*window 之和，避免每 tick 对切片求和 O(window)
        self._wsum = 0.0     # Σ surprises[-window:]
        self._w2sum = 0.0    # Σ surprises[-2*window:]
        # ---- E4：动作-结果共变学习（传出副本/比较器的功能实现）----
        # 学习"我的动作之后是否更常出现照护者言语"——能动感的统计学基础
        self.act_window_s = 60.0      # 动作后计为"跟随"的窗口
        self.contingency_half_life = 432000.0   # 遗忘半衰期 = 5 仿真日
        self.last_act_t = None        # 最近一次自发动作（发声）
        self.t_act = 0.0              # （指数加权）处于动作窗口内的有效时长
        self.t_total = 0.0            # （指数加权）有效总时长
        self.speech_in_win = 0.0      # （指数加权）窗口内到达的照护者言语
        self.speech_out_win = 0.0     # （指数加权）窗口外到达的照护者言语

    def observe(self, sim_hour):
        h = int(sim_hour) % self.n_bins
        p = self.counts[h] / self.total
        surprise = -math.log2(max(p, 1e-9))
        self.counts[h] += 1.0
        self.total += 1.0
        self.surprises.append(surprise)
        s = self.surprises
        L = len(s)
        # 增量维护两个窗口和（在截断前更新，截断只移除 2w 之外的元素，不影响这两窗口）
        self._wsum += surprise
        if L > self.window:
            self._wsum -= s[L - self.window - 1]
        self._w2sum += surprise
        if L > self.window * 2:
            self._w2sum -= s[0]
            self.surprises = s[-self.window * 2:]
        return surprise

    # ============ E4：动作-结果共变（比较器） ============
    def note_self_action(self, sim_time):
        """自发动作发生（如发声）。开启 60s 跟随窗口。"""
        self.last_act_t = sim_time

    def advance_contingency_clock(self, dt_s, sim_time):
        """每 tick 累计窗口内/外时长。指数遗忘（半衰期 5 仿真日）：
        共变估计反映'最近的世界'——消退可发生，旧证据不永久主导。"""
        decay = 0.5 ** (dt_s / self.contingency_half_life)
        self.t_total = self.t_total * decay + dt_s
        if (self.last_act_t is not None
                and sim_time - self.last_act_t < self.act_window_s):
            self.t_act = self.t_act * decay + dt_s
        else:
            self.t_act *= decay
        self.speech_in_win *= decay
        self.speech_out_win *= decay

    def note_speech(self, sim_time):
        """照护者言语到达。按是否处于动作跟随窗口分别计数。"""
        in_win = (self.last_act_t is not None
                  and sim_time - self.last_act_t < self.act_window_s)
        if in_win:
            self.speech_in_win += 1.0
        else:
            self.speech_out_win += 1.0
        return in_win

    def contingency(self):
        """C = 窗口内言语速率 / 窗口外言语速率（近期指数加权）。
        C≈1 无共变；C>1 我的动作有效。样本不足（有效窗口时长 < 60s）返回 None。"""
        if self.t_act <= 60.0 or self.t_total - self.t_act <= 600.0:
            return None
        r_in = self.speech_in_win / self.t_act
        r_out = self.speech_out_win / (self.t_total - self.t_act)
        if r_out <= 0:
            return None
        return r_in / r_out

    def efficacy(self):
        """功效 = 由自身动作导致的窗口内言语占比（(C-1)/C，截到 0..0.8）。
        能动归因的门控：跟随言语仅当功效超阈值才记 self。"""
        c = self.contingency()
        if c is None or c <= 1.0:
            return 0.0
        return min(0.8, (c - 1.0) / c)

    def expected_prob(self, sim_hour):
        h = int(sim_hour) % self.n_bins
        return self.counts[h] / self.total

    def running_mean(self, n=None):
        n = n or self.window
        if len(self.surprises) < n:
            return None
        if n == self.window:                 # 优化：增量窗口和 O(1)
            return self._wsum / self.window
        return sum(self.surprises[-n:]) / n

    def converged(self):
        """出口判据：最近窗口均值与前一段均值之差 < eps，且绝对值低于阈值。"""
        if len(self.surprises) < self.window * 2:
            return False
        w = self.window
        recent = self._wsum / w               # 优化：增量窗口和 O(1)
        prev = (self._w2sum - self._wsum) / w
        return abs(recent - prev) < self.eps and recent < self.max_surprise

    def snapshot(self):
        return {
            "counts": [round(c, 1) for c in self.counts],
            "n_observations": int(self.total - self.n_bins),
            "surprise_running_mean": self.running_mean(),
            "converged": self.converged(),
            "surprises_tail": [round(s, 3) for s in self.surprises[-self.window * 2:]],
            # E4 共变学习状态
            "contingency": (round(self.contingency(), 3)
                            if self.contingency() is not None else None),
            "efficacy": round(self.efficacy(), 3),
            "t_act": round(self.t_act, 1),
            "t_total": round(self.t_total, 1),
            "speech_in_win": round(self.speech_in_win, 1),
            "speech_out_win": round(self.speech_out_win, 1),
        }

    def load(self):
        """从 state/predictor.json 恢复（重启续跑）。"""
        if not os.path.exists(PREDICTOR_PATH):
            return False
        with open(PREDICTOR_PATH) as f:
            d = json.load(f)
        self.counts = [float(c) for c in d.get("counts", self.counts)]
        self.total = sum(self.counts)
        self.surprises = [float(s) for s in d.get("surprises_tail", [])]
        self._wsum = sum(self.surprises[-self.window:])   # 优化：恢复增量窗口和
        self._w2sum = sum(self.surprises)
        # E4 共变计数（旧格式缺省为 0）
        self.t_act = float(d.get("t_act", 0.0))
        self.t_total = float(d.get("t_total", 0.0))
        self.speech_in_win = int(d.get("speech_in_win", 0))
        self.speech_out_win = int(d.get("speech_out_win", 0))
        self.last_act_t = None
        return True

    def save(self):
        os.makedirs(os.path.dirname(PREDICTOR_PATH), exist_ok=True)
        with open(PREDICTOR_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)
