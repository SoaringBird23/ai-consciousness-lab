"""background.py — 背景层：连续状态演化（模式 B：外挂数值引擎）

明确声明（对应审查结论）：
- 本模块是 numpy 常微分方程积分引擎，不是任何模型内部的隐状态。
- "持续"来自本进程持续运行 + 状态持久化，不来自模型内在连续性。
- 变量对外只有中性代号 s1..s8；语义映射仅供人类观察者查阅（config.variable_mapping）。

动力学（双过程睡眠模型 + 情绪/注意 ODE，全部显式可审计）：
- 昼夜项 C(t)：24h 余弦，峰值 15:00
- 稳态项 H：清醒时线性上升，睡眠中指数衰减（Borbély 双过程模型）
- 睡眠/清醒切换：H 过阈值 + 时相门控，非固定时刻表
- s1..s8 的导数见 step() 内注释
"""
import json
import math
import os

import numpy as np

STATE_PATH = os.path.join(os.path.dirname(__file__), os.environ.get("STATE_DIR", "state"), "background_state.json")


def _clip(x, lo=0.0, hi=1.0):
    return lo if x < lo else (hi if x > hi else x)


class Background:
    def __init__(self, config, rng, sim_clock):
        self.cfg = config
        self.rng = rng
        self.clock = sim_clock  # 提供 sim_time()/sim_hour()/day_index()
        c = config["circadian"]
        o = config["ode"]
        self.c_peak = c["circadian_peak_hour"]
        self.h_rise = c["sleep_pressure_rise_per_hour_awake"]
        self.h_decay = c["sleep_pressure_decay_per_hour_asleep"]
        self.sleep_on = c["sleep_onset_threshold"]
        self.wake_thr = c["wake_threshold"]
        self.earliest_sleep = c["earliest_sleep_hour"]
        self.earliest_wake = c["earliest_wake_hour"]
        self.o = o
        # 探索阈值：默认 0.7，可由 config["behavior"]["explore_threshold"] 覆盖
        self.explore_threshold = 0.7
        if "behavior" in config and "explore_threshold" in config["behavior"]:
            self.explore_threshold = float(config["behavior"]["explore_threshold"])
        # R1–R3 回流量级阶梯：念头→状态 的耦合强度可配（默认即历史值 ±0.02 / +0.015）
        rf = config.get("reflow", {})
        self.reflow_s2 = float(rf.get("s2", 0.02))
        self.reflow_s5 = float(rf.get("s5", 0.015))
        self.reflow_thresh = float(rf.get("valence_threshold", 0.05))
        # 写回目标：默认 "s2" 保持原行为逐位一致。"s4" 把同一份情绪色彩写到紧张维度——
        # s4 被检索相似度消费（SIM_WEIGHTS 含 s4），而 s2 在系统里没有任何行为读取者
        # （审计见 experiments/prereg_R2.json）。此开关只为实验臂服务，不动默认值，
        # 以免改动正在运行的线。
        self.reflow_target = str(rf.get("target", "s2"))
        self.reflow_idx = 3 if self.reflow_target == "s4" else 1
        # MC0 计数：操纵检查必须验「通道是否真的开火」，不能只验「接线是否唯一」。
        self.reflow_fires = {"valence_neg": 0, "valence_pos": 0, "question": 0}

        # 状态向量（初始：清醒，中性）
        self.s = np.array([0.5, 0.0, 0.0, 0.1, 0.5, 0.0, 0.0, 0.0])  # s1..s8
        self.sleep_pressure = 0.0
        self.asleep = False
        self.surprise_bits = 0.0  # s7 由 predictor 外部注入
        self.event_flag = False    # 本 tick 是否有事件（触发 s6/s8 重置）

    # ---- 驱动项 ----
    def circadian_drive(self):
        hour = self.clock.sim_hour()
        return 0.5 * (1.0 + math.cos(2 * math.pi * (hour - self.c_peak) / 24.0))

    def _sleep_gate(self):
        """双过程模型：稳态压力 + 昼夜时相门控决定睡/醒。"""
        hour = self.clock.sim_hour()
        # 睡眠允许时相：21 点以后或凌晨 6 点前；唤醒允许时相：05–12 点
        sleep_phase_ok = hour >= self.earliest_sleep or hour < 6
        wake_phase_ok = self.earliest_wake <= hour < 12
        if not self.asleep:
            if self.sleep_pressure >= self.sleep_on and sleep_phase_ok:
                self.asleep = True
        else:
            if self.sleep_pressure <= self.wake_thr and wake_phase_ok:
                self.asleep = False

    # ---- 核心积分 ----
    def step(self, dt_hours, surprise_bits=0.0, event=False, ref_surprise=None):
        """推进一个 tick。dt_hours 为仿真小时数。
        ref_surprise：近期平均惊奇（来自预测器）。事件对无聊的缓解量由
        相对新异度门控——例行事件（惊奇≈近期均值）几乎不缓解无聊。"""
        o = self.o
        self.surprise_bits = surprise_bits
        self.event_flag = event
        self._sleep_gate()

        s1, s2, s3, s4, s5, s6, s7, s8 = self.s

        if self.asleep:
            # 睡眠：唤醒弛豫到低水平，疲劳与睡眠压力衰减，其余慢弛豫
            s1_t = (0.05 - s1) / 0.5
            s3_t = -s3 / 2.0                      # 疲劳清除（小时级）
            self.sleep_pressure -= self.h_decay * dt_hours * (0.5 + s3)
        else:
            target = _clip(0.15 + 0.8 * self.circadian_drive())
            s1_t = (target - s1) / 1.5            # 唤醒趋向昼夜目标（弛豫 1.5h）
            s3_t = 0.02 * s1                      # 疲劳随唤醒缓慢积累
            self.sleep_pressure += self.h_rise * dt_hours * (0.6 + s1)

        # s2 效价：慢弛豫到 0，低惊奇轻微正向，高惊奇负向
        s2_t = -s2 / o["s2_valence_relax_hours"] + 0.01 * (2.0 - surprise_bits) * dt_hours
        # s4 紧张：惊奇抬升（积分后写入），指数弛豫
        s4_t = -s4 / o["s4_tension_relax_hours"]
        # s5 注意：唤醒倒 U 型（0.5 处最高）+ 紧张加成
        att_target = 1.0 - abs(s1 - 0.5) * 1.6
        s5_t = (o["s5_attention_gain"] * _clip(att_target) + 0.3 * s4 - s5) / 0.5
        # s6 记忆激活：事件尖峰 + 指数衰减（尖峰在积分后直接写入）
        s6_t = -s6 / o["s6_memory_decay_hours"]
        # s7 预测误差：直接跟随注入值（快弛豫）
        s7_t = (surprise_bits / 6.0 - s7) / 0.1
        # s8 无聊：清醒且无事件时上升，事件打折重置；睡眠中不积累
        s8_t = (o["s8_boredom_rise_per_hour"] if (not event and not self.asleep) else 0.0)

        # 欧拉积分 + 小噪声（模拟内部涨落）
        noise = self.rng.normal(0, o["noise_sigma"], 8)
        derivs = np.array([s1_t, s2_t, s3_t, s4_t, s5_t, s6_t, s7_t, s8_t])
        self.s = np.clip(self.s + derivs * dt_hours + noise * math.sqrt(dt_hours), 0.0, 1.0)
        # 事件的瞬时作用必须直接写入状态（积分路径之外）
        if event:
            self.s[3] = _clip(self.s[3] + o["s4_tension_rise_per_surprise"] * surprise_bits / 4.0)  # s4 紧张
            self.s[5] = _clip(self.s[5] + 0.4)   # s6 记忆激活尖峰
            # s8 无聊缓解：相对新异度门控。早期（无参考值）一切皆新=强缓解；
            # 收敛后例行事件（惊奇≈均值）几乎不缓解 → 无聊在可预测的世界里积累。
            if ref_surprise is None:
                novelty = 1.0
            else:
                novelty = _clip((surprise_bits - ref_surprise + 0.5) / 2.0, 0.0, 1.0)
            self.s[7] *= (1.0 - 0.8 * novelty)
        self.surprise_bits = surprise_bits
        self.sleep_pressure = _clip(self.sleep_pressure)

    # ---- 输出 ----
    def snapshot(self):
        keys = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]
        snap = {k: round(float(v), 4) for k, v in zip(keys, self.s)}
        snap.update({
            "sim_time": self.clock.sim_time(),
            "sim_hour": round(self.clock.sim_hour(), 3),
            "day": self.clock.day_index(),
            "asleep": self.asleep,
            "sleep_pressure": round(self.sleep_pressure, 4),
            "mode": "B",
            "reflow_target": self.reflow_target,
            "reflow_fires": dict(self.reflow_fires),
        })
        return snap

    def save(self):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)

    def load(self):
        """恢复背景状态与仿真时钟（重启续跑）。"""
        if not os.path.exists(STATE_PATH):
            return False
        with open(STATE_PATH) as f:
            d = json.load(f)
        keys = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]
        for i, k in enumerate(keys):
            if k in d:
                self.s[i] = float(d[k])
        self.asleep = bool(d.get("asleep", False))
        self.sleep_pressure = float(d.get("sleep_pressure", 0.0))
        if isinstance(d.get("reflow_fires"), dict):
            for k in self.reflow_fires:
                self.reflow_fires[k] = int(d["reflow_fires"].get(k, 0))
        if "sim_time" in d:
            self.clock.t = float(d["sim_time"])
        return True

    # ---- 内联回流通道（P2.6）----
    def receive_inner_speech(self, text, valence):
        """被采纳的念头反作用于背景态。valence 来自语境统计
        （听到那句话时的 s2 与当前之差）。耦合强度由 config.reflow 控制（R1–R3 阶梯）。"""
        if self.asleep:
            return
        if valence < -self.reflow_thresh:
            self.s[self.reflow_idx] = _clip(self.s[self.reflow_idx] - self.reflow_s2)
            self.reflow_fires["valence_neg"] += 1
        elif valence > self.reflow_thresh:
            self.s[self.reflow_idx] = _clip(self.s[self.reflow_idx] + self.reflow_s2)
            self.reflow_fires["valence_pos"] += 1
        if "？" in text or "怎么" in text or "什么" in text:
            self.s[4] = _clip(self.s[4] + self.reflow_s5)     # 疑问类 → s5 注意微升
            self.reflow_fires["question"] += 1

    # 婴儿期探索行为：无聊超过阈值时产生内生行动意图（由 main 调用）
    def wants_explore(self):
        return (not self.asleep) and self.s[7] > self.explore_threshold

    # ---- P5：痛 / 乐 对状态的反馈 ----
    def receive_affect(self, distress_bias, ease_bias, gain):
        """gain=0 时为 no-op——与改动前逐位一致（默认 config.affect.k_affect=0）。
        痛：s4 紧张抬升，且 s8 无聊被压缩（注意力收窄）；
        乐：s4 松弛。两者共用同一增益，方向相反。"""
        if self.asleep or not gain:
            return
        self.s[3] = _clip(self.s[3] + gain * (distress_bias - ease_bias))
        if distress_bias > 0.0:
            self.s[7] = _clip(self.s[7] * (1.0 - 0.5 * gain * distress_bias))
