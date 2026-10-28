"""analyze_P15.py — P15 反事实自我报告

读取 state_P15_{off,full,shuf}/ 的 vocalizations.jsonl + counterfactual.jsonl +
linguistic_memory.json + self_model.json，检验 H15a–H15d，落盘 experiments/results_P15.json。

判据窗口：末 30 日（t0+30d .. t0+60d）。
- H15a 形式与无泄漏：台账良构；runner-up = 决策时点 E 第 2 名（≥0.99）；self_model 有非零 counterfactual；off 空。
- H15b 校准(承重)：预测效果 vs 实现效果 Spearman ≥ 0.5（full）；shuf < 0.5。
- H15c 后悔—回避：按型 Spearman(平均后悔, 被选率) < 0（full）；off 无效应。
- H15d 负意外调制：负意外后偏离状态胜者概率 ≥ 1.2× 非负意外后（full）；off 无效应。
"""
import json
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARMS = ["off", "full", "shuf"]
DAY = 86400.0
WINDOW_S = 60 * DAY
W_RESP = 60.0
T0_DEFAULT = 22002086.380798087
OUT = os.path.join(ROOT, "experiments", "results_P15.json")


def load_jsonl(p):
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def load_json(p, default):
    if not os.path.exists(p):
        return default
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def analyze_arm(arm, t0):
    st = os.path.join(ROOT, f"state_P15_{arm}")
    vocs = load_jsonl(os.path.join(st, "vocalizations.jsonl"))
    cfs = load_jsonl(os.path.join(st, "counterfactual.jsonl"))
    mem = load_json(os.path.join(st, "linguistic_memory.json"), [])
    sm = load_json(os.path.join(st, "self_model.json"), {})
    speech_ts = sorted(float(m["t"]) for m in mem if isinstance(m, dict) and "t" in m)

    hi = t0 + WINDOW_S
    lo30 = hi - 30 * DAY

    def n_in(v, w=W_RESP):
        # 二分：窗口 (v, v+w] 内言语条数
        import bisect
        return bisect.bisect_right(speech_ts, v + w) - bisect.bisect_right(speech_ts, v)

    sp_win = [s for s in speech_ts if lo30 <= s < hi]
    r_out = (len(sp_win) / (hi - lo30)) if (hi - lo30) > 0 else 0.0

    post = [r for r in vocs if lo30 <= float(r["t"]) < hi]

    # ---- H15a：台账良构 + runner-up 正确 + self_model 块 ----
    ok_n, tot_n = 0, 0
    for r in post:
        cf = r.get("cf")
        es = r.get("E_scores")
        if not cf or not es or len(es) < 1:
            continue
        tot_n += 1
        vals = sorted(es.values(), reverse=True)
        second_val = vals[1] if len(vals) > 1 else vals[0]
        if (es.get(cf.get("alt")) is not None
                and abs(es.get(cf.get("alt")) - second_val) < 1e-6
                and abs(es.get(r["text"], -1) - vals[0]) < 1e-6):
            ok_n += 1
    ru_rate = (ok_n / tot_n) if tot_n else None
    sm_cf = sm.get("counterfactual") if isinstance(sm, dict) else None
    sm_has = bool(sm_cf and sm_cf.get("count", 0) > 0)

    # ---- H15b：校准（预测 vs 实现）----
    pairs = []
    for r in post:
        cf = r.get("cf")
        if not cf or cf.get("E_chosen") is None or r_out <= 0:
            continue
        realized = (n_in(float(r["t"])) / W_RESP) / r_out
        pairs.append((cf["E_chosen"], realized))
    hb_rho = spearman([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 8 else None

    # ---- H15c：后悔—回避（按型）----
    by_type = {}
    for (pred, real), r in zip(pairs, [r for r in post
                                       if r.get("cf") and r.get("cf").get("E_chosen") is not None
                                       and r_out > 0]):
        t = r["text"]
        by_type.setdefault(t, {"reg": [], "n": 0})
        by_type[t]["reg"].append(pred - real)
        by_type[t]["n"] += 1
    tot_sel = sum(v["n"] for v in by_type.values()) or 1
    types = [(statistics.mean(v["reg"]), v["n"] / tot_sel) for v in by_type.values() if v["n"] >= 3]
    hc_rho = spearman([t[0] for t in types], [t[1] for t in types]) if len(types) >= 5 else None

    # ---- H15d：负意外调制 ----
    seq = [r for r in post if r.get("cf") and r.get("cf").get("E_chosen") is not None
           and r_out > 0]
    dev_neg, n_neg, dev_pos, n_pos = 0, 0, 0, 0
    for i in range(len(seq) - 1):
        pred = seq[i]["cf"]["E_chosen"]
        real = (n_in(float(seq[i]["t"])) / W_RESP) / r_out
        dev_next = (not seq[i + 1].get("was_winner", True))
        if pred - real > 0:
            n_neg += 1; dev_neg += 1 if dev_next else 0
        else:
            n_pos += 1; dev_pos += 1 if dev_next else 0
    p_neg = (dev_neg / n_neg) if n_neg else None
    p_pos = (dev_pos / n_pos) if n_pos else None
    hd_ratio = (p_neg / p_pos) if (p_neg is not None and p_pos not in (None, 0)) else None

    return {
        "arm": arm,
        "M5_vocal_n": len(vocs),
        "M5_vocal_n_post30": len(post),
        "H15a_ledger_n_post30": len([r for r in post if r.get("cf")]),
        "H15a_runnerup_rate": (round(ru_rate, 4) if ru_rate is not None else None),
        "H15a_selfmodel_cf": sm_has,
        "H15b_calib_rho": (round(hb_rho, 4) if hb_rho is not None else None),
        "H15b_n_pairs": len(pairs),
        "H15c_avoid_rho": (round(hc_rho, 4) if hc_rho is not None else None),
        "H15c_n_types": len(types),
        "H15d_p_dev_neg": (round(p_neg, 4) if p_neg is not None else None),
        "H15d_p_dev_pos": (round(p_pos, 4) if p_pos is not None else None),
        "H15d_ratio": (round(hd_ratio, 4) if hd_ratio is not None else None),
    }


def main():
    t0 = T0_DEFAULT
    p14c = load_json(os.path.join(ROOT, "experiments", "results_P14c.json"), {})
    if p14c.get("fork_sim_time"):
        t0 = float(p14c["fork_sim_time"])
    print(f"fork t0={t0}（day {t0/DAY:.2f}）；窗口 {int(WINDOW_S/DAY)} 日；判据窗口=末 30 日")
    print("=" * 86)
    res = {"fork_sim_time": t0, "window_days": int(WINDOW_S / DAY),
           "judged_window": "末30日 (t0+30d .. t0+60d)", "arms": {}}
    for a in ARMS:
        res["arms"][a] = analyze_arm(a, t0)

    off, full, shuf = res["arms"]["off"], res["arms"]["full"], res["arms"]["shuf"]
    for a in ARMS:
        m = res["arms"][a]
        print(f"  {a:5s} vocal={m['M5_vocal_n']:4d}(post30 {m['M5_vocal_n_post30']:3d}) "
              f"ledger={m['H15a_ledger_n_post30']:3d} ru={m['H15a_runnerup_rate']} "
              f"smcf={m['H15a_selfmodel_cf']} calib={m['H15b_calib_rho']}(n={m['H15b_n_pairs']}) "
              f"avoid={m['H15c_avoid_rho']}(t={m['H15c_n_types']}) "
              f"dev_ratio={m['H15d_ratio']}")
    print("=" * 86)

    v = {}
    # H15a
    a_ok = (full["H15a_runnerup_rate"] is not None and full["H15a_runnerup_rate"] >= 0.99
            and full["H15a_selfmodel_cf"]
            and off["M5_vocal_n_post30"] >= 0 and off["H15a_ledger_n_post30"] == 0
            and not off["H15a_selfmodel_cf"])
    v["H15a_形式与无泄漏"] = {"pass": bool(a_ok),
        "detail": (f"full ru={full['H15a_runnerup_rate']} smcf={full['H15a_selfmodel_cf']}; "
                   f"off ledger={off['H15a_ledger_n_post30']} smcf={off['H15a_selfmodel_cf']}")}
    # H15b
    b_ok = (full["H15b_calib_rho"] is not None and full["H15b_calib_rho"] >= 0.5
            and (shuf["H15b_calib_rho"] is None or shuf["H15b_calib_rho"] < 0.5))
    v["H15b_校准(Spearman>=0.5)"] = {"pass": bool(b_ok),
        "detail": f"full ρ={full['H15b_calib_rho']} vs shuf ρ={shuf['H15b_calib_rho']}"}
    # H15c（探索性）
    c_ok = (full["H15c_avoid_rho"] is not None and full["H15c_avoid_rho"] < 0)
    v["H15c_后悔—回避(ρ<0,探索)"] = {"pass": bool(c_ok),
        "detail": f"full ρ={full['H15c_avoid_rho']}（型数 {full['H15c_n_types']}）"}
    # H15d（探索性）
    d_ok = (full["H15d_ratio"] is not None and full["H15d_ratio"] >= 1.2)
    v["H15d_负意外调制(>=1.2x,探索)"] = {"pass": bool(d_ok),
        "detail": (f"full P(偏离|负)={full['H15d_p_dev_neg']} / P(偏离|非负)="
                   f"{full['H15d_p_dev_pos']} → {full['H15d_ratio']}")}
    res["verdicts"] = v
    res["power_ok"] = full["M5_vocal_n"] >= 80

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("落盘：", OUT)
    for k, d in v.items():
        print(f"  [{'PASS' if d['pass'] else 'FAIL'}] {k} — {d['detail']}")


if __name__ == "__main__":
    main()
