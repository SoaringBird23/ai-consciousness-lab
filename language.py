"""language.py — 语言层（P2.6 内化路线，Vygotsky）

对"幻觉/表演"问题的结构性回答：念头不生成，只检索。

- 本层不再调用任何 LLM。内言语 = 状态对语言记忆的激活检索。
  它只能说听过的东西——零幻觉是结构保证，不是 prompt 约束。
- 路径（Vygotsky 内言语发展）：
    听（照护者语言，绑定听到时的状态向量）
    → 私语（刚听到的话高概率复述，echo）
    → 内化（当前状态与"听到那句话时的状态"相似 → 片段自发激活，retrieval）
- 念头的情绪色彩来自语境统计：某片段总在状态好时被听到，它激活时携带正向——
  词义=共现，不预写任何词典。
- 自我指向语言（照护者说"你"）被激活 = 自我相关念头，喂给 self_model。
- 主题反复激活 → goals.json（目标涌现，基于片段本身，不基于人类分类）。

变量对外只有中性代号 s1..s8；相似度计算权重也用中性索引。
"""
import json
import math
import os
import random
from collections import deque

STATE_DIR = os.environ.get("STATE_DIR", "state")
_ROOT = os.path.dirname(__file__)
INNER_SPEECH_PATH = os.path.join(_ROOT, STATE_DIR, "inner_speech.jsonl")
GOALS_PATH = os.path.join(_ROOT, STATE_DIR, "goals.json")
LANG_STATE_PATH = os.path.join(_ROOT, STATE_DIR, "language_state.json")
LING_MEMORY_PATH = os.path.join(_ROOT, STATE_DIR, "linguistic_memory.json")


def _cumsum(weights):
    """累积权重。random.choices 若不传 cum_weights，每次调用都会重建整个分布
    （8.3 万型 = 每次选句 O(n)）；预计算后走 bisect，是 O(log n)。
    语料扩到 8 万短语后这不是优化，是必需——否则语言层会被选句拖死。"""
    out, acc = [], 0.0
    for w in weights:
        acc += w
        out.append(acc)
    return out

# ---- 照护者语料（真实育儿语言分布：高度重复 + 少量新奇）----
# 环境怎么说话是世界的属性（我们模拟世界的自由度），它的念头则完全由经历决定。
CORPUS_EVENT = [          # 事件/互动时说（好奇、招呼、命名）
    "哦？", "咦", "怎么了", "怎么了呀", "看", "看这个", "又动了", "又动啦",
    "是你呀", "你好呀", "你醒啦", "又在看", "对", "对呀", "来了来了",
    "什么声音", "呀", "摸摸", "轻轻的", "在这里", "在这儿呢",
]
CORPUS_NIGHT = [          # 夜间/哄睡
    "嘘", "安静哦", "睡吧", "睡喽", "睡觉觉", "晚啦", "不哭哦", "别怕",
    "不怕哦", "乖", "好啦", "好啦好啦", "嗯嗯",
]
CORPUS_DAY = [            # 白天安静时段（filler + 正向）
    "真乖", "好孩子", "饿不饿", "等一下", "等等哦", "再看看", "慢一点",
    "对了", "乖", "嗯", "哦", "天亮了", "亮了", "真乖", "在这里",
]
# 自我指向语料（少量——照护者偶尔指着它说话；"你"的内化是镜像期的种子）
CORPUS_SELF = [
    "这是你", "是你呀", "你醒啦", "你在看", "你又动了", "你好呀",
    # 第一人称（2026-10-05 用户决定加入）：真实照护者会说"我"——
    # "我"与自我指向场景严格共现（被注视/被安抚时刻），保证将来"我"被检索时
    # 携带"被爱注视"的语境色彩。你→我的倒转（人类 20-30 月龄里程碑）自此可及。
    "我在这儿", "我在这儿呢", "是我呀", "我陪你", "我看着你呢", "我不走",
]
# C1 对照用：第一人称短语清单 + 只含第二人称的自我指向子集
# FP_SOOTHE = 原 bound 通道 3 的安抚池（保持与历史行为逐字一致——E6 fork
# 与 XP 线的对照要求 bound 模式零改动）
FIRST_PERSON = ["我在这儿", "我在这儿呢", "是我呀", "我陪你", "我看着你呢", "我不走"]
FP_SOOTHE = ["我在这儿", "我在这儿呢", "我陪你"]
CORPUS_SELF_2P = [p for p in CORPUS_SELF if p not in FIRST_PERSON]

