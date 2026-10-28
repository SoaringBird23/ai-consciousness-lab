"""events.py — 环境事件源

P0 阶段没有真实用户交互，事件来自两类：
1. 模拟"类用户"事件：日内非均匀泊松（白天多、深夜少），带随机周律扰动。
   每条事件标 simulated=true，绝不能与真实输入混淆。
2. inbox/ 目录投递：实验者放入的文件 → 真实外部事件（simulated=false）。
   文件读取后归档到 inbox/processed/，不删除原始记录。
"""
import os
import shutil
import time

INBOX = os.path.join(os.path.dirname(__file__), os.environ.get("INBOX_DIR", "inbox"))
PROCESSED = os.path.join(INBOX, "processed")


class Environment:
    def __init__(self, config, rng):
        self.cfg = config["events"]["simulated_user"]
        self.rng = rng
        self.a, self.b = self.cfg["active_hours"]  # 9..23
        self.rate_active = self.cfg["rate_per_hour_active"]
        self.rate_night = self.cfg["rate_per_hour_night"]
        os.makedirs(PROCESSED, exist_ok=True)   # 优化：mkdir 从每 tick poll 移到一次初始化

    def _sim_rate(self, sim_hour):
        if self.a <= sim_hour < self.b:
            # 日内节律：早晚各一个活跃峰（模拟真人使用模式）
            base = self.rate_active
            morning = max(0.0, 1.0 - abs(sim_hour - 10.5) / 3.0)
            evening = max(0.0, 1.0 - abs(sim_hour - 20.5) / 3.5)
            return base * (0.5 + morning + evening)
        return self.rate_night

    def poll(self, dt_hours, sim_hour):
        """返回本 tick 发生的事件列表。"""
        events = []
        # 模拟用户：泊松采样
        lam = self._sim_rate(sim_hour) * dt_hours
        if self.rng.random() < lam:
            events.append({
                "type": "env",
                "source": "simulated_user",
                "simulated": True,
                "detail": "activity",
            })
        # inbox 真实投递（P3：say_* 文件 = 真实照护者话语，路由到语言层）
        if os.path.isdir(INBOX):
            for name in sorted(os.listdir(INBOX)):
                path = os.path.join(INBOX, name)
                if os.path.isfile(path) and not name.startswith("."):
                    if name.startswith("say_"):
                        text = ""
                        try:
                            with open(path, encoding="utf-8") as f:
                                text = f.read().strip()[:60]   # 短语系统：截到 60 字
                        except OSError:
                            pass
                        if text:
                            events.append({
                                "type": "speech",
                                "source": "caregiver_real",
                                "simulated": False,
                                "text": text,
                            })
                    else:
                        events.append({
                            "type": "env",
                            "source": "inbox",
                            "simulated": False,
                            "detail": name,
                        })
                    shutil.move(path, os.path.join(PROCESSED, name))
        return events
