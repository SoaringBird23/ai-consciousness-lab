"""awareness.py — 意识焦点雏形（P1，全局工作空间 GWT）

稀疏全局工作空间：大部分时间空着，只有显著性足够高的事件才能占据焦点。
焦点是"此刻被意识到的内容"，可以是非语言的（P1 还没有语言层）。

触发条件（任一）：
- 预测误差 s7 超阈值
- 情绪/紧张 s4 突变
- 记忆激活 s6 超阈值
- 探索行为发生
- 随机自发（低概率）

焦点进入工作空间后，在记忆里留下一条"focus"情景记忆。
输出：追加到 state/awareness_log.jsonl
"""
import json
import os
import math

STATE_DIR = os.environ.get("STATE_DIR", "state")
AWARENESS_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "awareness_log.jsonl")


class Awareness:
    def __init__(self, config):
        self.thresh_pred_err = config.get("awareness", {}).get("pred_err_threshold", 0.15)
        self.thresh_tension = config.get("awareness", {}).get("tension_jump_threshold", 0.3)
        self.thresh_mem = config.get("awareness", {}).get("memory_threshold", 0.5)
        self.spontaneous_prob = config.get("awareness", {}).get("spontaneous_prob", 1e-4)
        # 节流：同一原因的焦点最小间隔（仿真秒），防止刷屏
        self.min_interval_sim = config.get("awareness", {}).get("min_interval_sim", 600.0)
        self.last_focus_sim = {}  # reason -> 上次触发的 sim_time
        self.last_s4 = 0.0
        self.current_focus = None
        self.focus_count = 0

    def check(self, state_vec, surprise_bits, event, explore_happened, rng, sim_time=0.0):
        """每 tick 检查是否产生意识焦点。返回焦点 dict 或 None。"""
        s1, s2, s3, s4, s5, s6, s7, s8 = state_vec
        s4_jump = abs(s4 - self.last_s4)
        self.last_s4 = s4

        reasons = []
        salience = 0.0
        if s7 > self.thresh_pred_err:
            reasons.append("prediction_error")
            salience += s7
        if s4_jump > self.thresh_tension:
            reasons.append("tension_jump")
            salience += s4_jump
        if s6 > self.thresh_mem:
            reasons.append("memory_activation")
            salience += s6
        if explore_happened:
            reasons.append("explore")
            salience += 0.5
        if rng.rand() < self.spontaneous_prob:
            reasons.append("spontaneous")
            salience += 0.2

        if not reasons:
            self.current_focus = None
            return None

        # 节流：过滤掉最近已触发过的原因
        fresh = [r for r in reasons
                 if sim_time - self.last_focus_sim.get(r, -1e9) >= self.min_interval_sim]
        if not fresh:
            self.current_focus = None
            return None

        for r in fresh:
            self.last_focus_sim[r] = sim_time

        self.current_focus = {
            "reasons": fresh,
            "salience": round(salience, 3),
            "s": [round(float(v), 3) for v in state_vec],
            "surprise": round(surprise_bits, 3),
        }
        self.focus_count += 1
        return self.current_focus

    def log_focus(self, sim_time, focus):
        """写入意识焦点日志。"""
        record = {"t": round(sim_time, 1), **focus}
        os.makedirs(os.path.dirname(AWARENESS_PATH), exist_ok=True)
        with open(AWARENESS_PATH, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
