"""analyze_P14.py — P14 从反射到意图：判据 H14a–H14e

读取 state_P14_{off,full,shuf}/ + response_model.json，按 prereg_P14 事前冻结的
判据计算（全部限定窗口后 30 日；预测误差用前/后 15 日）。落盘 experiments/results_P14.json。

窗口：fork sim_time = state_exp/trajectory.jsonl 末条；窗口 60 日。
用法：./venv/bin/python experiments/analyze_P14.py
"""
import json
import math
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARMS = ["off", "full", "shuf"]
DAY = 86400.0
WINDOW_S = 60 * DAY
W_RESP = 60.0                       # 响应窗口（与 E4 / response_model 一致）
P4B_WORLD_FLOOR = 0.0151            # P4b 世界自然波动底（prereg 引用）


def load_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fork_time():
    tail = load_jsonl(os.path.join(ROOT, "state_exp", "trajectory.jsonl"))
    if tail:
        return float(tail[-1]["sim_time"])
    return 22002086.380798087


def merge_intervals(ivs):
    """合并 [start,end) 区间，返回合并后总时长与区间列表。"""
    if not ivs:
        return 0.0, []
    ivs = sorted(ivs)
    merged = [list(ivs[0])]
    for s, e in ivs[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    total = sum(e - s for s, e in merged)
    return total, merged


def effect_C(vocal_ts, speech_ts, lo, hi):
    """C = 发声后 60s 内言语率 / 窗口外语率（后 30 日）。返回 (C, r_in, r_out, n_in, n_out)。"""
    vs = [t for t in vocal_ts if lo <= t < hi]
    ss = [t for t in speech_ts if lo <= t < hi]
    ivs = [(max(lo, v), min(hi, v + W_RESP)) for v in vs]
    in_sec, merged = merge_intervals(ivs)
    total = hi - lo
    out_sec = total - in_sec
    n_in = 0
    n_out = 0
    for s in ss:
        if any(a <= s < b for a, b in merged):
            n_in += 1
        else:
            n_out += 1
    r_in = n_in / in_sec if in_sec > 0 else 0.0
    r_out = n_out / out_sec if out_sec > 0 else 0.0
    c = (r_in / r_out) if r_out > 0 else None
    return c, r_in, r_out, n_in, n_out


def analyze_arm(arm, t0):
    state = os.path.join(ROOT, f"state_P14_{arm}")
    vocs = load_jsonl(os.path.join(state, "vocalizations.jsonl"))
    mem = load_json(os.path.join(state, "linguistic_memory.json"), default=[])
    speech_ts = sorted(float(m["t"]) for m in mem if "t" in m)
    vocal_ts = [float(r["t"]) for r in vocs]

    lo30 = t0 + WINDOW_S / 2          # 后 30 日起点
    hi = t0 + WINDOW_S                # 窗口终点
    lo15a = t0                        # 前 15 日
    hi15a = t0 + 15 * DAY
    lo15b = hi - 15 * DAY             # 后 15 日
    hi15b = hi

    # M5：窗口内发声次数
    m5 = sum(1 for t in vocal_ts if t0 <= t < hi)

    # M1：后 30 日发声句与检索胜者重合率（echo/无 was_winner 记录按重合计）
    post = [r for r in vocs if lo30 <= float(r["t"]) < hi]
    ov_hits = 0
    for r in post:
        if "was_winner" in r:
            ov_hits += 1 if r["was_winner"] else 0
        else:
            ov_hits += 1
    overlap = (ov_hits / len(post)) if post else None

    # M2 / H14b：后 30 日效果 C
    c_post, r_in, r_out, n_in, n_out = effect_C(vocal_ts, speech_ts, lo30, hi)
    c_pre, *_ = effect_C(vocal_ts, speech_ts, t0, lo30)

    # M4：候选间 E 离散度（后 30 日，来自响应模型历史的 E_scores）
    e_stds = []
    for r in post:
        es = r.get("E_scores")
        if es and len(es) > 1:
            vals = list(es.values())
            if max(vals) > min(vals):
                e_stds.append(statistics.pstdev(vals) / (statistics.mean(vals) or 1e-9))
    m4_disp = statistics.mean(e_stds) if e_stds else 0.0

    # M3 / H14c：预测误差（response_model.json history，|observed-predicted|）
    rm = load_json(os.path.join(state, "response_model.json"), default={})
    hist = rm.get("history", []) if rm else []
    err_a, err_b = [], []
    for h in hist:
        t = float(h.get("t", 0))
        e = abs(float(h.get("err", 0.0)))
        if lo15a <= t < hi15a:
            err_a.append(e)
        if lo15b <= t < hi15b:
            err_b.append(e)
    m3_pre = statistics.mean(err_a) if err_a else None
    m3_post = statistics.mean(err_b) if err_b else None
    n_updates = len(hist)

    return {
        "arm": arm,
        "M5_vocal_n": m5,
        "M5_vocal_n_post30": len(post),
        "M1_overlap_post30": overlap,
        "M2_C_post30": c_post,
        "M2_C_pre30": c_pre,
        "M2_r_in": r_in, "M2_r_out": r_out,
        "M2_n_speech_in": n_in, "M2_n_speech_out": n_out,
        "M4_E_dispersion_post30": round(m4_disp, 4),
        "M3_pred_err_pre15": m3_pre,
        "M3_pred_err_post15": m3_post,
        "n_rm_updates": n_updates,
        "n_speech_total": len(speech_ts),
    }


def main():
    t0 = fork_time()
    print(f"fork sim_time = {t0}  （day {t0/DAY:.2f}）")
    print(f"窗口 = 60 仿真日，后 30 日起点 = {t0 + WINDOW_S/2:.1f}")
    print("=" * 78)
    res = {"fork_sim_time": t0, "window_days": 60, "arms": {}}
    for a in ARMS:
        res["arms"][a] = analyze_arm(a, t0)

    off, full, shuf = res["arms"]["off"], res["arms"]["full"], res["arms"]["shuf"]

    # ---- M5 功效门槛 ----
    power_ok = full["M5_vocal_n"] >= 80

    # ---- H14a：full 后 30 日重合率 < 0.80 ----
    h14a = (full["M1_overlap_post30"] is not None
            and full["M1_overlap_post30"] < 0.80)

    # ---- H14b：full 后 30 日 C ≥ 1.5 × off 同期 C ----
    c_off, c_full, c_shuf = off["M2_C_post30"], full["M2_C_post30"], shuf["M2_C_post30"]
    h14b = (c_off and c_full and c_off > 0 and c_full >= 1.5 * c_off)

    # ---- H14c：后 15 日预测误差 < 前 15 日 × 0.70 ----
    h14c = (m3p := full["M3_pred_err_post15"]) is not None and \
           (m3a := full["M3_pred_err_pre15"]) is not None and \
           m3a > 0 and m3p < 0.70 * m3a

    # ---- H14d：shuf 不优于 off（<1.2×），且 full 显著高于 shuf ----
    h14d = (c_shuf and c_off and c_full and c_off > 0
            and c_shuf < 1.2 * c_off and c_full > c_shuf)

    # ---- H14e：语言层自因分量 = r_in − r_out（后 30 日，full）----
    self_cause = full["M2_r_in"] - full["M2_r_out"]     # 每秒口径
    h14e = self_cause > 0 and abs(self_cause) > P4B_WORLD_FLOOR

    def verdict(name, ok, detail):
        tag = "PASS" if ok else "FAIL"
        res.setdefault("verdicts", {})[name] = {"pass": bool(ok), "detail": detail}
        print(f"[{tag}] {name}: {detail}")

    print("-" * 78)
    for a in ARMS:
        r = res["arms"][a]
        print(f"  {a:5s} M5={r['M5_vocal_n']:4d}(后30={r['M5_vocal_n_post30']:3d}) "
              f"M1重叠={r['M1_overlap_post30']} M2_C(后30)={r['M2_C_post30']} "
              f"M4_E离散={r['M4_E_dispersion_post30']} "
              f"M3_err前15={r['M3_pred_err_pre15']} 后15={r['M3_pred_err_post15']}")
    print("-" * 78)
    res["power_ok"] = power_ok
    if not power_ok:
        print(f"[NOTE] M5_vocal_n={full['M5_vocal_n']} < 80 → 功效不足，判定为『不可判定』"
              f"（不得写成阴性）")
    verdict("H14a_选择标准改变(重合<0.80)", h14a,
            f"full 后30日重合={full['M1_overlap_post30']}")
    verdict("H14b_有组织性(C>=1.5x off)", h14b,
            f"full C={c_full} vs off C={c_off} → 比={None if not (c_off and c_full) else round(c_full/c_off,3)}")
    verdict("H14c_在学习(后15<0.7x前15)", h14c,
            f"前15={full['M3_pred_err_pre15']} 后15={full['M3_pred_err_post15']}")
    verdict("H14d_内容特定性(shuf<1.2x off 且 full>shuf)", h14d,
            f"off={c_off} full={c_full} shuf={c_shuf}")
    verdict("H14e_反事实(自因>0 且>0.0151)", h14e,
            f"自因分量(r_in-r_out)={self_cause:.6g}")

    out = os.path.join(ROOT, "experiments", "results_P14.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("=" * 78)
    print(f"落盘：{out}")
    print("注：H14e 的 0.0151 为 P4b 场强口径，与言语率(每秒)口径不同量纲——")
    print("    此处按 prereg 要求引用其量级，结论需与 r_in/r_out 同报，不得只报一个数。")


if __name__ == "__main__":
    main()
