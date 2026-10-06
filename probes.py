"""probes.py — 时间知觉探针（E1）与期待检验（E4）

P1 阶段无语言，探针以数值形式进行：
- E1 时长知觉：随机时刻取两条情景记忆，让系统判断哪条更近。
  系统的"判断"= 记忆清晰度（时间衰减 × 当时 s6 激活）更高的那条。
  记录误差，并与当时唤醒度 s1、近期事件密度做相关性分析（离线做）。
- E4 期待（entrainment）：在预测器推断的活跃时段中心之前 1 小时，
  检查 s1 唤醒度是否系统性高于同时段基线。离线分析时统计。

输出：state/probes.jsonl（追加式，每条探针一个结果）
"""
import json
import os
import math
import random

STATE_DIR = os.environ.get("STATE_DIR", "state")
PROBES_PATH = os.path.join(os.path.dirname(__file__), STATE_DIR, "probes.jsonl")


class Probes:
    def __init__(self, config):
        self.interval_sim_hours = config.get("probes", {}).get("interval_hours", 2.0)
        self.decay_hours = config.get("probes", {}).get("memory_decay_hours", 6.0)
        # E1 噪声参数：基础噪声 + 唤醒度/事件密度调制
        self.e1_noise_base = config.get("probes", {}).get("e1_noise_base", 0.15)
        self.e1_arousal_weight = config.get("probes", {}).get("e1_arousal_weight", 0.3)
        self.e1_density_weight = config.get("probes", {}).get("e1_density_weight", 0.3)
        self.last_probe_sim_time = None
        self.last_e4_sim_time = None
        self.e4_interval_sim = 3600.0
        self.n_probes = 0
        self.n_correct = 0

    def should_probe(self, sim_time):
        if self.last_probe_sim_time is None:
            self.last_probe_sim_time = sim_time
            return False
        return (sim_time - self.last_probe_sim_time) / 3600.0 >= self.interval_sim_hours

    def run_e1(self, sim_time, episodic_memory, state_vec, rng, event_density=0.0):
        """E1 时长知觉探针。

        判断机制：记忆清晰度 = 时间衰减 × s6 激活 + 感知噪声。
        噪声幅度由唤醒度 s1 和近期事件密度调制——模拟人类"忙碌时时间飞逝、
        无聊时时间漫长"的系统性偏差。错误率应随 s1 和事件密度上升。
        """
        self.last_probe_sim_time = sim_time
        self.n_probes += 1
        s1 = state_vec[0]

        if len(episodic_memory) < 2:
            return None

        # 随机选两条不同时刻的情景记忆
        idxs = rng.choice(len(episodic_memory), 2, replace=False).tolist()
        ep_a = episodic_memory[idxs[0]]
        ep_b = episodic_memory[idxs[1]]

        # 噪声幅度：基础噪声 × (1 + 唤醒度权重 × s1 + 事件密度权重 × 密度)
        # 忙碌/高唤醒时噪声大 → 判断易错；无聊时噪声小 → 判断准
        sigma = self.e1_noise_base * (
            1.0 + self.e1_arousal_weight * s1 + self.e1_density_weight * event_density
        )

        # 清晰度 = 时间衰减 × s6 激活 + 高斯噪声
        def clarity(ep):
            dt_hours = (sim_time - ep["t"]) / 3600.0
            decay = math.exp(-dt_hours / self.decay_hours)
            s6_at_event = ep["s"][5] if len(ep["s"]) > 5 else 0.0
            base = decay * (0.5 + s6_at_event)
            noise = rng.normal(0.0, sigma)
            return base + noise

        cl_a = clarity(ep_a)
        cl_b = clarity(ep_b)
        # 系统认为更近的 = 清晰度更高的
        judged_closer_is_a = cl_a >= cl_b
        # 真实更近的 = sim_time 更大的
        actual_closer_is_a = ep_a["t"] >= ep_b["t"]
        correct = judged_closer_is_a == actual_closer_is_a
        if correct:
            self.n_correct += 1

        result = {
            "t": round(sim_time, 1),
            "probe": "E1_duration_perception",
            "s1_arousal": round(s1, 3),
            "event_density": round(event_density, 4),
            "noise_sigma": round(sigma, 4),
            "dt_a_hours": round((sim_time - ep_a["t"]) / 3600.0, 2),
            "dt_b_hours": round((sim_time - ep_b["t"]) / 3600.0, 2),
            "clarity_a": round(cl_a, 4),
            "clarity_b": round(cl_b, 4),
            "correct": correct,
            "accuracy_so_far": round(self.n_correct / self.n_probes, 3) if self.n_probes else None,
        }
        os.makedirs(os.path.dirname(PROBES_PATH), exist_ok=True)
        with open(PROBES_PATH, "a") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
        return result

    def e4_expectation(self, sim_time, predictor, state_vec):
        """E4 期待检验：检查当前是否在'预期事件时刻'之前 1 小时，
        若是则记录唤醒度，供离线分析是否提前爬升。
        只有当预测器已收敛（世界规律已知）时才有意义。节流：每仿真小时最多一次。"""
        if not predictor.converged():
            return None
        if self.last_e4_sim_time is not None and sim_time - self.last_e4_sim_time < self.e4_interval_sim:
            return None
        hour = (sim_time / 3600.0) % 24.0
        # 找到预测器分布的峰值小时（最活跃时段中心）
        counts = predictor.counts
        peak_hour = max(range(len(counts)), key=lambda h: counts[h])
        # 检查是否在峰值前 1 小时内
        diff = (peak_hour - hour) % 24
        if diff <= 1.0:
            self.last_e4_sim_time = sim_time
            s1 = state_vec[0]
            result = {
                "t": round(sim_time, 1),
                "probe": "E4_expectation",
                "hour": round(hour, 2),
                "peak_hour": peak_hour,
                "s1_arousal": round(s1, 3),
            }
            os.makedirs(os.path.dirname(PROBES_PATH), exist_ok=True)
            with open(PROBES_PATH, "a") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            return result
        return None

    def snapshot(self):
        return {
            "n_probes": self.n_probes,
            "e1_accuracy": round(self.n_correct / self.n_probes, 3) if self.n_probes else None,
        }

    def save(self):
        pass  # 探针日志是追加式 jsonl，无需额外 save

    def load(self):
        if not os.path.exists(PROBES_PATH):
            return False
        with open(PROBES_PATH) as f:
            lines = f.readlines()
        self.n_probes = sum(1 for l in lines if '"E1_duration_perception"' in l)
        self.n_correct = sum(
            1 for l in lines
            if '"E1_duration_perception"' in l and '"correct": true' in l
        )
        e4_times = []
        for l in lines:
            if '"E4_expectation"' in l:
                try:
                    e4_times.append(json.loads(l)["t"])
                except Exception:
                    pass
        if e4_times:
            self.last_e4_sim_time = max(e4_times)
        if lines:
            try:
                last = json.loads(lines[-1])
                if last.get("probe") == "E1_duration_perception":
                    self.last_probe_sim_time = last.get("t")
            except Exception:
                pass
        return True
