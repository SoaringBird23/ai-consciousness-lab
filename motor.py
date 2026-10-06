"""motor.py — 动作通道（P4/P4b）

设计原则（继承 vocal.py：给肌肉，不给目标）：
- 三个中性原语 p0/p1/p2（正向移动 / 反向移动 / 不动）。无方向项、无效价项。
- 动作选择 = 状态绑定记忆上的竞争（与语言层检索同构），不是规则。
- 有代价：每次"移动"消耗能量（停驻免费）——形成"动 vs 省"的取舍。
- 有后果：它改变位置 → 感知到的场强改变 → 回灌状态（闭环）。

两个学习信号（实验因子 motor.temporal）：
- False（P4）：瞬时空间梯度  outcome = field(新位置) − field(旧位置)，同一 tick 内读取。
  学到的是"沿空间梯度爬升"，无时间、无世界模型 → 无法区分自因/世界因。
- True（P4b）：时间化 + 自因分离。
  · 世界模型 fwd[level_bin, trend_bin]：只从"停驻"试次学，估计"我不动时世界怎么变"
  · 后果在动作区间上测：actual_Δ = f(t+Δ) − f(t)
  · 自因分量 self_caused = actual_Δ − fwd（我的动作超出世界自身演变的那部分）
  · q 只在 self_caused 上更新 ⇒ 选择的是"我的动作额外带来什么"

零硬编码：不存在"若场强下降则反向"之类规则；策略只能从后果中学出。
"""
import json
import os

STATE_PATH = os.path.join(os.path.dirname(__file__),
                          os.environ.get("STATE_DIR", "state"), "motor.json")
LOG_PATH = os.path.join(os.path.dirname(__file__),
                        os.environ.get("STATE_DIR", "state"), "actions.jsonl")


