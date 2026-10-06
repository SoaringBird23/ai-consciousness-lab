"""self_model.py — 自我模型（P2 核心）

不预设身份。初始为 null。
P2.6（Vygotsky 路线）：自我模型从内化的第二人称语言中形成——照护者对"你"
说的话被反复自发激活，构成最初的"被称呼的自己"；第一人称（"我"）若在语料
中出现则随后并入。每次自我指向念头浮现，提炼片段更新自我模型。
允许覆盖、矛盾、重建。版本化 + 证据链接。
输出 state/self_model.json
"""
import json
import os

STATE_DIR = os.environ.get("STATE_DIR", "state")
SELF_MODEL_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "self_model.json")

SELF_REFERENCE_WORDS = [
    # P2.6：第二人称指向是自我的种子（先被称呼，后自称）
    "你",
    # 第一人称家族（若语料中出现"我"则并入）
    "我", "自己", "自我", "我的", "我是", "我在", "我觉得", "我想", "我感到", "我发现",
    "I", "me", "myself", "my", "I am", "I think", "I feel",
]

# 空话模板（不进入自我模型）
EMPTY_TEMPLATES = [
    "一系列活动", "新的认识", "情绪状态",
]

MAX_DESC_LENGTH = 4000  # 自我模型最大字符数（原 300 帽会在 ~30 片段处截停自我表征生长）


class SelfModel:
    def __init__(self, config):
        self.description = None
        self.version = 0
        self.updated_at = None
        self.history = []

    def _is_empty(self, text):
        """判断是否是空话模板。"""
        for t in EMPTY_TEMPLATES:
            if t in text:
                return True
        return False

    def _similar(self, a, b):
        """简单相似度：字符重叠率 > 0.6 视为相似。"""
        if not a or not b:
            return False
        set_a = set(a)
        set_b = set(b)
        if not set_a or not set_b:
            return False
        overlap = len(set_a & set_b) / len(set_a | set_b)
        return overlap > 0.7

    def maybe_update(self, inner_speech_text, sim_time):
        if not inner_speech_text:
            return False
        if inner_speech_text.startswith("[语言层调用失败"):
            return False

        has_self_ref = any(w in inner_speech_text for w in SELF_REFERENCE_WORDS)
        if not has_self_ref:
            return False

        # 提炼包含自我指涉的碎片（P2.5：输入是 2-8 字念头碎片）
        sentences = inner_speech_text.replace("\n", "。").split("。")
        self_sentences = [s.strip() for s in sentences if any(w in s for w in SELF_REFERENCE_WORDS)]
        self_sentences = [s for s in self_sentences if len(s) >= 2 and not self._is_empty(s)]
        if not self_sentences:
            return False

        new_fragment = "。".join(self_sentences)

        # 去重：与现有描述中已有的碎片比较相似度（碎片短，阈值放宽到 0.7 防误杀）
        if self.description:
            existing_parts = self.description.split(" ")
            for part in existing_parts:
                if self._similar(new_fragment, part):
                    return False  # 相似，不更新

        # 更新
        if self.description is None:
            self.description = new_fragment
        else:
            self.description = self.description + " " + new_fragment

        # 长度控制：超过阈值时，保留最新的片段（去掉最旧的）
        if len(self.description) > MAX_DESC_LENGTH:
            parts = self.description.split(" ")
            while len(" ".join(parts)) > MAX_DESC_LENGTH and len(parts) > 1:
                parts = parts[1:]
            self.description = " ".join(parts)

        self.version += 1
        self.updated_at = sim_time
        self.history.append({
            "version": self.version,
            "description": self.description,
            "updated_at": round(sim_time, 1),
            "source_t": round(sim_time, 1),
        })
        return True

    def get_text(self):
        return self.description

    def snapshot(self):
        return {
            "description": self.description,
            "version": self.version,
            "updated_at": self.updated_at,
            "history_count": len(self.history),
            "history": self.history,   # 修复：历史随主文件持久化（此前重启即丢失）
        }

    def load(self):
        if not os.path.exists(SELF_MODEL_PATH):
            return False
        with open(SELF_MODEL_PATH) as f:
            d = json.load(f)
        self.description = d.get("description")
        self.version = d.get("version", 0)
        self.updated_at = d.get("updated_at")
        self.history = d.get("history", [])
        return True

    def save(self):
        os.makedirs(os.path.dirname(SELF_MODEL_PATH), exist_ok=True)
        with open(SELF_MODEL_PATH, "w") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)
        hist_path = SELF_MODEL_PATH.replace(".json", "_history.json")
        with open(hist_path, "w") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
