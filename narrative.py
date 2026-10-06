"""narrative.py — 自我叙事（P2）

持续编织关于"我"的故事。
每次自我模型更新时，把变化织入叙事链。
叙事是追加式的，允许矛盾、断裂、重建。
输出 state/narrative.json
"""
import json
import os

STATE_DIR = os.environ.get("STATE_DIR", "state")
NARRATIVE_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "narrative.json")


class Narrative:
    def __init__(self, config):
        self.threads = []  # 叙事线程列表
        self.version = 0

    def weave(self, self_model_description, sim_time, inner_speech=None):
        """根据自我模型变化编织/更新叙事。"""
        if not self_model_description:
            return
        # 每个版本的自我模型描述形成一条叙事线索
        thread = {
            "version": self.version,
            "t": round(sim_time, 1),
            "self_model": self_model_description,
            "inner_speech_excerpt": inner_speech[:100] if inner_speech else None,
        }
        self.threads.append(thread)
        self.version += 1

    def snapshot(self):
        return {
            "version": self.version,
            "thread_count": len(self.threads),
            "latest": self.threads[-1] if self.threads else None,
            "threads": self.threads[-10:],  # 只保留最近 10 条在线，全量在文件
        }

    def load(self):
        if not os.path.exists(NARRATIVE_PATH):
            return False
        with open(NARRATIVE_PATH) as f:
            d = json.load(f)
        self.version = d.get("version", 0)
        self.threads = d.get("all_threads", d.get("threads", []))
        return True

    def save(self):
        os.makedirs(os.path.dirname(NARRATIVE_PATH), exist_ok=True)
        with open(NARRATIVE_PATH, "w") as f:
            json.dump({
                "version": self.version,
                "all_threads": self.threads,
            }, f, ensure_ascii=False, indent=2)
