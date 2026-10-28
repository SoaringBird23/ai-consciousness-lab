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
import statistics
from collections import deque

import workspace as workspace_mod
import compose as compose_mod
import dialogue as dialogue_mod
import constructions as constructions_mod

STATE_DIR = os.environ.get("STATE_DIR", "state")
_ROOT = os.path.dirname(__file__)
INNER_SPEECH_PATH = os.path.join(_ROOT, STATE_DIR, "inner_speech.jsonl")
GOALS_PATH = os.path.join(_ROOT, STATE_DIR, "goals.json")
LANG_STATE_PATH = os.path.join(_ROOT, STATE_DIR, "language_state.json")
LING_MEMORY_PATH = os.path.join(_ROOT, STATE_DIR, "linguistic_memory.json")
WORD_COMPOSE_PATH = os.path.join(_ROOT, STATE_DIR, "word_compose.json")   # P18
DIALOGUE_PATH = os.path.join(_ROOT, STATE_DIR, "dialogue.json")           # P19
CONSTRUCTION_PATH = os.path.join(_ROOT, STATE_DIR, "constructions.json")  # P20


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
CORPUS_WORLD_HI = [       # P16：世界相关照护者——世界场偏高时命名（"球/亮亮"↔世界状态 HIGH）
    "球", "亮亮", "看那儿",
]
CORPUS_WORLD_LO = [       # P16：世界场偏低时命名（"灯/那个"↔世界状态 LOW）
    "灯", "那个", "在那儿",
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
        # P14b：内容敏感的听者——应答概率按「发声的型」差异化 r(f)。
        # 关闭（默认）时退化为固定 vocal_response_prob，行为与 P14 逐位一致。
        cr_cfg = cg_cfg.get("content_response", {})
        self.content_response_enabled = bool(cr_cfg.get("enabled", False))
        self.content_response_default = float(cr_cfg.get("default_r",
                                                         self.vocal_response_prob))
        # P14c：对 HIGH 词的“短爆”回应条数（1=不短爆；k>1 时一次发声窗口内回 k 句）
        self.cr_burst_k = int(cr_cfg.get("burst_high_k", 1))
        self._burst_pending = 0
        self._burst_pool = None
        self.content_r = {}
        # P16 前置：世界相关照护者（joint attention）——外部世界显著时命名外部对象
        self.world_contingent = bool(cg_cfg.get("world_contingent", False))
        self.wc_rate = float(cg_cfg.get("wc_rate_per_hour", 6.0))
        self.wc_field_hi = float(cg_cfg.get("wc_field_hi", 0.65))
        self.wc_field_lo = float(cg_cfg.get("wc_field_lo", 0.35))
        self.wc_field_delta = float(cg_cfg.get("wc_field_delta", 0.05))
        self._prev_wf = None
        if self.content_response_enabled:
            self._load_content_map(cr_cfg.get("map_file"))
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
        # P17：词汇发育——语料词表档（top-cap）+ 扩词规则
        self.corpus_vocab_cap = int(cg_cfg.get("corpus_vocab_cap", 0))   # 0=不设限
        self.vocab_growth = str(cg_cfg.get("vocab_growth", "none"))
        self.vocab_cap_max = int(cg_cfg.get("vocab_cap_max", 1000))
        self.vocab_median_threshold = float(cg_cfg.get("vocab_median_threshold", 20.0))
        self._rows_full = None
        self._exponent = 1.0
        self._type_n = {}                # 当前档内各型的被说次数
        self._type_n_sum = 0             # Σ type_n（均值短路用；避免每 tick O(cap) 求中位）
        self._cap_last_grow_day = -999
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
        # ---- C1 成句重组（R3，归口本层）----
        # 仅在 spont.compose=true 时激活；否则所有新分支不执行，本层输出与改动前
        # 逐位一致。bigram：从"真实相继听到的短语"学一张后继频次表（纯数据驱动、
        # 无人工语法），evoke 时以检索胜者为起点、按频次抽其后继拼成新句。
        self.compose = bool(config.get("spont", {}).get("compose", False))
        self._bigram = {}                 # prev_text -> {next_text: count}
        self._last_heard_text = None
        self.n_composed = 0               # 重组句计数（M_生成 分子）
        self._last_error = None
        # ---- P18 词级组合（零幻觉词法级、重组句法级）----
        # 默认关（word_compose.enabled=False）→ composer=None，本层行为逐位不变。
        self.composer = (compose_mod.WordComposer(config)
                         if config.get("word_compose", {}).get("enabled", False)
                         else None)
        # ---- P19 对话状态向量（多轮）----
        # 默认关（dialogue.enabled=False）→ dialogue=None，本层行为逐位不变。
        self.dialogue = (dialogue_mod.DialogueState(config)
                         if config.get("dialogue", {}).get("enabled", False)
                         else None)
        self.dialogue_gamma = float(config.get("dialogue", {}).get("gamma", 0.5))
        # ---- P20 构造语法（理解句式 + 槽位重组）----
        # 默认关 → grammar=None，本层行为逐位不变（P19b 等既有臂不受影响）。
        con_cfg = config.get("construction", {})
        self.grammar = (constructions_mod.ConstructionGrammar(
            os.path.join(_ROOT, con_cfg.get("lexicon_file", "corpus/lexicon.json")))
            if con_cfg.get("enabled", False) else None)
        if self.grammar is not None:
            self.grammar.finalize()      # 空模型也要有索引，避免首轮 respond 崩溃
        self.grammar_window_s = float(con_cfg.get("response_window_s", 300.0))
        self.grammar_finalize_every = int(con_cfg.get("finalize_every_learns", 500))
        self._grammar_learns = 0
        self.n_construction = 0
        # ---- R5 激活式工作集（见 workspace.py；默认关，行为逐位不变）----
        self.ws = workspace_mod.Workspace(config)
        # P13：学习/使用相位分界（day_index 口径，见 prereg_P13.json）。
        # <0：不分相（旧行为，priming 立即生效、A 边用边写，与 P9/P10 逐位一致）；
        # >=0：此前为学习期（只学 A、priming 关），此后为使用期（priming 开、A 冻结只读），
        #       以避免 P12 soft 臂那种「用 A → 改 A」正反馈把念头流锁死（uniq 5）。
        self.ws_phase_split = float(config.get("workspace", {}).get("phase_split_day", -1))
        # P9：上一个检索胜出的念头（priming 的前驱；与 adj_top3 判据对齐）
        self._last_thought = None
        # P14：最近一次检索的候选池（文本, 得分），供发声时按 E[f] 选择；echo 不动它
        self._last_candidates = []

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
        # P17：按频次降序保存整池，便于按 top-cap 截取与后续发育扩词
        self._rows_full = sorted(
            [(str(r.get("text", "")).strip(), float(r.get("count", 1)))
             for r in rows if str(r.get("text", "")).strip()],
            key=lambda x: x[1], reverse=True)
        self._exponent = exponent
        self._apply_vocab_cap()

    def _apply_vocab_cap(self):
        """按 top-cap 构建采样池（cap<=0 表示不设限）。P17：cap 可随发育增长。"""
        if not self._rows_full:
            return
        rows = self._rows_full
        if self.corpus_vocab_cap and self.corpus_vocab_cap > 0:
            rows = rows[:self.corpus_vocab_cap]
        texts, weights, d_w = [], [], []
        for t, c in rows:
            w = max(1e-9, c) ** self._exponent
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

    def maybe_grow_vocab(self, day_index):
        """P17 词汇发育：adaptive=当前档已巩固（每型中位样本≥阈值）→ cap 翻倍；
        fixed_fast=每 15 日翻倍。上限 vocab_cap_max。未启用 cap 时不动作。"""
        if self.vocab_growth not in ("adaptive", "fixed_fast"):
            return
        if not self._rows_full or self.corpus_vocab_cap <= 0:
            return
        if self.corpus_vocab_cap >= self.vocab_cap_max:
            return
        grow = False
        if self.vocab_growth == "fixed_fast":
            grow = (day_index - self._cap_last_grow_day) >= 15
        else:  # adaptive：巩固了再扩
            n = len(self.corpus_texts)
            # 均值短路：中位 ≤ 均值，故均值 < 阈值 ⇒ 中位必 < 阈值 ⇒ 无需排序。
            # 常见路径退化为 O(1)，避免每 tick 对整档 O(cap) 求中位（cap 可达 1000）。
            if n and (self._type_n_sum / n) >= self.vocab_median_threshold:
                vals = [self._type_n.get(t, 0) for t in self.corpus_texts]
                grow = statistics.median(vals) >= self.vocab_median_threshold
        if grow:
            self.corpus_vocab_cap = min(self.corpus_vocab_cap * 2, self.vocab_cap_max)
            self._cap_last_grow_day = day_index
            self._type_n = {}
            self._type_n_sum = 0
            self._apply_vocab_cap()

    def _sample_corpus(self, directed=False):
        if directed and self.corpus_directed:
            i = random.choices(self.corpus_directed,
                               cum_weights=self.corpus_directed_cum, k=1)[0]
            return self._record_type(i)
        i = random.choices(range(len(self.corpus_texts)),
                           cum_weights=self.corpus_cum, k=1)[0]
        return self._record_type(i)

    def _record_type(self, i):
        """P17：记录某型被说的次数（驱动自适应扩词）。"""
        t = self.corpus_texts[i]
        self._type_n[t] = self._type_n.get(t, 0) + 1
        self._type_n_sum += 1
        return t

    def _say(self, pool, directed=False, use_burst=False, force_pool=False):
        """选一句要说的话：加载了外部语料 → 按频次加权从整池采；
        否则退回内置池（未设 corpus_file 时行为与改动前逐位一致）。
        directed=True 时只从含"你/我"的子集里采——自我指向输入是自我模型
        形成的硬前提（213 天 null 已证），故保留这一条词法过滤。
        use_burst=True（仅用于通用内容的通道：安静基流 / 事件命名）时，改走
        话题连续采样。
        P17 修复：force_pool=True 时**始终用指定池、不走语料**——用于状态针对性
        与指称通道（醒来问候 / 安抚 / 无聊召唤 / 被注视 / 世界命名），保住"什么时候
        说、针对什么说"的情境驱动性（人类照护者对着婴儿的状态与所指对象说话）。
        仅通用内容通道（事件命名 #2 / 安静基流 #6）走语料——词汇发育发生在这里。"""
        if self.corpus_texts and not force_pool:
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
    def _load_content_map(self, map_file):
        """P14b：载入『型→应答倾向 r(f)』映射（默认路径 experiments/p14b_content_map.json）。"""
        path = map_file or "experiments/p14b_content_map.json"
        full = path if os.path.isabs(path) else os.path.join(_ROOT, path)
        if not os.path.exists(full):
            self.content_response_enabled = False
            self._last_error = f"content map 缺失：{full}"
            return
        try:
            with open(full, encoding="utf-8") as f:
                d = json.load(f)
            self.content_r = {str(k): float(v) for k, v in d.get("r", {}).items()}
        except Exception as e:
            self.content_response_enabled = False
            self._last_error = f"content map 解析失败：{e}"

    def _vocal_response_prob(self, vocal_text):
        """P14b：对某次发声的应答概率。关闭时恒为固定值（与 P14 逐位一致）。"""
        if self.content_response_enabled and vocal_text:
            return self.content_r.get(vocal_text, self.content_response_default)
        return self.vocal_response_prob

    def drain_burst(self):
        """P14c：取出本发声窗口剩余的“短爆”回应（HIGH 词），由调用方逐条 hear。"""
        if self._burst_pending <= 0 or not self._burst_pool:
            self._burst_pending = 0
            return []
        k = self._burst_pending
        self._burst_pending = 0
        return [random.choice(self._burst_pool) for _ in range(k)]

    def caregiver_speaks(self, dt_hours, sim_hour, event_happened,
                         state_vec=None, asleep=None, salience=0.0,
                         vocal_recent=False, vocal_text=None,
                         world_event=False, world_field=None):
        """决定本 tick 照护者是否说话，返回话语或 None。纯环境侧。
        - random 模式（原逻辑，对照）：随机时机 + 随机语料，与候选体状态无关（零应答）
        - contingent 模式（E3 应答式）：说话时机与内容由候选体状态驱动——
          环境可以有应答性（真实父母的属性）；候选体内部机制零改动。
        - E4：contingent 模式下对发声（vocal_recent）高概率应答——
          动作-结果共变的来源。
        - P14b：contingent 模式下若开启 content_response，应答概率改为按发声的型
          r(vocal_text)——听者对『说什么』敏感（环境侧属性）。关闭时与 P14 逐位一致。
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
                # P12 修复：本窗口首次调用即「决策」（无论应答与否）。原实现只在
                # 应答成功时置位，于是窗口内每 tick 重掷（60s 窗口 = 1200 次），
                # 累计概率 1-(1-0.7)^1200 ≈ 1.0 —— vocal_response_prob 被架空成死参数，
                # 与 echo 旧 bug 完全同构。
                if not self._vocal_responded:
                    self._vocal_responded = True
                    # P14b：应答概率按发声的型（关闭时 = vocal_response_prob）
                    rp = self._vocal_response_prob(vocal_text)
                    if random.random() < rp:
                        pool = ["看", "看这个", "又动了", "又动啦", "来了来了",
                                "是你呀", "你在看", "你好呀", "对", "对呀"]
                        # P14c：HIGH 词（r 高）→ 短爆 k 句，放大窗口内效应幅度
                        if (self.content_response_enabled and vocal_text
                                and self.cr_burst_k > 1 and rp >= 0.5):
                            self._burst_pool = pool
                            self._burst_pending = self.cr_burst_k - 1
                        return random.choice(pool)
            else:
                self._vocal_win_active = False       # 窗口结束，下次发声可再应答
            # 1) 醒来时刻：晨间问候（每天必现的自我指向共现）
            if woke:
                return self._say(["你醒啦", "你醒啦", "你醒啦", "你好呀"], directed=True,
                                 force_pool=True)
            # 1b) P16 前置：世界相关照护者（joint attention）——**不同的词对应不同的
            #     世界状态**：世界场偏高时命名 HIGH 词表，偏低时命名 LOW 词表。
            #     P17：force_pool——指称词始终来自世界词表，不被语料覆盖。
            if self.world_contingent and world_field is not None:
                if random.random() < self.wc_rate * dt_hours:
                    pool = (CORPUS_WORLD_HI if world_field > 0.5 else CORPUS_WORLD_LO)
                    return self._say(pool, directed=True, force_pool=True)
            # 2) 事件时刻：命名/好奇（与随机模式同概率、同语料）
            if event_happened and random.random() < self.speech_prob_with_event:
                return self._say(CORPUS_EVENT, use_burst=True)
            # 3) 紧张高（s4）：安抚——含第一人称在场承诺（"我在这儿"与被安抚共现）
            #    C1 对照（inverted）：同一批"我"短语移到平静时刻说——频率匹配、语境反转
            fp_soothe = FP_SOOTHE if (self.corpus_fp and self.fp_context == "bound") else []
            if state_vec[3] > 0.62 and random.random() < 10.0 * dt_hours:
                return self._say(CORPUS_NIGHT + fp_soothe, force_pool=True)
            if (self.corpus_fp and self.fp_context == "inverted" and state_vec[3] < 0.40
                    and random.random() < self.fp_inv_rate_soothe * dt_hours):
                return self._say(FP_SOOTHE, directed=True, force_pool=True)
            # 4) 无聊高（s8）：互动召唤（8/时）——状态针对性通道：force_pool，
            #    保住"无聊→召唤"这一状态-内容绑定（人类照护者的反应有定式）
            if state_vec[7] > 0.40 and random.random() < 8.0 * dt_hours:
                return self._say(["看", "看这个", "又动了", "又动啦",
                                  "摸摸", "来了来了"], force_pool=True)
            # 5) 注意焦点显著：自我指向——"你"与被注视状态共现（5/时）
            #    C1（inverted）：高焦点时刻只说"你"族；"我"族移到无焦点时刻（频率匹配）
            #    被注视=状态针对性通道：force_pool，保住"你"的语境驱动
            pool_self = (CORPUS_SELF if (self.corpus_fp and self.fp_context == "bound")
                         else CORPUS_SELF_2P)
            if salience > 0.6 and random.random() < 5.0 * dt_hours:
                return self._say(pool_self, directed=True, force_pool=True)
            if (self.corpus_fp and self.fp_context == "inverted" and salience < 0.3
                    and random.random() < self.fp_inv_rate_salience * dt_hours):
                return self._say(FIRST_PERSON, directed=True, force_pool=True)
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
    def hear(self, text, state_vec, sim_time, world_sig=None):
        """外部语言进入。存储片段 + 听到时的状态快照（+ P16：外部世界签名）。"""
        rec = {
            "text": text,
            "t": round(sim_time, 1),
            "s": [round(float(v), 4) for v in state_vec],
            "self_directed": any(w in text for w in self.sd_words),  # S2：门控词表可配（默认含"我"，与 self_model 词表对齐）
            "echoed": False,          # 私语复述只发生一次（真实私语是复述一两遍）
        }
        # P16：外部世界签名（照护者言之有物时，片段可获得对外部世界的所指）
        if world_sig is not None:
            rec["world"] = round(float(world_sig), 4)
        self.memory.append(rec)
        self.n_heard += 1
        if self.first_heard_t is None:
            self.first_heard_t = sim_time
        # C1：学习"真实相继听到的短语"的二元后继。仅 compose 开启时写入；关闭时
        # 本分支不执行（不消耗随机数、不改任何输出），hear 与改动前逐位一致。
        if self.compose:
            if self._last_heard_text is not None and self._last_heard_text != text:
                row = self._bigram.setdefault(self._last_heard_text, {})
                row[text] = row.get(text, 0) + 1
            self._last_heard_text = text
        # P18：词级组合——听到即切词、更新词二元表与实听词表（默认关时 composer=None）
        if self.composer is not None:
            self.composer.learn(text)
        # P19：听到照护者一轮 → 更新对话状态向量（多轮）
        if self.dialogue is not None:
            self.dialogue.observe_turn(text, "partner", sim_time)
        # P20：听到即学句式（挖空 → 填充词分布）与词序/共现；离线构造模型
        if self.grammar is not None:
            self.grammar.learn(text, state=state_vec, world=world_sig)
            self._grammar_learns += 1
            if (self.grammar_finalize_every > 0
                    and self._grammar_learns % self.grammar_finalize_every == 0):
                self.grammar.finalize()
        # R5：听到 → 沉积激活 + 沿共现扩散（默认关时 activate 直接返回）
        # P13：标注来源 'heard'；thought_only 下听到的事件不写念头—念头共现矩阵 A
        self.ws.activate(text, source="heard")
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

    # ---- P13：工作空间学习/使用相位 ----
    def _ws_priming_on(self, day_index):
        """本 tick priming 是否生效。phase_split_day<0 → 恒生效（P9/P10 逐位一致）；
        >=0 → 仅在使用期（day_index>=split）生效，此前为学习期、只学 A 不用 A。"""
        if self.ws_phase_split < 0:
            return True
        return day_index >= self.ws_phase_split

    def _ws_assoc_frozen(self, day_index):
        """使用期冻结 A（只读不写），切断『用 A → 念头流被改 → 又写回 A』的自锁。"""
        return self.ws_phase_split >= 0 and day_index >= self.ws_phase_split

    def _echo_prob(self, sim_time):
        """私语概率：随语言经验天数缓慢衰减（内化加深→复述减少）。"""
        if self.first_heard_t is None:
            return 0.0
        days = (sim_time - self.first_heard_t) / 86400.0
        return self.echo_prob0 / (1.0 + days / self.echo_decay_days)

    def _sample_successor(self, text):
        """C1：从二元后继表按频次加权抽一个续段。无后继时返回 None。"""
        succ = self._bigram.get(text)
        if not succ:
            return None
        pop = list(succ.keys())
        wts = [succ[k] for k in pop]
        return random.choices(pop, weights=wts, k=1)[0]

    def _record(self, kind, frag, mem_entry, sim_time, score, day_index, extra=None):
        """写入 inner_speech.jsonl 并更新统计。extra：仅在 C1 重组句上追加
        （composed 等标记）。默认 None → 记录字段与改动前逐位一致。"""
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
        if extra:
            rec.update(extra)
        self.recent_inner.append(frag)
        os.makedirs(os.path.dirname(INNER_SPEECH_PATH), exist_ok=True)
        with open(INNER_SPEECH_PATH, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    # ============ P14：候选打分管线（evoke 与 response_model 共用） ============
    def score_candidates(self, s, sim_time, day_index):
        """对记忆候选打分。返回 (best_entry, best_score, candidates)。
        candidates = [(text, score), ...] 按得分降序、按文本去重（同型多实例取最高）。
        本方法的随机数消耗与 P14 之前逐位一致：off 臂行为不变。"""
        freq = {}
        for m in self.memory:
            freq[m["text"]] = freq.get(m["text"], 0) + 1
        best, best_score = None, -1.0
        # 抽样评估（记忆大时不全扫）
        # R5：若工作集开启，候选 = 工作集内的型（保证沉积内容在候选里）；否则原路径。
        # P12 修复：soft_prior = **真正的全长池**——既不裁候选（硬帽 k），也不落到
        # `random.sample(memory, 200)`。P11 的 soft 臂写成了后者，候选被缩到
        # 200/51721 ≈ 0.4%，采样瓶颈（R3/R4 的老问题）回归、激活加权随之被淹没：
        # 实测 adj_top3=0.000，且 soft 与 soft_shuf 三项读数几乎全同（打乱行零效果），
        # 是为旁证。本次让候选 = 全部记忆条目，激活只经打分乘子 (1+γ·Âct) 起作用。
        wset = None if self.ws.soft_prior else self.ws.working_set()
        if self.ws.soft_prior:
            sample = self.memory
        elif wset is not None:
            keep = set(wset)
            cand = [m for m in self.memory if m["text"] in keep]
            if not cand:
                sample = (self.memory if len(self.memory) <= 200
                          else random.sample(self.memory, 200))
            else:
                sample = cand if len(cand) <= 200 else random.sample(cand, 200)
        else:
            sample = self.memory if len(self.memory) <= 200 else random.sample(self.memory, 200)
        now_days = sim_time / 86400.0
        self.ws.begin_retrieval()   # P11：刷新软先验的归一化基准（关闭时为空操作）
        scored = []
        for m in sample:
            sim = self._state_sim(s, m["s"])
            age_days = now_days - m["t"] / 86400.0
            recency = 0.5 ** (max(0.0, age_days - 0.02) / self.recency_half_life_days)
            score = sim * (0.35 + 0.65 * recency) * (1.0 + self.freq_gain * math.log(1 + freq[m["text"]]))
            # P9：联想启动——上一个念头对其联想后继加权（prime_bonus 在关闭时返回 0，乘子退化为 1）
            # P13：相位门——学习期不施加 priming（prime_bonus 自身的 priming 开关仍生效）
            if self._last_thought is not None and self._ws_priming_on(day_index):
                score *= 1.0 + self.ws.priming_gamma * self.ws.prime_bonus(self._last_thought, m["text"])
            # P11：软先验——当前激活场对候选加权（soft_bonus 在关闭时返回 0，乘子退化为 1）
            if self.ws.soft_prior:
                score *= 1.0 + self.ws.soft_gamma * self.ws.soft_bonus(m["text"])
            # P19：对话状态向量——候选与近几轮对话上下文的关联加权（默认关时 dialogue=None）
            if self.dialogue is not None:
                score *= 1.0 + self.dialogue_gamma * self.dialogue.relevance(m["text"])
            score *= 0.9 + 0.2 * random.random()   # 内部涨落
            scored.append((m, score))
            if score > best_score:
                best, best_score = m, score
        # 候选池：按文本去重取最高，再按得分降序（P14 的 top-k 来自这里）
        by_text = {}
        for m, sc in scored:
            t = m["text"]
            if t not in by_text or sc > by_text[t]:
                by_text[t] = sc
        candidates = sorted(by_text.items(), key=lambda kv: kv[1], reverse=True)
        return best, best_score, candidates

    def _construction_reply(self, state_vec, sim_time, day_index, score):
        """P20：对最近听到的一轮，用构造语法听→答。

        只在 grammar 开启时调用；返回 inner_speech 记录或 None。
        回答的句式与词都必须是它听过的（构造语法内部保证），
        整体词序可以没听过——这是“句法级重组”。
        """
        if self.grammar is None or not self.memory:
            return None
        last = self.memory[-1]
        if sim_time - last.get("t", 0.0) > self.grammar_window_s:
            return None
        # 近几轮话题（只取实词，避免把“的/了”带进对话状态）
        recent_topics = []
        for m in reversed(self.memory[-8:]):
            for w in self.grammar.tok.segment(m.get("text", "")):
                if (w not in constructions_mod.FUNCTION_WORDS
                        and w not in recent_topics):
                    recent_topics.append(w)
            if len(recent_topics) >= 8:
                break
        und, gen = self.grammar.respond(
            last.get("text", ""), state=state_vec, world=last.get("world"),
            recent_topics=recent_topics, rng=random,
            avoid=tuple(self.recent_inner))
        if not gen:
            return None
        self.n_construction += 1
        extra = {"composed": True, "compose_level": "construction",
                 "compose_from": last.get("text"), "reply_to": last.get("text"),
                 "construction_mode": gen.get("answer_mode"),
                 "construction_frame": ("".join(gen["frame"])
                                        if gen.get("frame") else None),
                 "construction_speech_act": und.get("speech_act"),
                 "construction_coverage": und.get("coverage")}
        return self._record("construction", gen["text"], last, sim_time,
                            score, day_index, extra=extra)

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
        # P14：抽离为 score_candidates()，供 evoke_inner_speech 与 response_model
        # 复用——同一条打分管线，同一批随机数消耗，off 臂行为逐位不变。
        best, best_score, candidates = self.score_candidates(s, sim_time, day_index)
        if best is None or best_score < self.evoke_threshold:
            return None  # 这一刻没有念头浮现
        self._last_candidates = candidates   # P14：供发声时按 E[f] 选择
        self.n_retrieval += 1
        # P9：记录本 tick 的念头，作为下一次检索的 priming 前驱
        prev_thought = self._last_thought
        self._last_thought = best["text"]
        # P13：念头—念头共现按「念头流」顺序记录（与 hearing 事件无关——原始激活序列里
        # 听到事件远多于念头，字面相邻几乎不存在，会使 A 被架空）。使用期冻结 A，
        # 切断『用 A → 念头流被改 → 又写回 A』的正反馈自锁（P12 soft 臂坍缩成因）。
        if self.ws.thought_only and not self._ws_assoc_frozen(day_index):
            self.ws.record_assoc(prev_thought, best["text"])
        # R5：检索到的念头 → 回写激活（复述/回响 = 双向闭环；默认关时直接返回）
        self.ws.activate(best["text"], source="thought")
        # P20：构造语法听→答（默认 grammar=None，不执行）
        if self.grammar is not None:
            crec = self._construction_reply(s, sim_time, day_index, best_score)
            if crec is not None:
                return crec
        # P18 词级组合 / C1 短语级重组（二选一——本实验只开 word_compose）
        frag, extra = best["text"], None
        if self.composer is not None:
            comp = self.composer.compose(best["text"])
            if comp is not None:
                frag = comp["text"]
                extra = {"composed": True, "compose_level": "word",
                         "compose_from": best["text"], "words": comp["words"],
                         "novel": comp["novel"], "n_pairs": comp["n_pairs"],
                         "n_pairs_real": comp["n_pairs_real"],
                         "purity": round(comp["purity"], 4)}
        elif self.compose:
            cont = self._sample_successor(best["text"])
            if cont is not None:
                frag = best["text"] + "，" + cont
                self.n_composed += 1
                extra = {"composed": True, "compose_level": "phrase",
                         "compose_from": best["text"], "compose_to": cont}
        return self._record("retrieval", frag, best, sim_time, best_score,
                            day_index, extra=extra)

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
            "n_composed": self.n_composed,
            "n_construction": self.n_construction,
            "grammar_frames": (len(self.grammar.frames) if self.grammar else 0),
            "grammar_words": (len(self.grammar.word_count) if self.grammar else 0),
            "existence_count": self.existence_count,
            "first_heard_t": self.first_heard_t,
            "recent_inner": list(self.recent_inner),
            "fragment_activations": self.fragment_activations,
            "retrieval_log": list(self.retrieval_log),
            "goals": self.goals,
            "bigram": self._bigram,
            "last_heard_text": self._last_heard_text,
            # P12：检索连续性——priming 前驱与检索节流时钟随盘持久化，
            # 避免重启/fork 后首个检索丢前驱、节流归零（各臂对称，但相对
            # "自然续跑"存在小状态断点，见审计 C-1）
            "last_thought": self._last_thought,
            "last_evoke_t": self._last_evoke_t,
            # P17：词汇发育状态（扩词档位与型计数）随盘持久化
            "corpus_vocab_cap": self.corpus_vocab_cap,
            "cap_last_grow_day": self._cap_last_grow_day,
            "type_n": self._type_n,
        }

    def save(self):
        os.makedirs(os.path.dirname(LANG_STATE_PATH), exist_ok=True)
        with open(LANG_STATE_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False)   # 去 indent（体积/IO）
        with open(LING_MEMORY_PATH, "w") as f:
            json.dump(self.memory[-120000:], f, ensure_ascii=False)
        self.ws.save()          # R5：工作集状态随语言层持久化
        if self.composer is not None:      # P18：词级组合状态
            self.composer.save(WORD_COMPOSE_PATH)
        if self.dialogue is not None:      # P19：对话状态向量
            self.dialogue.save(DIALOGUE_PATH)
        if self.grammar is not None:       # P20：构造语法
            self.grammar.finalize()
            self.grammar.save(CONSTRUCTION_PATH)

    def load(self):
        if not os.path.exists(LANG_STATE_PATH):
            return False
        with open(LANG_STATE_PATH) as f:
            d = json.load(f)
        self.n_heard = d.get("n_heard", 0)
        self.n_echo = d.get("n_echo", 0)
        self.n_retrieval = d.get("n_retrieval", 0)
        self.n_composed = d.get("n_composed", 0)
        self.n_construction = d.get("n_construction", 0)
        self.existence_count = d.get("existence_count", 0)
        self.first_heard_t = d.get("first_heard_t")
        self._bigram = d.get("bigram", {})
        self._last_heard_text = d.get("last_heard_text")
        self._last_thought = d.get("last_thought")
        self._last_evoke_t = d.get("last_evoke_t", 0.0)
        # P17：恢复词汇发育档位并重建采样池
        if d.get("corpus_vocab_cap"):
            self.corpus_vocab_cap = int(d["corpus_vocab_cap"])
            self._cap_last_grow_day = int(d.get("cap_last_grow_day", -999))
            self._type_n = d.get("type_n", {})
            self._type_n_sum = sum(self._type_n.values())
            if self._rows_full:
                self._apply_vocab_cap()
        self.recent_inner = deque(d.get("recent_inner", []), maxlen=8)
        self.fragment_activations = d.get("fragment_activations", {})
        self.retrieval_log = deque(d.get("retrieval_log", []),
                                   maxlen=self.goal_window)
        self.goals = d.get("goals", [])
        if os.path.exists(LING_MEMORY_PATH):
            with open(LING_MEMORY_PATH) as f:
                self.memory = json.load(f)
        self.ws.load()          # R5：工作集状态恢复（缺失时返回 False，不影响）
        if self.composer is not None:      # P18：词级组合状态恢复
            if self.composer.load(WORD_COMPOSE_PATH):
                # seen 不再随盘（等价于 set(记忆整句)）→ 从 memory 重建
                if not self.composer.seen:
                    self.composer.seen = {_m.get("text") for _m in self.memory
                                          if _m.get("text")}
            else:
                # 无自身状态文件（新 fork）：用已有听觉史（memory）初始化词二元与实听词表。
                # 否则检索胜者若来自 fork 前的旧记忆，其词不在「实听词表」→ 词法纯净被误伤。
                for _m in self.memory:
                    _t = _m.get("text")
                    if _t:
                        self.composer.learn(_t)
        if self.dialogue is not None:      # P19：对话状态向量恢复
            self.dialogue.load(DIALOGUE_PATH)
        if self.grammar is not None:       # P20：构造语法恢复/用听觉史初始化
            if os.path.exists(CONSTRUCTION_PATH):
                self.grammar = constructions_mod.ConstructionGrammar.load(
                    CONSTRUCTION_PATH)
            else:
                for _m in self.memory:
                    _t = _m.get("text")
                    if _t:
                        self.grammar.learn(_t, state=_m.get("s"),
                                           world=_m.get("world"))
                self.grammar.finalize()
        return True

    # ============ R5 工作集：每 tick 衰减 ============
    def tick_workspace(self, dt_hours):
        """每 tick 调用；默认关时直接返回，不改状态。"""
        self.ws.decay(dt_hours)
