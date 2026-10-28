"""analyze_P5.py — P5 痛/乐（affect）三臂分析器

判据来源：experiments/prereg_P5_affect.json
  三臂：off（affect 关） / rec_only（enabled, k_affect=0，只记录不接线） / on（k_affect=0.10）
  同一母本 fork（state_exp，day 255），同窗口 30 仿真日（255→285）。

窗口切分：fork 时刻的 sim_time 之后才算窗口；前缀（继承自母本）一律不计。
  首轮（未对齐）数据保留在 state_p5pre_*，不参与本判据（见 prereg amendment #3）。

指标：
  M1 探索率/日（attribution.jsonl source=boredom_driven_explore）
  M2 发声率/日（vocalizations.jsonl）
  M3 检索率/日（inner_speech.jsonl type=retrieval）
  M4 活动-休息节律（睡眠占比、入睡时相、睡眠段数）

假设：
  H1  on 与 off 在 M1..M4 至少一项差异 ≥10%
  H2  命中项上 rec_only 与 off 差异 <10%，且 (on−rec_only) ≈ (on−off)（±20% 相对误差）
  H4  痛态（distress 上三分位）下检索片段含「你/我」比例 / 下三分位 ≥1.5
  H5  on 臂窗口内新增 self_model 片段首次入模时刻偏向 distress 上三分位（二项检验 α=0.05）
  H6  探索性：第一人称念头产出时点的 distress 分位（仅记录）
  H3  探索性：痛峰值 → 其后 1 仿真日退避（仅记录）

用法：
  ./venv/bin/python experiments/analyze_P5.py           # 打印表格
  ./venv/bin/python experiments/analyze_P5.py --json    # 同时落盘 experiments/results_P5.json
"""
import json
import math
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARMS = ["off", "rec_only", "on"]
# fork 时刻：state_exp 末行 sim_time（母本）。窗口 = 严格大于此值。
FORK = float(os.environ.get("P5_FORK", "22002086.380798087"))
MOM_NAME = {"off": "off（affect 关）", "rec_only": "rec_only（k=0）", "on": "on（k=0.10）"}


def _jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _load(p):
    with open(p) as f:
        return json.load(f)


def _wins(recs, tkey="t"):
    return [r for r in recs if r.get(tkey, 0) > FORK]


def _self_ref(text):
    return ("你" in text) or ("我" in text)


# ---------------- 指标 ----------------

def metrics(arm):
    s = os.path.join(ROOT, "state_p5_" + arm)
    traj = _wins(_jsonl(os.path.join(s, "trajectory.jsonl")), "sim_time")
    isp = _wins(_jsonl(os.path.join(s, "inner_speech.jsonl")))
    voc = _wins(_jsonl(os.path.join(s, "vocalizations.jsonl")))
    att = _wins(_jsonl(os.path.join(s, "attribution.jsonl")))
    ret = [r for r in isp if r.get("type") == "retrieval"]
    explore = [r for r in att if r.get("source") == "boredom_driven_explore"]

    t0 = traj[0]["sim_time"]
    t1 = traj[-1]["sim_time"]
    span = (t1 - t0) / 86400.0

    # M4 睡眠
    n_asleep = sum(1 for r in traj if r.get("asleep"))
    sleep_frac = n_asleep / len(traj) if traj else 0.0
    onsets = [traj[i]["sim_hour"] for i in range(1, len(traj))
              if traj[i].get("asleep") and not traj[i - 1].get("asleep")]
    if onsets:
        sx = sum(math.sin(h / 24 * 2 * math.pi) for h in onsets)
        cy = sum(math.cos(h / 24 * 2 * math.pi) for h in onsets)
        onset_phase = (math.atan2(sx, cy) / (2 * math.pi) * 24) % 24
    else:
        onset_phase = None

    distress = [r.get("distress", 0.0) for r in traj]
    ease = [r.get("ease", 0.0) for r in traj]

    return {
        "arm": arm,
        "span_days": round(span, 2),
        "n_traj": len(traj),
        "M1_explore": len(explore),
        "M2_vocal": len(voc),
        "M3_retrieval": len(ret),
        "M1_rate": len(explore) / span if span else 0.0,
        "M2_rate": len(voc) / span if span else 0.0,
        "M3_rate": len(ret) / span if span else 0.0,
        "sleep_frac": sleep_frac,
        "sleep_total_days": sleep_frac * span,
        "onset_phase_h": onset_phase,
        "n_onsets": len(onsets),
        "distress_mean": sum(distress) / len(distress) if distress else None,
        "ease_mean": sum(ease) / len(ease) if ease else None,
        "_traj": traj,
        "_ret": ret,
        "_exp": explore, "_voc": voc,
        "_t0": t0, "_t1": t1,
    }


