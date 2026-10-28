"""spont.py — 自发双向（R3：预期-比较-修正 × 后果驱动耦合）

设计纪律（继承 motor.py：给肌肉，不给方向）：
- 零方向：不写任何"若 X 则 Y"的语义规则；不看、不设任何目标变量与符号。
- 零外部奖赏：学习信号只用系统自身已有的后果（自我预测误差，以及可选的
  痛/乐积分量），与 motor 一致——不存在实验者发下的 reward 标量。
- 默认关：spont.enabled=false 时 observe/act 全部直接返回；不消耗任何随机数、
  不写任何状态。行为与改动前逐位一致（在跑的线不受影响）。

本模块补两处结构缺口（见 experiments/prereg_R3.json；第三处 C1 成句重组在 language.py）：

C2 预期-比较-修正（自预期）：
    自我活动标量 a = mean(s1..s8)。
    自预期器预测下一刻的 a：a_hat = c·a_prev + d。
    (c, d) 初值 (1, 0)（中性：预测"不变"），由在线梯度学。
    每 tick 得自我预测误差 err = (a - a_hat)^2。
    闭环自指：写回使 s 变 → 下一刻的 a 变 → 它必须预测到这个变化。

C3 后果驱动耦合（复用 motor 范式）：
    上下文 σ = sign(念头效价 valence)：正念 +1 / 负念 -1。
    动作 i ∈ {s1..s8}，共 8 个原语；g[σ][i] 初值全 0。
    ε-贪心：以 explore 概率随机挑 i（中性探测），否则 argmax g[σ][:]。
    写回 delta = base_step · σ 到 s[i]（量级沿用历史 reflow，符号来自念头自身）。
    后果 outcome = Δease − Δdistress + (err_before − err_after)，
    在写回与下次结算之间测（自因/世界因不做显式分离，先做最小版）。
    更新 g[σ][i] += lr·(outcome − g[σ][i])；g 向 0 缓慢衰减。
    起点全 0、只被后果推动 → 长出来的任何结构都是系统自己的；可能一直不长。

shuffle 对照臂：结算时用"历史 outcome 的随机置换"替代当前 outcome，
    断开"动作 → 后果"的对应——若 full 与 shuf 的 |g| 无差异，则结构来自探测噪声。
"""
import json
import os

import numpy as np

STATE_DIR = os.environ.get("STATE_DIR", "state")
STATE_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "spont.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "spont.jsonl")


