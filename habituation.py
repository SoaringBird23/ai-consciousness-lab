"""habituation.py — P19b 发声习惯化 + 去回声

P19 得到「有来有回」，但 87% 的轮次是重复句、且大量是原样回声（伙伴「我在这儿」→ 念「我在这儿」）。
本模块在**发声选取**处加两个生物上合理的抑制项：

1) 习惯化（satiation）：某句近期被说得越多，其选取得分越低；抑制随时间指数恢复。
   penalty = max(min_penalty, strength ** 近期使用质量)
   近期使用质量按半衰期衰减（默认 6 仿真小时）。
2) 去回声：候选与伙伴**紧邻上一轮**完全相同 → ×echo_penalty；
   互为子串（近回声）→ ×near_echo_penalty。

对照 shuffle：惩罚的取值分布不变，但键被随机替换为别的句子 ⇒「说得多→被抑制」的关联被打断。

零生成不变：只是抑制，不产生新句。
"""
import json
import os
import random


class Habituation:
    def __init__(self, config):
        cfg = config.get("habituation", {})
        self.enabled = bool(cfg.get("enabled", False))
        self.shuffle = bool(cfg.get("shuffle", False))
        self.half_life_s = float(cfg.get("half_life_hours", 6.0)) * 3600.0
        self.strength = float(cfg.get("strength", 0.8))
        self.min_penalty = float(cfg.get("min_penalty", 0.05))
        self.echo_penalty = float(cfg.get("echo_penalty", 0.15))
        self.near_echo_penalty = float(cfg.get("near_echo_penalty", 0.5))
        self._mass = {}          # text -> [mass, t]
        self._keys = []          # 供 shuffle 抽样（含重复，保持边际分布）

    def _decay(self, text, t):
        rec = self._mass.get(text)
        if not rec:
            return 0.0
        mass, ts = rec
        if self.half_life_s > 0 and t > ts:
            mass *= 0.5 ** ((t - ts) / self.half_life_s)
        return mass

    def note_spoken(self, text, t):
        """记录一次发声（更新该句的近期使用质量）。"""
        if not self.enabled or not text:
            return
        is_new = text not in self._mass
        mass = self._decay(text, t) + 1.0
        self._mass[text] = [mass, t]
        # shuffle 抽样池用**去重**文本，保证与「说得多少」无关（否则高频句仍被抽中）
        if is_new and len(self._keys) < 4000:
            self._keys.append(text)

    def penalty(self, text, t, partner_last=None):
        """返回 (0,1] 的选取得分乘子。

        shuffle 臂：整条惩罚（习惯化 + 去回声）都改用**代理文本**计算——
        取值分布与 full 相同，但与「候选自身」的关联/回声状态无关。
        """
        if not self.enabled:
            return 1.0
        ref = (self._keys[random.randrange(len(self._keys))]
               if (self.shuffle and self._keys) else text)
        mass = self._decay(ref, t)
        p = max(self.min_penalty, self.strength ** mass)
        if partner_last:
            if ref == partner_last:
                p *= self.echo_penalty
            elif ref in partner_last or partner_last in ref:
                p *= self.near_echo_penalty
        return p

    # ---- 持久化 ----
    def snapshot(self):
        return {"mass": {k: v[0] for k, v in self._mass.items()},
                "t_ref": self._t_ref()}

    def _t_ref(self):
        return max((v[1] for v in self._mass.values()), default=0.0)

    def save(self, path):
        if not self.enabled:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False)

    def load(self, path):
        if not self.enabled or not os.path.exists(path):
            return False
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            t_ref = float(d.get("t_ref", 0.0))
            self._mass = {k: [float(v), t_ref] for k, v in d.get("mass", {}).items()}
            self._keys = list(self._mass.keys())
            return True
        except Exception:
            return False