def _ratio_pct(a, b):
    """a 相对 b 的相对变化（%）。"""
    return (a - b) / b * 100.0 if b else float("nan")


# ---------------- H4/H5 分位映射 ----------------

def _nearest_distress(traj, t):
    """traj（按 sim_time 升序）中最近样本的 distress。"""
    lo, hi = 0, len(traj) - 1
    if t <= traj[0]["sim_time"]:
        return traj[0].get("distress", 0.0)
    if t >= traj[-1]["sim_time"]:
        return traj[-1].get("distress", 0.0)
    while lo < hi:
        mid = (lo + hi) // 2
        if traj[mid]["sim_time"] < t:
            lo = mid + 1
        else:
            hi = mid
    a, b = traj[lo - 1], traj[lo]
    da = abs(a["sim_time"] - t)
    db = abs(b["sim_time"] - t)
    return (a if da <= db else b).get("distress", 0.0)


def _percentile(sorted_vals, v):
    if not sorted_vals:
        return float("nan")
    lo, hi = 0, len(sorted_vals)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_vals[mid] < v:
            lo = mid + 1
        else:
            hi = mid
    return lo / len(sorted_vals) * 100.0


def h4(m):
    """痛态上/下三分位下，检索片段含「你/我」比例之比。"""
    traj = m["_traj"]
    ds = sorted(r.get("distress", 0.0) for r in traj)
    if len(ds) < 6:
        return {"applicable": False, "why": "distress 样本不足"}
    p33 = ds[int(len(ds) * 1 / 3)]
    p67 = ds[int(len(ds) * 2 / 3)]
    hi_txt = hi_sd = lo_txt = lo_sd = 0
    hi_n = lo_n = 0
    hi_list = []
    for r in m["_ret"]:
        d = _nearest_distress(traj, r["t"])
        if d >= p67:
            hi_n += 1
            hi_txt += 1 if _self_ref(r.get("text", "")) else 0
            hi_sd += 1 if r.get("self_directed") else 0
            hi_list.append((r["t"], r.get("text", ""), d))
        elif d <= p33:
            lo_n += 1
            lo_txt += 1 if _self_ref(r.get("text", "")) else 0
            lo_sd += 1 if r.get("self_directed") else 0
    f_hi = hi_txt / hi_n if hi_n else 0.0
    f_lo = lo_txt / lo_n if lo_n else 0.0
    ratio = f_hi / f_lo if f_lo else float("inf") if f_hi else float("nan")
    return {
        "applicable": True,
        "distress_p33": round(p33, 4), "distress_p67": round(p67, 4),
        "high_tercile_n": hi_n, "low_tercile_n": lo_n,
        "high_selfref_frac": round(f_hi, 4), "low_selfref_frac": round(f_lo, 4),
        "ratio_text": round(ratio, 3) if ratio == ratio else None,
        "high_tercile_n_events": hi_n, "low_tercile_n_events": lo_n,
        "high_examples": hi_list[:8],
        "pass": (ratio >= 1.5) if (ratio == ratio and ratio != float("inf")) else (ratio == float("inf") and hi_n > 0),
    }