# 状态相似度权重（中性索引）：这几个维度区分度高
SIM_WEIGHTS = {0: 1.0, 3: 1.2, 6: 1.5, 7: 1.0}   # s1, s4, s7, s8


class Language:
    def __init__(self, config):
        lang_cfg = config.get("language", {})
        cg_cfg = config.get("caregiver", {})
        self.enabled = lang_cfg.get("enabled", True)
        # 听
        self.speech_per_hour_quiet = cg_cfg.get("speech_per_hour_quiet", 4.0)
        self.speech_prob_with_event = cg_cfg.get("speech_prob_with_event", 0.6)
        self.self_prob = cg_cfg.get("self_directed_prob", 0.08)
        # E3：照护者模式 random（零应答，对照）| contingent（状态应答式）
        self.cg_mode = cg_cfg.get("mode", "random")
        # C1：第一人称语料的语境绑定方式 bound（默认：紧张/被注视时刻）
        # | inverted（对照：平静/无焦点时刻——频率匹配、语境反转）
        self.fp_context = cg_cfg.get("first_person_context", "bound")
        # S2 分离实验：把原修复里被同时改动的两个变量拆成独立开关
        #   corpus_first_person=False → 照护者语料不含任何第一人称短语
        #   self_directed_words=["你"] → self_directed 门控只看第二人称（修复前的状态）
        self.corpus_fp = bool(cg_cfg.get("corpus_first_person", True))
        self.sd_words = list(lang_cfg.get("self_directed_words", ["你", "我"]))
        # C1b（deviation_1）：inverted 通道速率参数化——平静态占全天多数，
        # 同概率下暴露率是 bound 的 ~8 倍；按实测校准以实现真正的频率匹配
        self.fp_inv_rate_soothe = cg_cfg.get("fp_inverted_rate_soothe", 10.0)
        self.fp_inv_rate_salience = cg_cfg.get("fp_inverted_rate_salience", 5.0)
        self._prev_asleep = None
        # E4：对发声的应答概率（contingent 模式下）
        self.vocal_response_prob = cg_cfg.get("vocal_response_prob", 0.7)
        # E4 修复：每个发声窗口只应答一次（此前逐 tick 掷骰 → 60s 窗口内
        # 洪水式应答 8000+/日，p1 已污染清洗重跑，见 experiments/e4/deviation_1.json）
        self._vocal_win_active = False
        self._vocal_responded = False
        # 私语（echo）：复述概率随内化天数缓慢衰减
        self.echo_prob0 = lang_cfg.get("echo_prob_initial", 0.40)
        self.echo_decay_days = lang_cfg.get("echo_decay_days", 10.0)
        # 检索（retrieval）
        self.evoke_threshold = lang_cfg.get("evoke_threshold", 0.72)
        self.evoke_interval = lang_cfg.get("evoke_interval_seconds", 120)
        self.recency_half_life_days = lang_cfg.get("recency_half_life_days", 5.0)
        self.freq_gain = lang_cfg.get("frequency_gain", 0.12)
        # 计数
        self.n_heard = 0
        self.n_echo = 0
        self.n_retrieval = 0
        self.existence_count = 0
        self.first_heard_t = None
        # ---- 外部语料（扩语料）：不分池，按频次加权从整池采 ----
        # 设为 caregiver.corpus_file 时启用；未设时行为与改动前逐位一致。
        # 采样策略：权重 ∝ 语料中观测频次^exponent（真实儿童语言是 Zipf 分布，
        # 少数句子极高频、长尾极大——这样才保住"高重复 + 少量新奇"的发育结构）。
        self.corpus_texts = []
        self.corpus_weights = []
        self.corpus_cum = []               # 累积权重（选句 O(log n)）
        self.corpus_directed = []          # 含"你/我"的子集索引（状态定义时刻用）
        self.corpus_directed_cum = []
        _cf = cg_cfg.get("corpus_file")
        if _cf:
            self._load_corpus(_cf, float(cg_cfg.get("corpus_zipf_exponent", 1.0)))
        # ---- P7 话题连续性（burst）：一次说话回合内连说 k 句同一会话的话 ----
        # 单元是"会话"而非相邻句——可行性探测显示相邻转移过稀（核心 5000 条中
        # 仅 1000 条有重复后继），一阶马尔可夫链学不到结构。
        # burst_shuffled=True 是对照臂：回合长度与语率完全相同，但句间独立，
        # 用于把"爆发结构"与"话题内容"分开。
        self.burst_mode = bool(cg_cfg.get("burst_mode", False))
        self.burst_shuffled = bool(cg_cfg.get("burst_shuffled", False))
        self.burst_k_min = int(cg_cfg.get("burst_k_min", 3))
        self.burst_k_max = int(cg_cfg.get("burst_k_max", 5))
        self.burst_sessions = []           # 每个会话的短语列表
        self.burst_session_cum = []        # 每个会话内部的累积权重
        self.burst_session_size = []       # 每个会话的话语量（会话被抽中的权重）
        self.burst_session_size_cum = None # 跨会话的累积权重（载入后一次算好）
        self.burst_directed = []           # 每个会话内含"你/我"的子集
        self.burst_directed_cum = []
        self.burst_session = None
        self.burst_remaining = 0
        if self.burst_mode:
            self._load_sessions(cg_cfg.get("sessions_file",
                                           "corpus/caregiver_sessions.json"))
        # 语言记忆：[{text, t, s2, hour, self_directed}]，片段级
        self.memory = []
        self.recent_inner = deque(maxlen=8)
        # 目标涌现：片段文本重复激活统计
        goal_cfg = config.get("goals", {})
        self.goal_min_activations = goal_cfg.get("min_activations", 15)
        self.goal_min_fraction = goal_cfg.get("min_fraction", 0.2)
        self.goal_min_days = goal_cfg.get("min_days", 3)
        self.goal_window = goal_cfg.get("window", 300)
        self.fragment_activations = {}   # text -> {count, days[], promoted}
        self.goals = []
        # 目标涌现的滚动窗口：最近 N 次自发检索（窗口占比替代全期占比）
        self.retrieval_log = deque(maxlen=self.goal_window)
        self._last_evoke_t = 0.0
        self._last_error = None

    # ============ 外部语料：加载与采样（扩语料）============
    def _load_corpus(self, path, exponent):
        """加载语料 JSON（[{"text":..., "count":...}, ...]）。
        exponent=1.0 → 权重正比于观测频次（保真 Zipf）；>1 → 更偏向高频。
        累积权重预先算好：random.choices 若不传 cum_weights，每次调用都会重建
        整个分布（8.3 万型 = 每次选句 O(n)），会把语言层拖垮。预计算后是 O(log n)。"""
        full = path if os.path.isabs(path) else os.path.join(_ROOT, path)
        if not os.path.exists(full):
            return
        with open(full, encoding="utf-8") as f:
            rows = json.load(f)
        texts, weights, d_w = [], [], []
        for r in rows:
            t = str(r.get("text", "")).strip()
            if not t:
                continue
            w = max(1e-9, float(r.get("count", 1))) ** exponent
            texts.append(t)
            weights.append(w)
            if any(word in t for word in self.sd_words):
                d_w.append((len(texts) - 1, w))
        if not texts:
            return
        self.corpus_texts = texts
        self.corpus_weights = weights
        self.corpus_cum = _cumsum(weights)
        self.corpus_directed = [i for i, _ in d_w]
        self.corpus_directed_cum = _cumsum([w for _, w in d_w])

    def _sample_corpus(self, directed=False):
        if directed and self.corpus_directed:
            i = random.choices(self.corpus_directed,
                               cum_weights=self.corpus_directed_cum, k=1)[0]
            return self.corpus_texts[i]
        return random.choices(self.corpus_texts,
                              cum_weights=self.corpus_cum, k=1)[0]

    def _say(self, pool, directed=False, use_burst=False):
        """选一句要说的话：加载了外部语料 → 按频次加权从整池采；
        否则退回内置池（未设 corpus_file 时行为与改动前逐位一致）。
        directed=True 时只从含"你/我"的子集里采——自我指向输入是自我模型
        形成的硬前提（213 天 null 已证），故保留这一条词法过滤。
        use_burst=True（仅用于通用内容的通道：安静基流 / 事件命名）时，改走
        话题连续采样；状态针对性的通道（醒来问候 / 安抚 / 被注视 / 应答）
        不受影响，以保住"什么时候说"的状态驱动性。"""
        if self.corpus_texts:
            if use_burst and self.burst_mode and self.burst_sessions:
                return self._burst_next(directed)
            return self._sample_corpus(directed)
        return random.choice(pool)

    def _load_sessions(self, path):
        """加载会话索引：{"sessions": [[[phrase, count], ...], ...]}。
        每个会话的累积权重与"含你/我"子集都在这里一次算好，避免选句时重建。"""
        full = path if os.path.isabs(path) else os.path.join(_ROOT, path)
        if not os.path.exists(full):
            return
        with open(full, encoding="utf-8") as f:
            d = json.load(f)
        for s in d.get("sessions", []):
            texts, wts, dtexts, dwts = [], [], [], []
            for t, c in s:
                t = str(t)
                if not t:
                    continue
                texts.append(t)
                wts.append(float(c))
                if any(word in t for word in self.sd_words):
                    dtexts.append(t)
                    dwts.append(float(c))
            if not texts:
                continue
            self.burst_sessions.append(texts)
            self.burst_session_cum.append(_cumsum(wts))
            self.burst_session_size.append(sum(wts))
            self.burst_directed.append(dtexts)
            self.burst_directed_cum.append(_cumsum(dwts))
        if self.burst_session_size:
            self.burst_session_size_cum = _cumsum(self.burst_session_size)

    def _burst_next(self, directed=False):
        """一次说话回合内，从同一会话里连续取句。回合用尽则新开一个会话。"""
        if self.burst_remaining <= 0 or self.burst_session is None:
            self.burst_session = random.choices(
                range(len(self.burst_sessions)),
                cum_weights=self.burst_session_size_cum, k=1)[0]
            self.burst_remaining = random.randint(self.burst_k_min, self.burst_k_max)
        self.burst_remaining -= 1
        if self.burst_shuffled:              # 对照臂：结构相同、句间独立
            return self._sample_corpus(directed)
        i = self.burst_session
        if directed and self.burst_directed[i]:
            return random.choices(self.burst_directed[i],
                                  cum_weights=self.burst_directed_cum[i], k=1)[0]
        if directed:
            return self._sample_corpus(True)
        return random.choices(self.burst_sessions[i],
                              cum_weights=self.burst_session_cum[i], k=1)[0]

    # ============ 环境（照护者）说话 ============
    def caregiver_speaks(self, dt_hours, sim_hour, event_happened,
                         state_vec=None, asleep=None, salience=0.0,
                         vocal_recent=False):
        """决定本 tick 照护者是否说话，返回话语或 None。纯环境侧。
        - random 模式（原逻辑，对照）：随机时机 + 随机语料，与候选体状态无关（零应答）
        - contingent 模式（E3 应答式）：说话时机与内容由候选体状态驱动——
          环境可以有应答性（真实父母的属性）；候选体内部机制零改动。
        - E4：contingent 模式下对发声（vocal_recent）高概率应答——
          动作-结果共变的来源。
        """
        if not self.enabled:
            return None

        if self.cg_mode == "contingent" and state_vec is not None:
            # 睡眠期不说话（醒来瞬间除外，见下）；仅更新睡眠记忆
            woke = (self._prev_asleep is True) and (asleep is False)
            self._prev_asleep = asleep
            if asleep:
                return None
            # 0) E4：它刚发声 → 应答（每窗口至多一次）
            if vocal_recent:
                if not self._vocal_win_active:       # 新发声窗口开启
                    self._vocal_win_active = True
                    self._vocal_responded = False
                if (not self._vocal_responded
                        and random.random() < self.vocal_response_prob):
                    self._vocal_responded = True
                    pool = ["看", "看这个", "又动了", "又动啦", "来了来了",
                            "是你呀", "你在看", "你好呀", "对", "对呀"]
                    return random.choice(pool)
            else:
                self._vocal_win_active = False       # 窗口结束，下次发声可再应答
            # 1) 醒来时刻：晨间问候（每天必现的自我指向共现）
            if woke:
                return self._say(["你醒啦", "你醒啦", "你醒啦", "你好呀"], directed=True)
            # 2) 事件时刻：命名/好奇（与随机模式同概率、同语料）
            if event_happened and random.random() < self.speech_prob_with_event:
                return self._say(CORPUS_EVENT, use_burst=True)
            # 3) 紧张高（s4）：安抚——含第一人称在场承诺（"我在这儿"与被安抚共现）
            #    C1 对照（inverted）：同一批"我"短语移到平静时刻说——频率匹配、语境反转
            fp_soothe = FP_SOOTHE if (self.corpus_fp and self.fp_context == "bound") else []
            if state_vec[3] > 0.62 and random.random() < 10.0 * dt_hours:
                return self._say(CORPUS_NIGHT + fp_soothe)
            if (self.corpus_fp and self.fp_context == "inverted" and state_vec[3] < 0.40
                    and random.random() < self.fp_inv_rate_soothe * dt_hours):
                return self._say(FP_SOOTHE, directed=True)
            # 4) 无聊高（s8）：互动召唤（8/时）
            if state_vec[7] > 0.40 and random.random() < 8.0 * dt_hours:
                return self._say(["看", "看这个", "又动了", "又动啦",
                                  "摸摸", "来了来了"])
            # 5) 注意焦点显著：自我指向——"你"与被注视状态共现（5/时）
            #    C1（inverted）：高焦点时刻只说"你"族；"我"族移到无焦点时刻（频率匹配）
            pool_self = (CORPUS_SELF if (self.corpus_fp and self.fp_context == "bound")
                         else CORPUS_SELF_2P)
            if salience > 0.6 and random.random() < 5.0 * dt_hours:
                return self._say(pool_self, directed=True)
            if (self.corpus_fp and self.fp_context == "inverted" and salience < 0.3
                    and random.random() < self.fp_inv_rate_salience * dt_hours):
                return self._say(FIRST_PERSON, directed=True)
            # 6) 默认：安静时段基础语流（与随机模式同率；自我指向通道已由 1/5 承担）
            p = self.speech_per_hour_quiet * dt_hours
            if random.random() < p:
                pool = CORPUS_NIGHT if (21 <= sim_hour or sim_hour < 5) else CORPUS_DAY
                return self._say(pool, use_burst=True)
            return None

        # ---- random 模式（原逻辑，对照） ----
        self._prev_asleep = asleep
        if event_happened and random.random() < self.speech_prob_with_event:
            pool = CORPUS_EVENT
        else:
            # 安静时段按泊松率说话
            p = self.speech_per_hour_quiet * dt_hours
            if random.random() > p:
                return None
            if 21 <= sim_hour or sim_hour < 5:
                pool = CORPUS_NIGHT
            else:
                pool = CORPUS_DAY
        # 少量自我指向语言
        if random.random() < self.self_prob:
            text = self._say(CORPUS_SELF, directed=True)
        else:
            text = self._say(pool)
        return text

    # ============ 听 ============
    def hear(self, text, state_vec, sim_time):
        """外部语言进入。存储片段 + 听到时的状态快照。"""
        self.memory.append({
            "text": text,
            "t": round(sim_time, 1),
            "s": [round(float(v), 4) for v in state_vec],
            "self_directed": any(w in text for w in self.sd_words),  # S2：门控词表可配（默认含"我"，与 self_model 词表对齐）
            "echoed": False,          # 私语复述只发生一次（真实私语是复述一两遍）
        })
        self.n_heard += 1
        if self.first_heard_t is None:
            self.first_heard_t = sim_time
        return self.memory[-1]

    # ============ 念头：私语 + 检索 ============
    def _state_sim(self, a, b):
        """两状态向量的加权相似度（0-1）。"""
        num = 0.0
        den = 0.0
        for i, w in SIM_WEIGHTS.items():
            num += w * (1.0 - abs(a[i] - b[i]))
            den += w
        return num / den if den else 0.0

    def _echo_prob(self, sim_time):
        """私语概率：随语言经验天数缓慢衰减（内化加深→复述减少）。"""
        if self.first_heard_t is None:
            return 0.0
        days = (sim_time - self.first_heard_t) / 86400.0
        return self.echo_prob0 / (1.0 + days / self.echo_decay_days)

    def _record(self, kind, frag, mem_entry, sim_time, score, day_index):
        """写入 inner_speech.jsonl 并更新统计。"""
        delay_days = (sim_time - mem_entry["t"]) / 86400.0
        rec = {
            "t": round(sim_time, 1),
            "type": kind,                    # echo=私语复述 | retrieval=状态驱动检索
            "text": frag,
            "heard_at": mem_entry["t"],      # 首次听到这句话的时刻
            "delay_days": round(delay_days, 3),
            "heard_s2": mem_entry["s"][1],   # 听到时的 s2（念头携带的语境色彩）
            "activation": round(score, 3),
            "self_directed": mem_entry["self_directed"],
            "evidence": "soft",
        }
        self.recent_inner.append(frag)
        os.makedirs(os.path.dirname(INNER_SPEECH_PATH), exist_ok=True)
        with open(INNER_SPEECH_PATH, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def evoke_inner_speech(self, state_vec, focus, sim_time, day_index):
        """主入口：本 tick 是否有念头浮现。返回记录 dict 或 None。
        echo：最近听到的话按衰减概率复述（私语）；
        retrieval：当前状态与历史语境相似 → 激活片段（内言语）。"""
        if not self.enabled or not self.memory:
            return None
        s = [float(v) for v in state_vec]
        salience = focus.get("salience", 0.0) if focus else 0.0

        # --- 私语（echo）：刚听到的话按衰减概率复述一次 ---
        # 每句只掷一次骰子（echo_decided）：若逐 tick 重试，300 秒窗口内累计
        # 概率趋于 1，衰减曲线失效、复述率恒为 100%（P2.6 修正）
        last = self.memory[-1]
        if (not last.get("echoed")
                and not last.get("echo_decided")
                and sim_time - last["t"] < 300.0):
            last["echo_decided"] = True
            if random.random() < self._echo_prob(sim_time) * (0.5 + salience):
                last["echoed"] = True
                self.n_echo += 1
                return self._record("echo", last["text"], last, sim_time, 1.0, day_index)

        # --- 检索（retrieval）：状态驱动 ---
        if sim_time - self._last_evoke_t < self.evoke_interval:
            return None
        self._last_evoke_t = sim_time
        # 概率门：意识焦点显著时更易浮现（基线低——念头是稀疏事件）
        if random.random() > 0.06 + 0.20 * salience:
            return None
        # 记忆容量：仅防极端膨胀的护栏（原 3000 FIFO 帽会物理删除 3/4 听觉史，
        # 与"自传体记忆"目标冲突——扩容至 12 万，约 300 年听觉量）
        if len(self.memory) > 120000:
            self.memory = self.memory[-120000:]
        # 对候选片段打分：状态相似 × 新近 × 频率
        freq = {}
        for m in self.memory:
            freq[m["text"]] = freq.get(m["text"], 0) + 1
        best, best_score = None, -1.0
        # 抽样评估（记忆大时不全扫）
        sample = self.memory if len(self.memory) <= 200 else random.sample(self.memory, 200)
        now_days = sim_time / 86400.0
        for m in sample:
            sim = self._state_sim(s, m["s"])
            age_days = now_days - m["t"] / 86400.0
            recency = 0.5 ** (max(0.0, age_days - 0.02) / self.recency_half_life_days)
            score = sim * (0.35 + 0.65 * recency) * (1.0 + self.freq_gain * math.log(1 + freq[m["text"]]))
            score *= 0.9 + 0.2 * random.random()   # 内部涨落
            if score > best_score:
                best, best_score = m, score
        if best is None or best_score < self.evoke_threshold:
            return None  # 这一刻没有念头浮现
        self.n_retrieval += 1
        return self._record("retrieval", best["text"], best, sim_time, best_score, day_index)

    # ============ 回流信号 ============
    def valence_of(self, record, state_vec):
        """念头的情绪色彩 = 它被听到时的 s2 与当前 s2 之差（语境统计，非词典）。"""
        heard_s2 = record.get("heard_s2", 0.0)
        current_s2 = float(state_vec[1])
        return (heard_s2 - current_s2) * 2.0

    # ============ 目标涌现 ============
    def update_goals(self, record, sim_time, day_index, logger=None):
        """同一片段在滚动窗口内反复被激活（窗口占比 + 跨天）→ 升格为目标。
        窗口 = 最近 goal_window 次自发检索（echo 是外部诱发的复述，不算持续
        关切；用窗口占比而非全期占比，避免最早涌现的片段永久垄断目标空间）。"""
        if record["type"] != "retrieval":
            return None
        text = record["text"]
        st = self.fragment_activations.setdefault(
            text, {"count": 0, "days": [], "promoted": False})
        if st["promoted"]:
            return None
        st["count"] += 1
        if day_index not in st["days"]:
            st["days"].append(day_index)
        # 滚动窗口占比：最近 N 次自发检索中该片段的份额
        self.retrieval_log.append({"text": text, "day": day_index})
        window_total = len(self.retrieval_log)
        window_count = sum(1 for r in self.retrieval_log if r["text"] == text)
        if (window_count >= self.goal_min_activations
                and window_count / window_total >= self.goal_min_fraction
                and len(st["days"]) >= self.goal_min_days):
            goal = {
                "goal": text,
                "created_at": round(sim_time, 1),
                "created_day": day_index,
                "evidence": {"activations": st["count"],
                             "window_activations": window_count,
                             "window_total": window_total,
                             "window_fraction": round(window_count / window_total, 3),
                             "days": len(st["days"]), "day_list": st["days"]},
            }
            st["promoted"] = True
            self.goals.append(goal)
            os.makedirs(os.path.dirname(GOALS_PATH), exist_ok=True)
            existing = []
            if os.path.exists(GOALS_PATH):
                with open(GOALS_PATH) as f:
                    existing = json.load(f)
            existing.append(goal)
            with open(GOALS_PATH, "w") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            if logger:
                logger.info("[目标涌现] 片段 '%s' 升格为目标（窗口 %d/%d，跨 %d 天）",
                            text, window_count, window_total, len(st["days"]))
            return goal
        return None

    # ============ 持久化 ============
    def snapshot(self):
        return {
            "n_heard": self.n_heard,
            "n_echo": self.n_echo,
            "n_retrieval": self.n_retrieval,
            "existence_count": self.existence_count,
            "first_heard_t": self.first_heard_t,
            "recent_inner": list(self.recent_inner),
            "fragment_activations": self.fragment_activations,
            "retrieval_log": list(self.retrieval_log),
            "goals": self.goals,
        }

    def save(self):
        os.makedirs(os.path.dirname(LANG_STATE_PATH), exist_ok=True)
        with open(LANG_STATE_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)
        with open(LING_MEMORY_PATH, "w") as f:
            json.dump(self.memory[-120000:], f, ensure_ascii=False)

    def load(self):
        if not os.path.exists(LANG_STATE_PATH):
            return False
        with open(LANG_STATE_PATH) as f:
            d = json.load(f)
        self.n_heard = d.get("n_heard", 0)
        self.n_echo = d.get("n_echo", 0)
        self.n_retrieval = d.get("n_retrieval", 0)
        self.existence_count = d.get("existence_count", 0)
        self.first_heard_t = d.get("first_heard_t")
        self.recent_inner = deque(d.get("recent_inner", []), maxlen=8)
        self.fragment_activations = d.get("fragment_activations", {})
        self.retrieval_log = deque(d.get("retrieval_log", []),
                                   maxlen=self.goal_window)
        self.goals = d.get("goals", [])
        if os.path.exists(LING_MEMORY_PATH):
            with open(LING_MEMORY_PATH) as f:
                self.memory = json.load(f)
        return True