class Motor:
    def __init__(self, config, rng):
        m = config.get("motor", {})
        self.enabled = m.get("enabled", False)          # 默认关：显式开启
        self.temporal = m.get("temporal", False)        # P4b 开关
        self.rng = rng
        self.move_step = float(m.get("move_step", 0.08))
        # P4c：新增写痕原语 p3/p4（在当前位置写正/负痕迹，不改变位置）
        self.marks_enabled = bool(m.get("marks_enabled", False))
        self.mark_gain = float(m.get("mark_gain", 0.05))
        if self.marks_enabled:
            self.deltas = [self.move_step, -self.move_step, 0.0, 0.0, 0.0]
            self.marks = [0.0, 0.0, 0.0, self.mark_gain, -self.mark_gain]
            self.names = ["p0", "p1", "p2", "p3", "p4"]
        else:
            self.deltas = [self.move_step, -self.move_step, 0.0]
            self.marks = [0.0, 0.0, 0.0]
            self.names = ["p0", "p1", "p2"]
        self.n_actions = len(self.names)
        self.cost = float(m.get("energy_cost", 0.02))
        self.mark_cost = float(m.get("mark_cost", 0.02))
        self.lr = float(m.get("learning_rate", 0.08))
        self.explore = float(m.get("exploration", 0.15))
        self.n_level_bins = int(m.get("level_bins", 5))
        self.n_trend_bins = int(m.get("trend_bins", 3))
        self.action_interval = float(m.get("action_interval_seconds", 60.0))
        self.fwd_alpha = float(m.get("fwd_alpha", 0.05))   # 世界模型学习率
        self._last_t = 0.0
        self._prev_action = -1          # -1 = 尚无前动作（初始）
        self._prev_field = None
        self.q = {}                     # (prev_action, lb, tb) -> [q0, q1, q2]
        self.fwd = {}                   # (lb, tb) -> 世界漂移 EMA（仅停驻试次更新）
        self.pending = None             # P4b：待结算的上一次动作
        self.n_act = 0
        self.n_moves = 0
        self.n_marks = 0                # P4c：写痕次数
        self.n_self_pos = 0             # self_caused > 0 的次数
        self._last_error = None

    # ---- 分档 ----
    def bins(self, field, trend):
        lb = min(self.n_level_bins - 1, max(0, int(field * self.n_level_bins)))
        tb = min(self.n_trend_bins - 1, max(0, int((trend + 0.5) * self.n_trend_bins)))
        return lb, tb

    def _sig(self, field, trend):
        lb, tb = self.bins(field, trend)
        return (self._prev_action, lb, tb)

    def _q(self, sig):
        if sig not in self.q:
            self.q[sig] = [0.0] * self.n_actions
        return self.q[sig]

    def due(self, sim_time):
        return self.enabled and (sim_time - self._last_t >= self.action_interval)

    def mark_acted(self, sim_time):
        self._last_t = sim_time

    def trend(self, field):
        """自上次动作以来的场强变化（含世界自演化 + 上次动作效应）。"""
        if self._prev_field is None:
            return 0.0
        return field - self._prev_field

    def note_field(self, field):
        self._prev_field = field

    def select(self, field, trend):
        """在当前签名上做 ε-贪心竞争。返回 (签名, 原语下标)。"""
        sig = self._sig(field, trend)
        q = self._q(sig)
        if self.rng.random() < self.explore:
            idx = int(self.rng.randint(0, self.n_actions))
        else:
            idx = int(max(range(self.n_actions), key=lambda i: q[i]))
        return sig, idx

    # ---- P4 原机制：瞬时空间梯度 ----
    def learn_instant(self, sig, idx, outcome):
        q = self._q(sig)
        q[idx] += self.lr * (outcome - q[idx])
        self._prev_action = idx

    # ---- P4b：时间化 + 自因分离 ----
    def set_pending(self, sig, idx, f_before, ltb):
        self.pending = {"sig": sig, "idx": idx, "f_before": f_before, "ltb": ltb}

    def resolve(self, field_now):
        """在下一个动作时刻结算上一次动作。
        返回 {actual, world_drift, self_caused, ...} 或 None（无待结算动作）。"""
        p = self.pending
        if p is None:
            return None
        self.pending = None
        actual = field_now - p["f_before"]
        ltb = p["ltb"]
        if p["idx"] == 2:
            # 停驻 = 纯世界漂移 → 更新世界模型（不被动作污染）
            old = self.fwd.get(ltb, 0.0)
            self.fwd[ltb] = old + self.fwd_alpha * (actual - old)
            world_drift = old
        else:
            world_drift = self.fwd.get(ltb, 0.0)
        self_caused = actual - world_drift
        q = self._q(p["sig"])
        q[p["idx"]] += self.lr * (self_caused - q[p["idx"]])
        self._prev_action = p["idx"]
        if self_caused > 0.0:
            self.n_self_pos += 1
        return {"sig": p["sig"], "action": self.names[p["idx"]],
                "f_before": p["f_before"], "f_after": field_now,
                "actual": actual, "world_drift": world_drift,
                "self_caused": self_caused}

    # ---- 记录 ----
    def log_record(self, sim_time, day, rec, pos, energy):
        try:
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
            with open(LOG_PATH, "a") as f:
                f.write(json.dumps({
                    "t": round(sim_time, 1), "day": day,
                    "sig": list(rec["sig"]), "action": rec["action"],
                    "field_before": round(rec["f_before"], 4),
                    "field_after": round(rec["f_after"], 4),
                    "outcome": round(rec["actual"], 5),
                    "world_drift": round(rec["world_drift"], 5),
                    "self_caused": round(rec["self_caused"], 5),
                    "pos": round(pos, 4), "energy": round(energy, 2),
                }, ensure_ascii=False) + "\n")
        except OSError as e:
            self._last_error = str(e)

    # ---- 持久化 ----
    def snapshot(self):
        return {"enabled": self.enabled, "temporal": self.temporal,
                "marks_enabled": self.marks_enabled, "n_actions": self.n_actions,
                "n_act": self.n_act, "n_moves": self.n_moves,
                "n_marks": self.n_marks,
                "n_self_pos": self.n_self_pos,
                "prev_action": self._prev_action, "prev_field": self._prev_field,
                "pending": self.pending,
                "n_sigs": len(self.q), "n_fwd": len(self.fwd),
                "q": [[list(k), v] for k, v in self.q.items()],
                "fwd": [[list(k), v] for k, v in self.fwd.items()],
                "last_error": self._last_error}

    def save(self):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)

    def load(self):
        if not os.path.exists(STATE_PATH):
            return False
        with open(STATE_PATH) as f:
            d = json.load(f)
        self.n_act = int(d.get("n_act", 0))
        self.n_moves = int(d.get("n_moves", 0))
        self.n_marks = int(d.get("n_marks", 0))
        self.n_self_pos = int(d.get("n_self_pos", 0))
        self._prev_action = int(d.get("prev_action", -1))
        self._prev_field = d.get("prev_field")
        self.pending = d.get("pending")
        if self.pending and "sig" in self.pending:
            self.pending["sig"] = tuple(self.pending["sig"])
            self.pending["ltb"] = tuple(self.pending["ltb"])
        self.q = {}
        for k, v in d.get("q", []):
            self.q[tuple(k)] = list(v)
        self.fwd = {}
        for k, v in d.get("fwd", []):
            self.fwd[tuple(k)] = float(v)
        return True
