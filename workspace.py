"""workspace.py — 激活式工作集（R5：人类工作记忆/全局工作空间的对应物）

设计纪律（与项目既有原则一致）：
- 零方向：不设目标变量、不写任何『若 X 则 Y』规则；联想矩阵 A 纯数据驱动（共现）。
- 零外部奖赏：激活只由系统自身事件（听到 / 想到）驱动，无 reward。
- 默认关：workspace.enabled=false 时 activate/decay/working_set 直接返回，
  language.py 走原检索路径，行为与改动前逐位一致。

机制（对应人类语言认知）：
- 容量受限（Miller/Baddeley）：检索只在激活最高的 k 个『型』里发生。
- 扩散激活（Collins & Loftus）：activate(f) 时 act += κ·A[f]（A=共现后继，行归一化）。
- 复述/语音回路：念头被检索 → activate → 改变下一 tick 的工作集（双向闭环）。
- 启动与遗忘：分钟级指数衰减。

它为何能绕开 R3/R4 的两条硬约束：
- 抽样瓶颈：候选 = 工作集（沉积内容必在候选），不再随机抽 200/44k。
- 绑定判别度低：扩散走**共现**而非绑定相似度。
"""
import json
import math
import os

STATE_DIR = os.environ.get("STATE_DIR", "state")
STATE_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "workspace.json")


