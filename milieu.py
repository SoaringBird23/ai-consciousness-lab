"""milieu.py — 环境（P4 行动环 / P4c 痕迹层）

设计原则（与 vocal.py 同源：给肌肉，不给目标）：
- 世界有自己的动力学（各"源"按各自周期/相位独立振荡），与它无关——
  这是"世界"，不是它的延伸。
- P4c 新增"痕迹层"：它可以在当前格写入痕迹（正/负），痕迹慢衰减。
  这是世界状态里**只可能来自它**的那一部分——没有任何自然过程会写痕迹。
- 世界不告诉它该去哪、该不该写：场强的含义必须从后果中涌现。

变量对外一律中性：pos（位置）/ sources[i].level（源强度）/ trace（痕迹），无任何语义命名。
"""
import json
import math
import os

STATE_PATH = os.path.join(os.path.dirname(__file__),
                          os.environ.get("STATE_DIR", "state"), "milieu.json")


class Milieu:
    def __init__(self, config):
        m = config.get("milieu", {})
        self.n = int(m.get("n_sources", 3))
        self.sigma = float(m.get("sigma", 0.12))
        # 源位置固定（均匀分布）；强度按各自周期/相位独立振荡
        self.positions = [(i + 0.5) / self.n for i in range(self.n)]
        periods = [float(p) for p in m.get("periods_hours", [3.0, 5.0, 7.0])]
        phases = [float(p) for p in m.get("phases", [0.0, 0.3, 0.7])]
        while len(periods) < self.n:
            periods.append(4.0 + len(periods))
        while len(phases) < self.n:
            phases.append(0.5)
        self.periods = periods[:self.n]
        self.phases = phases[:self.n]
        self.t = float(m.get("start_t_hours", 0.0))   # 世界自己的时钟（仿真小时）
        self.pos = float(m.get("start_position", 0.5))
        self.move_step = float(m.get("move_step", 0.08))
        # ---- P4c 痕迹层 ----
        self.trace_on = bool(m.get("trace_enabled", False))
        self.n_tr = int(m.get("trace_bins", 36))
        self.trace = [0.0] * self.n_tr
        self.trace_gain = float(m.get("trace_gain", 0.03))      # 单次写入量
        self.trace_weight = float(m.get("trace_weight", 0.5))   # 痕迹对场强的贡献权重
        self.trace_decay = float(m.get("trace_decay_per_hour", 0.5))
        self.trace_cap = float(m.get("trace_cap", 10.0))

    def level_of(self, i):
        """第 i 个源的当前强度（0..1）：独立正弦振荡。"""
        ph = self.t / self.periods[i] + self.phases[i]
        return 0.5 + 0.5 * math.sin(2 * math.pi * ph)

    def _weights(self, x):
        return [math.exp(-(min(abs(x - p), 1.0 - abs(x - p)) ** 2)
                         / (2 * self.sigma * self.sigma)) for p in self.positions]

    def _bin(self, x):
        return int(x * self.n_tr) % self.n_tr

    def trace_at(self, x):
        return self.trace[self._bin(x)]

    def write_trace(self, x, amount):
        """在当前格写入痕迹（+/-）。这是世界状态里只可能来自它的成分。
        不设硬上限：无限幅则每次写入都有边际效果（配合指数衰减不会失控）。"""
        i = self._bin(x)
        self.trace[i] = max(-100.0, min(100.0, self.trace[i] + amount))

    def field_at(self, x):
        """位置 x 处感知到的场强 = 源的振荡（世界底色）+ 痕迹（它写下的部分）。
        不设上限：痕迹可以把它所在处抬到源之上——这正是"它留下的印记"。"""
        w = self._weights(x)
        norm = sum(w)
        src = sum(self.level_of(i) * w[i] for i in range(self.n)) / norm if norm > 0 else 0.0
        tr = self.trace_at(x) if self.trace_on else 0.0
        return max(-1.0, min(4.0, src + self.trace_weight * tr))

    @property
    def field(self):
        return self.field_at(self.pos)

    @property
    def trace_total(self):
        return sum(self.trace)

    def move(self, delta):
        self.pos = (self.pos + delta) % 1.0

    def step(self, dt_hours):
        self.t += dt_hours
        if self.trace_on and self.trace_decay > 0.0:
            # 指数衰减：写入永远保留边际效果（无饱和），存量收敛到 写入速率×写入量/衰减率
            f = math.exp(-self.trace_decay * dt_hours)
            for i, v in enumerate(self.trace):
                if v:
                    self.trace[i] = v * f

    def snapshot(self):
        return {"t": round(self.t, 4), "pos": round(self.pos, 5),
                "field": round(self.field, 4),
                "levels": [round(self.level_of(i), 4) for i in range(self.n)],
                "positions": [round(p, 4) for p in self.positions],
                "periods": self.periods, "n_sources": self.n,
                "trace_on": self.trace_on,
                "trace_total": round(self.trace_total, 4),
                "trace_nonzero": sum(1 for v in self.trace if abs(v) > 1e-6),
                "trace": [round(v, 4) for v in self.trace] if self.trace_on else []}

    def save(self):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)

    def load(self):
        if not os.path.exists(STATE_PATH):
            return False
        with open(STATE_PATH) as f:
            d = json.load(f)
        self.t = float(d.get("t", self.t))
        self.pos = float(d.get("pos", self.pos))
        tr = d.get("trace") or []
        if tr and len(tr) == self.n_tr:
            self.trace = [float(v) for v in tr]
        return True