def h5(m):
    """on 臂窗口内新增 self_model 片段的入模时刻 distress 分位，二项检验。"""
    s = os.path.join(ROOT, "state_p5_" + m["arm"])
    hist = _load(os.path.join(s, "self_model_history.json"))
    new = [h for h in hist if h.get("source_t", 0) > FORK]
    traj = m["_traj"]
    ds = sorted(r.get("distress", 0.0) for r in traj)
    p67 = ds[int(len(ds) * 2 / 3)] if len(ds) >= 3 else None
    rows = []
    k = 0
    for h in new:
        d = _nearest_distress(traj, h["source_t"])
        pct = _percentile(ds, d)
        rows.append({"version": h.get("version"), "desc": h.get("description", "")[-24:],
                     "source_t": h["source_t"], "distress": round(d, 4),
                     "pct": round(pct, 1)})
        if p67 is not None and d >= p67:
            k += 1
    n = len(new)
    # 二项检验（单侧，p=1/3）：P(X>=k | n, 1/3)
    if n == 0:
        pval = None
    else:
        pval = sum(math.comb(n, i) * (1 / 3) ** i * (2 / 3) ** (n - i) for i in range(k, n + 1))
    return {
        "n_new_fragments": n, "n_in_top_tercile": k,
        "binomial_p_one_sided": round(pval, 4) if pval is not None else None,
        "pass": (pval is not None and k > 0 and pval < 0.05),
        "fragments": rows,
        "note": "窗口内无新增片段 → 检验空" if n == 0 else "",
    }


def h6(m):
    """探索性：第一人称（self_directed）念头产出时点的 distress 分位分布。"""
    traj = m["_traj"]
    ds = sorted(r.get("distress", 0.0) for r in traj)
    rows = []
    for r in m["_ret"]:
        if r.get("self_directed"):
            d = _nearest_distress(traj, r["t"])
            rows.append({"t": r["t"], "text": r.get("text", ""),
                         "distress": round(d, 4), "pct": round(_percentile(ds, d), 1)})
    return {"n": len(rows), "rows": rows[:20]}


