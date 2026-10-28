"""analyze_P14b.py — P14c 内容敏感听者：判据 H14a–H14f

读取 state_P14c_{off,full,shuf}/ + response_model.json + experiments/p14c_content_map.json，
按 prereg_P14c 事前冻结的判据计算（后 30 日为主；预测误差用前/后 15 日）。
落盘 experiments/results_P14c.json。

新增（相对 analyze_P14.py）：
  M6_E_vs_r_corr：窗口末 E 表与真值 r(f) 的 Spearman 秩相关（H14f）
  M7_class_mix  ：后 30 日 top-5 候选里 HIGH 占比均值（诊断：选择是否有空间）
用法：./venv/bin/python experiments/analyze_P14b.py
"""
import json
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARMS = ["off", "full", "shuf"]
DAY = 86400.0
WINDOW_S = 120 * DAY
W_RESP = 60.0
P4B_WORLD_FLOOR = 0.0151


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
    return float(tail[-1]["sim_time"]) if tail else 22002086.380798087


def merge_intervals(ivs):
    if not ivs:
        return 0.0, []
    ivs = sorted(ivs)
    merged = [list(ivs[0])]
    for s, e in ivs[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return sum(e - s for s, e in merged), merged


def effect_C(vocal_ts, speech_ts, lo, hi):
    vs = [t for t in vocal_ts if lo <= t < hi]
    ss = [t for t in speech_ts if lo <= t < hi]
    ivs = [(max(lo, v), min(hi, v + W_RESP)) for v in vs]
    in_sec, merged = merge_intervals(ivs)
    out_sec = (hi - lo) - in_sec
    n_in = sum(1 for s in ss if any(a <= s < b for a, b in merged))
    n_out = len(ss) - n_in
    r_in = n_in / in_sec if in_sec > 0 else 0.0
    r_out = n_out / out_sec if out_sec > 0 else 0.0
    return ((r_in / r_out) if r_out > 0 else None), r_in, r_out, n_in, n_out


def _rankdata(vals):
    """平均秩（处理并列）。"""
    idx = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and vals[idx[j + 1]] == vals[idx[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[idx[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys):
    if len(xs) < 3:
        return None
    rx, ry = _rankdata(xs), _rankdata(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def analyze_arm(arm, t0, r_map):
    state = os.path.join(ROOT, f"state_P14c_{arm}")
    vocs = load_jsonl(os.path.join(state, "vocalizations.jsonl"))
    mem = load_json(os.path.join(state, "linguistic_memory.json"), default=[])
    speech_ts = sorted(float(m["t"]) for m in mem if "t" in m)
    vocal_ts = [float(r["t"]) for r in vocs]

    hi = t0 + WINDOW_S
    lo30 = hi - 30 * DAY          # 判据窗口 = 末 30 日（与预注册『后30日』一致）
    lo15a, hi15a = t0, t0 + 15 * DAY      # 学习对照：起始 15 日
    lo15b, hi15b = hi - 15 * DAY, hi      # 学习对照：末 15 日

    m5 = sum(1 for t in vocal_ts if t0 <= t < hi)
    post = [r for r in vocs if lo30 <= float(r["t"]) < hi]

    ov_hits = sum((1 if r.get("was_winner", True) else 0) for r in post)
    overlap = (ov_hits / len(post)) if post else None

    c_post, r_in, r_out, n_in, n_out = effect_C(vocal_ts, speech_ts, lo30, hi)

    e_stds = []
    for r in post:
        es = r.get("E_scores")
        if es and len(es) > 1:
            vals = list(es.values())
            if max(vals) > min(vals):
                e_stds.append(statistics.pstdev(vals) / (statistics.mean(vals) or 1e-9))
    m4 = statistics.mean(e_stds) if e_stds else 0.0

    # M7：top-5 里 HIGH 占比
    m7_vals = []
    for r in post:
        es = r.get("E_scores")
        if es:
            hi_n = sum(1 for t in es if r_map.get(t) == "HIGH")
            m7_vals.append(hi_n / len(es))
    m7 = statistics.mean(m7_vals) if m7_vals else None

    rm = load_json(os.path.join(state, "response_model.json"), default={})
    hist = rm.get("history", []) if rm else []
    err_a = [abs(float(h.get("err", 0.0))) for h in hist if lo15a <= float(h.get("t", 0)) < hi15a]
    err_b = [abs(float(h.get("err", 0.0))) for h in hist if lo15b <= float(h.get("t", 0)) < hi15b]
    m3_pre = statistics.mean(err_a) if err_a else None
    m3_post = statistics.mean(err_b) if err_b else None

    # M6：E（按型）与真值 r(f) 的相关
    E = rm.get("E", {}) if rm else {}
    xs, ys = [], []
    for t, e in E.items():
        if t in r_map:
            xs.append(e)
            ys.append(1.0 if r_map[t] == "HIGH" else 0.0)
    m6 = spearman(xs, ys) if len(xs) >= 3 else None

    return {
        "arm": arm, "M5_vocal_n": m5, "M5_vocal_n_post30": len(post),
        "M1_overlap_post30": overlap,
        "M2_C_post30": c_post, "M2_r_in": r_in, "M2_r_out": r_out,
        "M2_n_speech_in": n_in, "M2_n_speech_out": n_out,
        "M4_E_dispersion_post30": round(m4, 4),
        "M7_class_mix_HIGH": None if m7 is None else round(m7, 4),
        "M3_pred_err_pre15": m3_pre, "M3_pred_err_post15": m3_post,
        "M6_E_vs_r_spearman": None if m6 is None else round(m6, 4),
        "n_rm_updates": len(hist), "n_E_types": len(E), "n_speech_total": len(speech_ts),
    }


def main():
    t0 = fork_time()
    cmap = load_json(os.path.join(ROOT, "experiments", "p14c_content_map.json"), default={})
    r_map = cmap.get("r", {})
    cs = cmap.get("classes", {})
    print(f"fork sim_time = {t0}（day {t0/DAY:.2f}）；映射 n={cmap.get('n_types')} "
          f"HIGH={cmap.get('n_high')} LOW={cmap.get('n_low')} sha={str(cmap.get('sha256'))[:12]}")
    print("=" * 86)
    res = {"fork_sim_time": t0, "window_days": 120,
           "judged_window": "末30日 (t0+90d .. t0+120d)",
           "content_map_sha": cmap.get("sha256"), "arms": {}}
    for a in ARMS:
        res["arms"][a] = analyze_arm(a, t0, cs)

    off, full, shuf = res["arms"]["off"], res["arms"]["full"], res["arms"]["shuf"]
    power_ok = full["M5_vocal_n"] >= 80
    mix = full["M7_class_mix_HIGH"]
    space_ok = (mix is not None and 0.05 < mix < 0.95)

    h14a = full["M1_overlap_post30"] is not None and full["M1_overlap_post30"] < 0.80
    c_off, c_full, c_shuf = off["M2_C_post30"], full["M2_C_post30"], shuf["M2_C_post30"]
    h14b = bool(c_off and c_full and c_off > 0 and c_full >= 1.5 * c_off)
    m3p, m3a = full["M3_pred_err_post15"], full["M3_pred_err_pre15"]
    h14c = (m3p is not None and m3a is not None and m3a > 0 and m3p < 0.70 * m3a)
    h14d = bool(c_shuf and c_off and c_full and c_off > 0
                and c_shuf < 1.2 * c_off and c_full >= 1.2 * c_shuf)
    self_cause = full["M2_r_in"] - full["M2_r_out"]
    h14e = self_cause > 0 and abs(self_cause) > P4B_WORLD_FLOOR
    h14f = full["M6_E_vs_r_spearman"] is not None and full["M6_E_vs_r_spearman"] >= 0.5

    for a in ARMS:
        r = res["arms"][a]
        print(f"  {a:5s} M5={r['M5_vocal_n']:4d} M1={r['M1_overlap_post30']} "
              f"C={None if r['M2_C_post30'] is None else round(r['M2_C_post30'],3)} "
              f"M4={r['M4_E_dispersion_post30']} M7_HIGH={r['M7_class_mix_HIGH']} "
              f"M6_ρ={r['M6_E_vs_r_spearman']} M3前15={None if r['M3_pred_err_pre15'] is None else round(r['M3_pred_err_pre15'],2)} "
              f"后15={None if r['M3_pred_err_post15'] is None else round(r['M3_pred_err_post15'],2)}")
    print("-" * 86)

    res["power_ok"] = power_ok
    res["space_ok"] = space_ok
    res["verdicts"] = {}

    def verdict(name, ok, detail):
        res["verdicts"][name] = {"pass": bool(ok), "detail": detail}
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    if not power_ok:
        print(f"[NOTE] M5_vocal_n={full['M5_vocal_n']} < 80 → 功效不足：判『不可判定』")
    if not space_ok:
        print(f"[NOTE] M7_class_mix_HIGH={mix} 越界(<=0.05 或 >=0.95) → 选择无空间：判『不可判定』")

    verdict("H14a_选择标准改变(重合<0.80)", h14a, f"full 后30日重合={full['M1_overlap_post30']}")
    verdict("H14b_有组织性(C>=1.5x off)", h14b,
            f"full C={c_full} vs off C={c_off} → 比={None if not (c_off and c_full) else round(c_full/c_off,3)}")
    verdict("H14c_在学习(后15<0.7x前15)", h14c, f"前15={m3a} 后15={m3p}")
    verdict("H14d_内容特定性(shuf<1.2xoff 且 full>=1.2xshuf)", h14d,
            f"off={c_off} full={c_full} shuf={c_shuf}")
    verdict("H14e_反事实(自因>0 且>0.0151)", h14e, f"自因分量(r_in-r_out)={self_cause:.6g}")
    verdict("H14f_学到听者内容规则(Spearman>=0.5)", h14f,
            f"full M6 ρ={full['M6_E_vs_r_spearman']}（对比 shuf ρ={shuf['M6_E_vs_r_spearman']}）")

    out = os.path.join(ROOT, "experiments", "results_P14c.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("=" * 86)
    print(f"落盘：{out}")


if __name__ == "__main__":
    main()