class Workspace:
    def __init__(self, config):
        w = config.get("workspace", {})
        self.enabled = bool(w.get("enabled", False))
        self.kappa = float(w.get("kappa", 1.0))          # 扩散强度
        self.k = int(w.get("k", 6))                       # 工作集容量（型数）
        self.tau_min = float(w.get("tau_minutes", 10.0))  # 衰减时间常数（仿真分钟）
        self.gain = float(w.get("gain", 1.0))             # 沉积强度
        self.shuffle_assoc = bool(w.get("shuffle_assoc", False))  # 对照：打乱联想
        self.no_deposit = bool(w.get("no_deposit", False))        # 对照：只读不写
        # ---- P9 联想启动（priming）：让 A 进入检索打分（优先级），而非仅筛选候选（容量）----
        self.priming = bool(w.get("priming", False))
        self.priming_gamma = float(w.get("priming_gamma", 1.0))
        self.shuffle_prime = bool(w.get("shuffle_prime", False))  # 对照：打乱 A 的行对应
        # P10：屏蔽自环——上一个念头不给自己投票（人类语义启动是关联而非自我重复）
        self.prime_no_self_loop = bool(w.get("prime_no_self_loop", False))
        # ---- P11 软先验：工作集不裁候选（候选=全长池），只把激活作为打分加权项 ----
        # 动机见 experiments/prereg_P11_soft.json：硬候选帽把检索空间从 403 型压到 10 型。
        self.soft_prior = bool(w.get("soft_prior", False))
        self.soft_gamma = float(w.get("soft_gamma", 1.0))
        # ---- P13 念头—念头工作空间：assoc 只记「检索胜出者 → 检索胜出者」的相继 ----
        # 动机见 experiments/prereg_P13.json：P6B–P12 的 A 混了「听→听」「听→念」，
        # 而判据真值（听—听）与「想—想」结构本质不同。本开关让 A 只学念头自身的相继。
        self.thought_only = bool(w.get("thought_only", False))
        self.act = {}          # text -> 激活
        self.assoc = {}        # text -> {next_text: count}（一阶共现）
        self._last = None      # 原始激活序列的上一项（听/念皆可；legacy 路径用）
        self.n_deposit = 0
        self._acc_h = 0.0      # 衰减累积器（见 decay）
        self._act_max = 0.0    # 本次检索的归一化基准（begin_retrieval 刷新）

    def decay(self, dt_hours):
        """每 tick 累积，按 tau 的 1% 为步长推进指数衰减。默认关时直接返回。

        修复记录（P11）：原实现用 `if f >= 0.999: return` 作性能守卫，但 tick 级
        步长（0.05 s → f=0.9999167）**永远**触发该守卫，于是衰减从未执行过、
        act 单调累积成终身计数——工作集 top-k 因此被永久钉死在高频枢纽上，
        检索空间从 403 型塌缩到 10 型；P6B「nodecay(tau=1e5)≈full(tau=10)」
        （0.0426 vs 0.0424）即此故：tau 是死参数。
        现改为累积到 f 与 1 可分辨（tau 的 1%）再一次性推进：语义与连续指数
        衰减一致，调用频次降为原来的约 1.4e-4 倍。
        """
        if not self.enabled:
            return
        self._acc_h += float(dt_hours)
        step_min = self._acc_h * 60.0
        if step_min < self.tau_min * 0.01:
            return
        f = math.exp(-step_min / max(1e-6, self.tau_min))
        self._acc_h = 0.0
        if f <= 0.0:
            self.act = {}
            return
        dead = []
        for t in self.act:
            self.act[t] *= f
            if self.act[t] < 1e-6:
                dead.append(t)
        for t in dead:
            del self.act[t]

    def _spread_row(self, text):
        """取 text 的联想行（对照臂用打乱行）。"""
        row = self.assoc.get(text)
        if not row:
            return None
        if self.shuffle_assoc and len(self.assoc) > 1:
            keys = [k for k in self.assoc if k != text]
            if keys:
                alt = self.assoc[keys[len(keys) // 2]]   # 确定性打乱（非真随机，便于复现）
                if alt:
                    return alt
        return row

    def activate(self, text, source="heard", write_assoc=True):
        """听到（source='heard'）或想到（source='thought'）text：沉积激活 + 沿联想扩散。
        默认关或 no_deposit（只读对照）时直接返回。

        P13：thought_only=True 时本方法**不写**共现矩阵 A —— 念头—念头共现改由
        record_assoc() 按「念头流」顺序显式记录。理由：原始激活序列里听到事件
        （约 170/日）远多于念头（约 7/日），两者交错使「念头→念头」的**字面相邻**
        几乎不存在（实测 1 日仅 3 行 A），A 会被架空。判据真值图正是按念头流顺序
        （retrieval 序列）构造的，二者须同源。
        write_assoc=False 用于使用期冻结（A 只读），切断正反馈自锁。"""
        if not self.enabled or not text:
            return
        if self.no_deposit:
            self._last = text
            return
        prev = self._last
        if write_assoc and not self.thought_only and prev is not None and prev != text:
            row = self.assoc.setdefault(prev, {})
            row[text] = row.get(text, 0) + 1
        self.act[text] = self.act.get(text, 0.0) + self.gain
        row = self._spread_row(text)
        if row:
            tot = sum(row.values())
            if tot > 0:
                for g, c in row.items():
                    self.act[g] = self.act.get(g, 0.0) + self.kappa * (c / tot)
        self._last = text
        self.n_deposit += 1

    def record_assoc(self, prev, text):
        """P13：按「念头流」顺序显式记录一条 念头→念头 共现（与听到事件无关）。
        由 language.evoke 在每次检索胜出时调用；使用期（A 冻结）由调用方保证不调用。"""
        if not self.enabled or not prev or not text or prev == text:
            return
        row = self.assoc.setdefault(prev, {})
        row[text] = row.get(text, 0) + 1

    def working_set(self):
        """激活最高的 k 个型；空则 None（调用方回退到原检索）。"""
        if not self.enabled or not self.act:
            return None
        top = sorted(self.act.items(), key=lambda kv: -kv[1])[:self.k]
        return [t for t, _ in top]

    # ---- P9：联想启动 ----
    def _prime_row(self, text):
        """取 text 的联想行用于 priming。对照臂（shuffle_prime）返回确定性打乱后的另一行，
        使 full 与 shuf 的唯一差别是"A 的内容是否真实"。"""
        row = self.assoc.get(text)
        if not row:
            return None
        if self.shuffle_prime and len(self.assoc) > 1:
            keys = sorted(k for k in self.assoc if k != text)
            if keys:
                return self.assoc[keys[len(keys) // 2]]
        return row

    def prime_bonus(self, prev, cand):
        """Â[prev][cand] = A[prev][cand] / sum(A[prev][*])（行归一化共现强度）。
        priming 关闭或无前驱时返回 0.0（调用方乘子退化为 1，与改动前逐位一致）。"""
        if not self.priming or not prev or not cand:
            return 0.0
        # P10：屏蔽自环（分子分母同时排除 prev 自身），使归一化只落在真实后继上
        if self.prime_no_self_loop and prev == cand:
            return 0.0
        row = self._prime_row(prev)
        if not row:
            return 0.0
        if self.prime_no_self_loop:
            tot = sum(c for k, c in row.items() if k != prev)
        else:
            tot = sum(row.values())
        if tot <= 0:
            return 0.0
        return row.get(cand, 0) / tot

    # ---- P11：软先验（act 作为打分加权项，不裁候选）----
    def begin_retrieval(self):
        """每次检索前刷新归一化基准（O(|act|) 一次，避免在候选循环里重复求 max）。"""
        if not self.soft_prior:
            return
        self._act_max = max(self.act.values()) if self.act else 0.0

    def soft_bonus(self, text):
        """Âct[text] = act[text]/max(act) ∈ [0,1]。soft_prior 关或无激活时返回 0.0
        （调用方乘子退化为 1，与改动前逐位一致）。"""
        if not self.soft_prior or self._act_max <= 0.0 or not text:
            return 0.0
        return self.act.get(text, 0.0) / self._act_max

    # ---- 持久化 ----
    def snapshot(self):
        return {"enabled": self.enabled, "kappa": self.kappa, "k": self.k,
                "tau_min": self.tau_min, "gain": self.gain,
                "shuffle_assoc": self.shuffle_assoc, "no_deposit": self.no_deposit,
                "priming": self.priming, "priming_gamma": self.priming_gamma,
                "shuffle_prime": self.shuffle_prime,
                "prime_no_self_loop": self.prime_no_self_loop,
                "soft_prior": self.soft_prior, "soft_gamma": self.soft_gamma,
                "thought_only": self.thought_only,
                "n_types_act": len(self.act),
                # P12：衰减累积器随盘持久化。否则重启最多丢失 tau*1% 的衰减窗口
                # （tau=720min → 7.2min；tau=1e5 → 16.7 仿真小时），使 act 系统性偏高
                "acc_h": self._acc_h,
                "act": {t: round(float(v), 6) for t, v in self.act.items()},
                "assoc": self.assoc, "last": self._last,
                "n_deposit": self.n_deposit}

    def save(self):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False)

    def load(self):
        if not os.path.exists(STATE_PATH):
            return False
        with open(STATE_PATH) as f:
            d = json.load(f)
        self.act = {t: float(v) for t, v in d.get("act", {}).items()}
        self.assoc = {k: {kk: int(vv) for kk, vv in v.items()}
                      for k, v in d.get("assoc", {}).items()}
        self._last = d.get("last")
        self.n_deposit = int(d.get("n_deposit", 0))
        self._acc_h = float(d.get("acc_h", 0.0))
        return True
