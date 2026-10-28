"""vocal.py — 发声（babbling）：第一个社交动作（E4 机制 B）

设计原则：给肌肉，不给目标。
- 发声是生理结构（婴儿啼哭/咿呀不需要被教）：强度门控（唤醒 s1 + 片段激活强度），
  无任何效价/方向项——它为什么发声、为谁发声，必须从后果中涌现。
- 内容零生成：只外化此刻检索胜出的内言语片段（它只能"说"听过的东西）。
- 有代价：消耗能量（进入资源经济）。
- 有后果：照护者（contingent 模式）会应答——动作-结果共变可被预测器学习（机制 A）。

E4 预注册（experiments/prereg_E4.json）：
- 共变学习：P(照护者言语|发声) / P(照护者言语) 随经验上升（H4a）
- 能动归因：跟随发声的照护者言语在习得共变后被归因为 self（H4b）
- 消退检验：共变移除后归因回落——证明是学到的不是硬编码（H4c）
"""
import json
import os
import random

import habituation as habituation_mod

VOCAL_PATH = os.path.join(os.path.dirname(__file__),
                          os.environ.get("STATE_DIR", "state"), "vocal.json")
HABITUATION_PATH = os.path.join(os.path.dirname(__file__),
                                os.environ.get("STATE_DIR", "state"), "habituation.json")
VOCAL_LOG_PATH = os.path.join(os.path.dirname(__file__),
                              os.environ.get("STATE_DIR", "state"), "vocalizations.jsonl")
# P15：反事实自我报告台账（结构化，非自由文本）
CF_LOG_PATH = os.path.join(os.path.dirname(__file__),
                           os.environ.get("STATE_DIR", "state"), "counterfactual.jsonl")


class Voice:
    def __init__(self, config):
        v = config.get("vocal", {})
        self.enabled = v.get("enabled", False)   # 默认关：E4 驱动显式开启
        self.arousal_gate = v.get("arousal_gate", 0.55)   # 唤醒门槛（生理）
        self.base_prob = v.get("base_prob", 0.25)         # 过门后的基础外化概率
        self.energy_cost = v.get("energy_cost", 1.0)      # 能量代价（探索的 1/5）
        # P14：候选池规模（仅 response_model.enabled 时生效）
        self.top_k = int(config.get("response_model", {}).get("top_k", 5))
        self.n_vocal = 0
        self.last_vocal_t = None       # 最近一次发声的 sim_time
        self.last_vocal_text = None    # P14b：最近一次发声的文本（供照护者按型应答）
        self._last_error = None
        # P19b：发声习惯化 + 去回声（默认关；启用时在选取处抑制重复/回声）
        self.habituation = habituation_mod.Habituation(config)

    def maybe_vocalize(self, state_vec, energy, focus, inner_result, sim_time,
                       candidates=None, response_model=None, partner_last=None):
        """本 tick 是否外化刚浮现的念头。返回发声文本或 None。
        门控全部为强度（无方向）：唤醒 × 片段激活强度 × 能量。
        P14：response_model 非空且 enabled 时，在候选池 top-k 内按 E[f] 选句
        （从「状态最像」改为「预期听者效果最好」）；为空时行为与改动前逐位一致。"""
        if not self.enabled or inner_result is None:
            return None
        try:
            s1 = float(state_vec[0])
            if s1 < self.arousal_gate:          # 生理：低唤醒不出声
                return None
            if energy is not None and not energy.can_afford(self.energy_cost):
                return None                     # 生理：没力气不出声
            act = float(inner_result.get("activation", 0.0))
            # 强度门：片段激活越强越可能外化（0.72 阈值 → 归一化 0..1）
            intensity = max(0.0, min(1.0, (act - 0.6) / 0.4))
            p = self.base_prob * (0.3 + 0.7 * s1) * (0.2 + 0.8 * intensity)
            if random.random() > p:
                return None
            if energy is not None:
                energy.spend(self.energy_cost)
            text = inner_result["text"]
            rm_meta = None
            if response_model is not None and response_model.enabled and candidates:
                pool = candidates[:self.top_k]
                # P19b：习惯化/去回声抑制（未启用时 penalty_fn=None，逐位不变）
                pen = None
                if self.habituation.enabled:
                    pen = lambda t: self.habituation.penalty(t, sim_time, partner_last)
                text, rm_meta = response_model.select(pool, text, penalty_fn=pen)
                response_model.note_vocal(sim_time, text)
            if self.habituation.enabled:
                self.habituation.note_spoken(text, sim_time)
            self.n_vocal += 1
            self.last_vocal_t = sim_time
            self.last_vocal_text = text   # P14b：记录发声的型
            rec = {"t": round(sim_time, 1), "text": text,
                   "activation": round(act, 3), "s1": round(s1, 3),
                   "self_directed": inner_result.get("self_directed", False)}
            if rm_meta is not None:
                rec.update(rm_meta)
            os.makedirs(os.path.dirname(VOCAL_LOG_PATH), exist_ok=True)
            with open(VOCAL_LOG_PATH, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            # P15：反事实自我报告——"我选了 X；本可以说 Y；决策时点预计差 ΔE"
            if rm_meta is not None and rm_meta.get("cf"):
                cf = rm_meta["cf"]
                cf_rec = {"t": round(sim_time, 1), "chosen": text,
                          "alt": cf["alt"], "E_chosen": cf["E_chosen"],
                          "E_alt": cf["E_alt"], "delta": cf["delta"],
                          "was_winner": rm_meta.get("was_winner")}
                with open(CF_LOG_PATH, "a") as f:
                    f.write(json.dumps(cf_rec, ensure_ascii=False) + "\n")
            return text
        except Exception as e:      # 发声永不致命
            self._last_error = str(e)
            return None

    def vocal_recent(self, sim_time, window_s=60.0):
        return (self.last_vocal_t is not None
                and sim_time - self.last_vocal_t < window_s)

    def snapshot(self):
        return {"enabled": self.enabled, "n_vocal": self.n_vocal,
                "last_vocal_t": self.last_vocal_t,
                "last_vocal_text": self.last_vocal_text,
                "last_error": self._last_error}

    def save(self):
        os.makedirs(os.path.dirname(VOCAL_PATH), exist_ok=True)
        with open(VOCAL_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)
        self.habituation.save(HABITUATION_PATH)

    def load(self):
        if not os.path.exists(VOCAL_PATH):
            return False
        try:
            with open(VOCAL_PATH) as f:
                d = json.load(f)
            self.n_vocal = int(d.get("n_vocal", 0))
            self.last_vocal_t = d.get("last_vocal_t")
            self.last_vocal_text = d.get("last_vocal_text")
            self.habituation.load(HABITUATION_PATH)
            return True
        except Exception:
            return False