class Spont:
    def __init__(self, config):
        sp = config.get("spont", {})
        self.enabled = bool(sp.get("enabled", False))
        self.compose = bool(sp.get("compose", False))            # C1 开关（实现在 language.py）
        self.self_predict = bool(sp.get("self_predict", False))  # C2
        self.learn_coupling = bool(sp.get("learn_coupling", False))  # C3
        self.shuffle = bool(sp.get("shuffle", False))            # 对照臂：置换后果
        # 独立 RNG：臂间只应差一个机制，不能因本模块多抽一个随机数而污染
        # 背景层噪声流（main 的 rng）。故自带一条流，种子由全局 seed 派生。
        seed = int(config.get("time", {}).get("seed", 42))
        self.rng = np.random.RandomState(seed + 60013)
        # ---- C2 参数 ----
        self.predict_lr = float(sp.get("predict_lr", 0.05))
        self.err_alpha = float(sp.get("err_alpha", 0.02))        # err  EMA 平滑
        # ---- C3 参数 ----
        self.base_step = float(sp.get("base_step", 0.02))
        self.lr = float(sp.get("learning_rate", 0.08))
        self.explore = float(sp.get("exploration", 0.15))
        self.decay = float(sp.get("decay", 0.001))
        self.n_primitives = 8
        # ---- C2 状态 ----
        self.c = 1.0
        self.d = 0.0
        self._prev_a = None
        self.err_now = 0.0
        self.err_ema = 0.0
        self.n_obs = 0
        # ---- C3 状态 ----
        self.g = {1: [0.0] * self.n_primitives, -1: [0.0] * self.n_primitives}
        self.pending = None
        self.outcome_hist = []                                   # 供 shuffle 置换
        self.n_acts = 0
        self.n_probes = 0
        self.n_writes = 0
        self._last_error = None
        # ---- R4：后果窗口积分（替代 R3 的端点差分）----
        # 写回后逐 tick 累积 (ease-distress) 相对写回时刻基线的偏差；
        # 结算时取窗口均值 —— 拾回在端点前已弛豫的瞬态后果（见 prereg_R4）。
        self.win_base = 0.0                                      # 写回时刻的 (ease-distress)
        self.win_dev = 0.0                                       # 窗口内累积偏差之和
        self.win_n = 0                                           # 窗口内 tick 数

    # ============ C2：每 tick 自预期 ============
    def observe(self, s):
        """预测下一刻的自我活动标量并记误差。返回 err 或 None。"""
        if not (self.enabled and self.self_predict):
            return None
        a = float(np.mean(np.asarray(s, dtype=float)))
        if self._prev_a is None:            # 首 tick 无历史，只记锚点
            self._prev_a = a
            return None
        a_hat = self.c * self._prev_a + self.d
        resid = a - a_hat
        err = resid * resid
        # 在线梯度（最小化 (a - a_hat)^2；∂/∂c = -2·resid·a_prev，∂/∂d = -2·resid）
        self.c += self.predict_lr * resid * self._prev_a
        self.d += self.predict_lr * resid
        self.err_now = err
        self.err_ema = (err if self.n_obs == 0
                        else self.err_ema + self.err_alpha * (err - self.err_ema))
        self.n_obs += 1
        self._prev_a = a
        return err

    # ============ C3 辅助：每 tick 累积后果窗口（R4）============
    def tick(self, ease, distress):
        """每 tick 累积 (ease-distress) 相对写回时刻基线的偏差。
        默认关（enabled 或 learn_coupling 为 false）时直接返回，不改状态。"""
        if not (self.enabled and self.learn_coupling):
            return
        if self.pending is None:
            return
        self.win_dev += (float(ease) - float(distress)) - self.win_base
        self.win_n += 1

    # ============ C3：念头浮现时结算 + 选新原语 ============
    def act(self, valence, s, distress, ease, sim_time, day_index):
        """一次念头 → 一次写回。先结算上一次写回（后果），再选新原语写回。
        s 就地修改（numpy 状态向量）。返回记录 dict 或 None（未开启时）。"""
        if not (self.enabled and self.learn_coupling):
            return None
        s = np.asarray(s)
        resolved = None
        # ---- 结算上一次写回（R4：窗口积分，替代 R3 端点差分）----
        if self.pending is not None:
            p = self.pending
            integ = (self.win_dev / self.win_n) if self.win_n > 0 else 0.0
            outcome = integ + (p["err_before"] - self.err_now)
            used = outcome
            if self.shuffle and self.outcome_hist:      # 对照臂：断开动作↔后果
                used = float(self.rng.choice(self.outcome_hist))
            for sg in (1, -1):                          # g 向 0 缓慢衰减
                gg = self.g[sg]
                for i in range(self.n_primitives):
                    gg[i] *= (1.0 - self.decay)
            gi = self.g[p["sigma"]]
            gi[p["idx"]] += self.lr * (used - gi[p["idx"]])
            self.outcome_hist.append(round(outcome, 8))
            if len(self.outcome_hist) > 2000:
                self.outcome_hist = self.outcome_hist[-2000:]
            resolved = {"prev_sigma": p["sigma"], "prev_idx": p["idx"],
                        "prev_outcome": round(outcome, 8),
                        "prev_integ": round(integ, 8),
                        "prev_g_after": round(gi[p["idx"]], 6),
                        "used": round(used, 8)}
            self.pending = None

        # ---- 选新原语并写回 ----
        sigma = 1 if valence >= 0.0 else -1
        g = self.g[sigma]
        if self.rng.random() < self.explore:            # 中性探测（零方向）
            idx = int(self.rng.randint(0, self.n_primitives))
            self.n_probes += 1
            explore = True
        else:
            idx = int(max(range(self.n_primitives), key=lambda i: g[i]))
            explore = False
        delta = self.base_step * sigma
        s[idx] = float(np.clip(float(s[idx]) + delta, 0.0, 1.0))
        self.pending = {"sigma": sigma, "idx": idx,
                        "err_before": self.err_now,
                        "distress_before": float(distress),
                        "ease_before": float(ease)}
        self.win_base = float(ease) - float(distress)   # R4：窗口基线
        self.win_dev = 0.0
        self.win_n = 0
        self.n_acts += 1
        self.n_writes += 1

        rec = {"t": round(sim_time, 1), "day": day_index, "kind": "write",
               "sigma": sigma, "idx": idx, "delta": round(delta, 5),
               "explore": explore, "g_chosen": round(g[idx], 6),
               "err": round(self.err_now, 8),
               "distress": round(float(distress), 4),
               "ease": round(float(ease), 4), "shuffle": self.shuffle}
        if resolved is not None:
            rec.update(resolved)
        self._log(rec)
        return rec

    # ---- 记录 ----
    def _log(self, rec):
        try:
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
            with open(LOG_PATH, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            self._last_error = str(e)

    # ============ 持久化 ============
    def snapshot(self):
        return {
            "enabled": self.enabled, "compose": self.compose,
            "self_predict": self.self_predict,
            "learn_coupling": self.learn_coupling, "shuffle": self.shuffle,
            "c": round(self.c, 6), "d": round(self.d, 6),
            "err_now": round(self.err_now, 8), "err_ema": round(self.err_ema, 8),
            "n_obs": self.n_obs, "n_acts": self.n_acts,
            "n_probes": self.n_probes, "n_writes": self.n_writes,
            "g_pos": [round(float(x), 6) for x in self.g[1]],
            "g_neg": [round(float(x), 6) for x in self.g[-1]],
            "pending": self.pending,
            "prev_a": (None if self._prev_a is None else round(self._prev_a, 8)),
            "outcome_hist": self.outcome_hist[-2000:],
            "win_base": round(self.win_base, 8),
            "win_dev": round(self.win_dev, 8),
            "win_n": self.win_n,
            "last_error": self._last_error,
        }

    def save(self):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)

    def load(self):
        if not os.path.exists(STATE_PATH):
            return False
        with open(STATE_PATH) as f:
            d = json.load(f)
        self.c = float(d.get("c", 1.0))
        self.d = float(d.get("d", 0.0))
        self.err_ema = float(d.get("err_ema", 0.0))
        self.n_obs = int(d.get("n_obs", 0))
        self.n_acts = int(d.get("n_acts", 0))
        self.n_probes = int(d.get("n_probes", 0))
        self.n_writes = int(d.get("n_writes", 0))
        self.g = {1: [float(x) for x in d.get("g_pos", [0.0] * self.n_primitives)],
                  -1: [float(x) for x in d.get("g_neg", [0.0] * self.n_primitives)]}
        self.pending = d.get("pending")
        self._prev_a = d.get("prev_a")
        self.outcome_hist = [float(x) for x in d.get("outcome_hist", [])]
        self.win_base = float(d.get("win_base", 0.0))
        self.win_dev = float(d.get("win_dev", 0.0))
        self.win_n = int(d.get("win_n", 0))
        return True