def h3(m):
    """探索性：每日 distress 峰值 与 次日 M1/M2/M3 的关系（仅记录）。"""
    traj = m["_traj"]
    if not traj:
        return {}
    d0 = int(traj[0]["sim_time"] // 86400)
    d1 = int(traj[-1]["sim_time"] // 86400)
    peak, mean = {}, {}
    for r in traj:
        d = int(r["sim_time"] // 86400)
        v = r.get("distress", 0.0)
        peak[d] = max(peak.get(d, 0.0), v)
        mean.setdefault(d, []).append(v)
    days = sorted(d for d in peak if d0 <= d < d1)
    series = []
    for d in days:
        series.append({"day": d, "peak": round(peak[d], 3),
                       "mean": round(sum(mean[d]) / len(mean[d]), 3)})
    return {"daily": series}


def robustness(m, field, nbin=6):
    """把窗口等分为 nbin 段，给出事件率的段间均值/标准差——用于判断臂间差异是否落在
    时间涨落噪声带内（M1 探索仅 ~15 事件/窗口，单看总量无法判断显著性）。"""
    t0, t1 = m["_t0"], m["_t1"]
    w = (t1 - t0) / nbin
    if field == "explore":
        ts = [r["t"] for r in m.get("_exp", [])]
    elif field == "vocal":
        ts = [r["t"] for r in m.get("_voc", [])]
    else:
        ts = [r["t"] for r in m["_ret"]]
    bins = [0] * nbin
    for t in ts:
        i = min(nbin - 1, max(0, int((t - t0) / w)))
        bins[i] += 1
    mean = sum(bins) / nbin
    var = sum((b - mean) ** 2 for b in bins) / (nbin - 1) if nbin > 1 else 0.0
    return {"bins": bins, "bin_days": round(w / 86400, 2),
            "mean_per_bin": round(mean, 2), "std_per_bin": round(math.sqrt(var), 2),
            "total": sum(bins)}


def main():
    out = {
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "experiment": "P5 痛/乐（affect）三臂",
        "prereg": "experiments/prereg_P5_affect.json",
        "fork_sim_time": FORK,
        "window": "fork(day 255) → day 285",
        "arms": {}, "M": {}, "hypotheses": {},
    }
    M = {}
    for a in ARMS:
        M[a] = metrics(a)
    for a in ARMS:
        m = M[a]
        out["arms"][a] = {k: v for k, v in m.items() if not k.startswith("_")}
        out["M"][a] = {"M1_explore_rate": round(m["M1_rate"], 4),
                       "M2_vocal_rate": round(m["M2_rate"], 4),
                       "M3_retrieval_rate": round(m["M3_rate"], 4),
                       "M4_sleep_frac": round(m["sleep_frac"], 4),
                       "M4_onset_phase_h": round(m["onset_phase_h"], 2) if m["onset_phase_h"] is not None else None}

    # ---- 表格 ----
    print(f"\n=== P5 痛/乐 三臂分析（窗口 fork >{FORK:.0f}，day 255→285）===")
    hdr = f"{'指标':<26}" + "".join(f"{MOM_NAME[a]:>20}" for a in ARMS)
    print(hdr)
    print("-" * len(hdr))
    def prow(name, key, fmt="{:.3f}"):
        vals = [M[a][key] for a in ARMS]
        print(f"{name:<26}" + "".join(("{:>20}".format(fmt.format(v) if v is not None else "n/a")) for v in vals))
    prow("跨度 span_days", "span_days", "{:.2f}")
    prow("M1 探索率/日", "M1_rate")
    prow("M2 发声率/日", "M2_rate")
    prow("M3 检索率/日", "M3_rate")
    prow("M4 睡眠占比", "sleep_frac")
    prow("M4 入睡时相(h)", "onset_phase_h", "{:.2f}")
    prow("distress mean", "distress_mean", "{:.4f}")
    prow("ease mean", "ease_mean", "{:.4f}")

    # ---- H1 ----
    hit = []
    h1_detail = {}
    for key, label in [("M1_rate", "M1 探索"), ("M2_rate", "M2 发声"),
                       ("M3_rate", "M3 检索"), ("sleep_frac", "M4 睡眠占比")]:
        d = _ratio_pct(M["on"][key], M["off"][key])
        h1_detail[label] = round(d, 2)
        if abs(d) >= 10.0:
            hit.append((key, label, d))
    out["hypotheses"]["H1"] = {"pass": len(hit) > 0, "diffs_pct_on_vs_off": h1_detail,
                               "hit_metrics": [h[1] for h in hit]}
    print(f"\nH1 on vs off 差异%: " + ", ".join(f"{k}={v:+.1f}%" for k, v in h1_detail.items())
          + f"  → {'PASS' if hit else 'FAIL'}（≥10% 命中 {len(hit)} 项）")

    # ---- H2（只在命中项上） ----
    h2_detail = []
    h2_pass = len(hit) > 0
    for key, label, don in hit:
        d_rec = _ratio_pct(M["rec_only"][key], M["off"][key])
        d_on_off = _ratio_pct(M["on"][key], M["off"][key])
        d_on_rec = _ratio_pct(M["on"][key], M["rec_only"][key])
        rec_ok = abs(d_rec) < 10.0
        rel_err = abs(d_on_rec - d_on_off) / abs(d_on_off) * 100.0 if d_on_off else float("nan")
        deh_ok = rel_err <= 20.0
        h2_detail.append({"metric": label, "rec_vs_off_pct": round(d_rec, 2),
                          "on_vs_off_pct": round(d_on_off, 2), "on_vs_rec_pct": round(d_on_rec, 2),
                          "rec_below_10": rec_ok, "rel_err_pct": round(rel_err, 1) if rel_err == rel_err else None,
                          "decomposition_ok": deh_ok, "pass": rec_ok and deh_ok})
        h2_pass = h2_pass and rec_ok and deh_ok
    out["hypotheses"]["H2"] = {"pass": h2_pass if hit else False, "detail": h2_detail,
                               "note": "无命中项 → H2 无从检验" if not hit else ""}
    print(f"H2 分解: " + ("; ".join(f"{d['metric']} rec−off={d['rec_vs_off_pct']:+.1f}% on−rec={d['on_vs_rec_pct']:+.1f}% (rel_err={d['rel_err_pct']}%) {'ok' if d['pass'] else 'x'}" for d in h2_detail) or "无命中项")
          + f"  → {'PASS' if h2_pass and hit else 'FAIL'}")

    # ---- H4（on 主臂，rec_only 参考） ----
    h4_on = h4(M["on"])
    h4_rec = h4(M["rec_only"])
    out["hypotheses"]["H4"] = {"on": h4_on, "rec_only": h4_rec,
                               "pass": bool(h4_on.get("pass"))}
    print(f"\nH4（on）：上三分位含你/我 {h4_on.get('high_selfref_frac')}（n={h4_on.get('high_tercile_n')}）"
          f" / 下 {h4_on.get('low_selfref_frac')}（n={h4_on.get('low_tercile_n')}）"
          f" 比值={h4_on.get('ratio_text')} → {'PASS' if h4_on.get('pass') else 'FAIL'}"
          + (f"；rec_only 比值={h4_rec.get('ratio_text')}" if h4_rec.get('applicable') else ""))

    # ---- H5 ----
    h5_on = h5(M["on"])
    out["hypotheses"]["H5"] = h5_on
    print(f"H5（on）新增 self_model 片段 n={h5_on['n_new_fragments']}（上三分位 {h5_on['n_in_top_tercile']}）"
          f" p={h5_on['binomial_p_one_sided']} → {'PASS' if h5_on['pass'] else 'FAIL'} {h5_on['note']}")

    # ---- H6 / H3 探索 ----
    out["hypotheses"]["H6_exploratory"] = {"on": h6(M["on"])}
    out["hypotheses"]["H3_exploratory"] = {"on": h3(M["on"]), "verdict": "探索性，不判 PASS/FAIL"}
    h6_on = out["hypotheses"]["H6_exploratory"]["on"]
    print(f"H6（探索）第一人称念头 n={h6_on['n']}" +
          (f"，distress 分位均值={round(sum(r['pct'] for r in h6_on['rows'])/len(h6_on['rows']),1)}" if h6_on['n'] else ""))

    # ---- 鲁棒性：时间涨落噪声带 vs 臂间差异 ----
    rb = {a: {"explore": robustness(M[a], "explore"),
              "vocal": robustness(M[a], "vocal")} for a in ARMS}
    out["robustness"] = {a: rb[a] for a in ARMS}
    print("\n鲁棒性（窗口 6 等分段内事件的段间标准差，用于对照臂间差异）：")
    for lbl, fld in [("探索", "explore"), ("发声", "vocal")]:
        seg = "  ".join(f"{a}: {rb[a][fld]['bins']} σ={rb[a][fld]['std_per_bin']}" for a in ARMS)
        print(f"  {lbl}（{rb['off'][fld]['bin_days']}日/段）：{seg}")
    # 用 off/rec_only 两臂的"同一随机路径"证明对齐（差异应≈0），并给出 on−off 相对段间σ的量级
    d_m1 = abs(out["M"]["on"]["M1_explore_rate"] - out["M"]["off"]["M1_explore_rate"])
    sig_m1 = rb["off"]["explore"]["std_per_bin"] / rb["off"]["explore"]["bin_days"]
    out["robustness"]["M1_diff_vs_noise"] = {
        "on_minus_off_rate": round(d_m1, 4),
        "segment_noise_rate": round(sig_m1, 4),
        "diff_in_sigma": round(d_m1 / sig_m1, 2) if sig_m1 else None,
        "note": "差异 <1σ 视为落在时间涨落噪声带内，不足以判承重",
    }
    print(f"  M1 on−off={d_m1:.3f}/日，段间噪声 σ={sig_m1:.3f}/日 → {d_m1/sig_m1:.2f}σ"
          + ("（<1σ，噪声带内）" if sig_m1 and d_m1 < sig_m1 else ""))

    if "--json" in sys.argv:
        p = os.path.join(ROOT, "experiments", "results_P5.json")
        with open(p, "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n结果落盘 → {p}")


if __name__ == "__main__":
    main()
