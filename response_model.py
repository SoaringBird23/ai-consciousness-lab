"""response_model.py — P14：从反射到意图

把发声内容的选择依据，从「与自身状态最相似」改为「对听者的预期效果最好」。

设计原则：
- 与候选生成完全解耦：只改「选哪一个」，不改「候选从哪来」。
- 与 predictor（E4）解耦：E4 学全局共变 C；这里按「片段型」分组学预期效果 E[f]。
- 反事实更新：发声前用 E 预测，发声后用真实回应修正 EMA（预测误差回写）。
- 冷启动：uniform 先验 → 前期选择≈top-1，判据因此限定在后 30 日。
- 言语计数只做指数衰减不加时长的技巧：speech 与 time 同步衰减时，
  速率 = speech/time 在衰减下保持不变（与 E4 共变统计同一技巧）。
"""
import json
import os
import random

STATE_DIR = os.environ.get("STATE_DIR", "state")
_ROOT = os.path.dirname(__file__)
RM_PATH = os.path.join(_ROOT, STATE_DIR, "response_model.json")


class ResponseModel:
    """按片段文本维护『说这句话后，听者回应强度』的 EMA 估计。"""

    def __init__(self, config):
        cfg = config.get("response_model", {})
        self.enabled = bool(cfg.get("enabled", False))
        self.shuffle = bool(cfg.get("shuffle", False))
        self.window_s = float(cfg.get("window_seconds", 60.0))
        hl_days = float(cfg.get("half_life_days", 5.0))
        self.half_life = hl_days * 86400.0
        self.alpha = float(cfg.get("ema_alpha", 0.2))
        self.uniform = 1.0
        # E[text] = 说 text 后 window_s 内听者言语率 / 窗口外语率 的 EMA
        self.E = {}
        # 上一个发声的待结算窗口
        self._last = None          # {"t": sim_time, "text": str}
        self._win_speech = 0.0     # 指数加权：窗口内到达的言语计数
        self._win_t = 0.0          # 指数加权：窗口内有效时长
        self._out_speech = 0.0     # 指数加权：窗口外到达的言语计数
        self._out_t = 0.0          # 指数加权：窗口外有效时长
        # 逐次更新历史（H14c 预测误差分析用；量级 ~4/日，60 日 ~240 条，全量保留）
        self.history = []          # [{"t", "text", "predicted", "observed", "err"}]

    # ---- 预测与选择 ----
    def predict(self, text):
        if not self.enabled:
            return self.uniform
        return self.E.get(text, self.uniform)

    def select(self, candidates, winner_text, penalty_fn=None):
        """从候选池中选择发声文本。

        candidates: list of (text, mem_score)，按记忆得分降序（[0] 即检索胜者）
        winner_text: 检索胜者文本
        penalty_fn: P19b 可选抑制项 text -> (0,1]；None 时行为与改动前逐位一致

        返回 (selected_text, meta)。meta 仅在 enabled 且候选非空时非 None。
        """
        if not self.enabled or not candidates:
            return winner_text, None
        texts = [c[0] for c in candidates]
        # shuffle 臂：对当前候选集做局部键重映射，E 的 lookup 与真实内容脱钩
        lookup = self._shuffle_lookup(texts) if self.shuffle else None
        scored = []
        e_scores = {}
        for text, mem_score in candidates:
            key = lookup[text] if lookup else text
            e = self.E.get(key, self.uniform)
            # P19b：习惯化/去回声抑制项（penalty_fn 为 None 时 eff == e，逐位不变）
            eff = e * (penalty_fn(text) if penalty_fn is not None else 1.0)
            scored.append((text, eff))
            e_scores[text] = round(e, 4)
        e_vals = [s[1] for s in scored]
        if max(e_vals) == min(e_vals):
            # E 全等（冷启动/未分化）→ 退化为 top-1（检索胜者）
            alt = scored[1][0] if len(scored) > 1 else None
            return winner_text, {
                "selected_by": "response_model",
                "reason": "e_tie",
                "E_scores": e_scores,
                "was_winner": True,
                "winner_text": winner_text,
                "cf": self._make_cf(winner_text, alt, scored),
            }
        scored.sort(key=lambda x: x[1], reverse=True)
        best = scored[0][0]
        alt = scored[1][0] if len(scored) > 1 else None
        return best, {
            "selected_by": "response_model",
            "E_scores": e_scores,
            "was_winner": (best == winner_text),
            "winner_text": winner_text,
            "cf": self._make_cf(best, alt, scored),
        }

    def _make_cf(self, chosen, alt, scored):
        """P15：反事实配对——chosen 与其 runner-up 及决策时点 E 差。
        仅用本次 select 时点的 E（更新前），保证无泄漏。"""
        if alt is None:
            return None
        e = {s[0]: s[1] for s in scored}
        ec, ea = e.get(chosen), e.get(alt)
        if ec is None or ea is None:
            return None
        return {"alt": alt, "E_chosen": round(ec, 4), "E_alt": round(ea, 4),
                "delta": round(ec - ea, 4)}

    def _shuffle_lookup(self, texts):
        """对 texts 做局部打乱，返回 text->shuffled_key 映射。
        种子取自集合内容哈希：同一 tick 同一候选集结果稳定，跨 tick 不同——
        内容对照需要的是『E 与内容的真实对应关系被摧毁』，而非可复现映射。"""
        if not texts:
            return {}
        shuffled = list(texts)
        rng = random.Random(hash(tuple(sorted(texts))) % (2**31))
        rng.shuffle(shuffled)
        return dict(zip(texts, shuffled))

    # ---- 时钟与更新（反事实 EMA） ----
    def advance_clock(self, dt_s, sim_time, n_speech=0):
        """每 tick 调用。n_speech = 本 tick 到达的照护者言语条数（可为 0/1/多）。
        P14c：由“有无言语”改为“言语条数”，短爆回应才能被正确计入速率。"""
        if not self.enabled:
            return
        decay = 0.5 ** (dt_s / self.half_life) if self.half_life > 0 else 1.0
        in_win = (self._last is not None
                  and sim_time - self._last["t"] < self.window_s)
        n = float(n_speech or 0)
        if in_win:
            self._win_t = self._win_t * decay + dt_s
            self._win_speech = self._win_speech * decay + n
            self._out_t *= decay
            self._out_speech *= decay
        else:
            self._win_t *= decay
            self._win_speech *= decay
            self._out_t = self._out_t * decay + dt_s
            self._out_speech = self._out_speech * decay + n

    def note_vocal(self, sim_time, text):
        """发声时刻调用：先结算上一个窗口（反事实更新），再开启本次窗口。"""
        if not self.enabled:
            return
        if self._last is not None:
            self._commit(sim_time)
        self._last = {"t": sim_time, "text": text}
        self._win_t = 0.0
        self._win_speech = 0.0

    def _commit(self, now_t):
        """把上一个发声窗口的实际观测回写为 EMA 更新（预测误差驱动的反事实修正）。"""
        text = self._last["text"]
        if self._win_t < 1.0:
            return  # 窗口有效时长太短，无统计意义
        r_in = self._win_speech / self._win_t
        r_out = self._out_speech / max(self._out_t, 1.0)
        observed = r_in / max(r_out, 1e-9)
        predicted = self.E.get(text, self.uniform)
        self.E[text] = predicted + self.alpha * (observed - predicted)
        self.history.append({
            "t": round(now_t, 1),
            "text": text,
            "predicted": round(predicted, 4),
            "observed": round(observed, 4),
            "err": round(observed - predicted, 4),
        })

    # ---- 持久化 ----
    def snapshot(self):
        return {
            "enabled": self.enabled,
            "shuffle": self.shuffle,
            "uniform": self.uniform,
            "E": dict(self.E),
            "last": self._last,
            "win_speech": self._win_speech,
            "win_t": self._win_t,
            "out_speech": self._out_speech,
            "out_t": self._out_t,
            "history": self.history,
        }

    def save(self):
        if not self.enabled:
            return
        os.makedirs(os.path.dirname(RM_PATH), exist_ok=True)
        with open(RM_PATH, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)

    def load(self):
        if not os.path.exists(RM_PATH):
            return False
        try:
            with open(RM_PATH, encoding="utf-8") as f:
                d = json.load(f)
            self.E = {k: float(v) for k, v in d.get("E", {}).items()}
            self._last = d.get("last")
            self._win_speech = float(d.get("win_speech", 0.0))
            self._win_t = float(d.get("win_t", 0.0))
            self._out_speech = float(d.get("out_speech", 0.0))
            self._out_t = float(d.get("out_t", 0.0))
            self.history = list(d.get("history", []))
            return True
        except Exception:
            return False
