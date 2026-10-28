"""analyze_P15b.py — P15b 反事实校准归因

4 个条件：
  full60  = state_P15_full      （复用 P15 数据，window=60s）
  shuf60  = state_P15_shuf      （复用 P15 数据，window=60s）
  full180 = state_P15b_full180  （新跑，window=180s）
  shuf180 = state_P15b_shuf180  （新跑，window=180s）

指标：逐次 ρ、按型聚合 ρ（型内 n≥5）、时间外推 ρ（前30日冻结 E → 后30日实现率）。
判据：H15b1 去噪抬升 / H15b2 时间外推 / H15b3 内容对照 / H15b4 归因判定。
落盘 experiments/results_P15b.json。
"""
import json
import os
import bisect
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 86400.0
WINDOW_S = 60 * DAY
T0_DEFAULT = 22002086.380798087
OUT = os.path.join(ROOT, "experiments", "results_P15b.json")

CONDS = [
    ("full60", "state_P15_full", 60.0),
    ("shuf60", "state_P15_shuf", 60.0),
    ("full180", "state_P15b_full180", 180.0),
    ("shuf180", "state_P15b_shuf180", 180.0),
]


def load_jsonl(p):
    out = []
    if not os.path.exists(p):
        return out
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
    def rk(v):
        o = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[o[j + 1]] == v[o[i]]:
                j += 1
            a = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[o[k]] = a
            i = j + 1
        return r
    rx, ry = rk(xs), rk(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else None


def binned_calibration(preds, reals, k=10, min_per_bin=3):
    """分箱校准：按预测值分成 k 个等量箱，箱内取实现均值 → Spearman(箱序, 均值)。
    稳健统计（用全部实例），不像小样本按型聚合那样不稳。返回 (ρ, 有效箱数)。"""
    n = len(preds)
    if n < k * min_per_bin:
        return None, 0
    idx = sorted(range(n), key=lambda i: preds[i])
    bins = [[] for _ in range(k)]
    for rank, i in enumerate(idx):
        bins[min(k - 1, rank * k // n)].append(reals[i])
    xs, ys = [], []
    for b in range(k):
        if len(bins[b]) >= min_per_bin:
            xs.append(b + 1)
            ys.append(statistics.mean(bins[b]))
    return (spearman(xs, ys), len(xs)) if len(xs) >= 5 else (None, len(xs))


def frozen_E(hist, split_t):
    """P15b：按型取『前 30 日冻结 E』——history 中 t>=split 的该型首个 predicted。
    严格只用决策时点值，不使用后 30 日信息。"""
    frozen = {}
    for h in sorted(hist, key=lambda x: float(x.get("t", 0))):
        t = float(h.get("t", 0))
        tx = h.get("text")
        if t >= split_t and tx and tx not in frozen:
            frozen[tx] = float(h.get("predicted", 0))
    return frozen


def analyze_cond(state_dir, t0, w_model):
    st = os.path.join(ROOT, state_dir)
    vocs = load_jsonl(os.path.join(st, "vocalizations.jsonl"))
    mem = load_json(os.path.join(st, "linguistic_memory.json"), [])
    rm = load_json(os.path.join(st, "response_model.json"), {})
    sp = sorted(float(m["t"]) for m in mem if isinstance(m, dict) and "t" in m)

    hi = t0 + WINDOW_S
    lo30 = hi - 30 * DAY
    split = t0 + 30 * DAY
    spw = [s for s in sp if lo30 <= s < hi]
    r_out = (len(spw) / (hi - lo30)) if (hi - lo30) > 0 else 0.0

    def n_in(v):
        return bisect.bisect_right(sp, v + w_model) - bisect.bisect_right(sp, v)

    post = [r for r in vocs if lo30 <= float(r["t"]) < hi
            and r.get("cf") and r["cf"].get("E_chosen") is not None]

    def realized(r):
        return (n_in(float(r["t"])) / w_model) / r_out if r_out > 0 else None

    # 逐次 ρ
    inst = [(r["cf"]["E_chosen"], realized(r)) for r in post if realized(r) is not None]
    rho_inst = spearman([p[0] for p in inst], [p[1] for p in inst]) if len(inst) >= 8 else None

    # 分箱校准 ρ（稳健，用全部实例）
    rho_bin, n_bins = binned_calibration([p[0] for p in inst], [p[1] for p in inst], 10, 3)

    # 时间外推 ρ：前30日冻结 E（history 决策时点）→ 后30日实现率
    hist = rm.get("history", [])
    frozen = frozen_E(hist, split)
    outs = {}
    for r in post:
        if float(r["t"]) >= split:
            rv = realized(r)
            if rv is not None:
                outs.setdefault(r["text"], []).append(rv)
    pairs = [(frozen[k], statistics.mean(v)) for k, v in outs.items()
             if k in frozen and len(v) >= 3]
    rho_oos = spearman([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 5 else None

    return {
        "dir": state_dir, "w_model": w_model,
        "n_post30": len(post),
        "rho_inst": (round(rho_inst, 4) if rho_inst is not None else None),
        "rho_bin": (round(rho_bin, 4) if rho_bin is not None else None),
        "n_bins": n_bins,
        "rho_oos": (round(rho_oos, 4) if rho_oos is not None else None),
        "n_pairs_oos": len(pairs),
    }


def main():
    t0 = T0_DEFAULT
    p14c = load_json(os.path.join(ROOT, "experiments", "results_P14c.json"), {})
    if p14c.get("fork_sim_time"):
        t0 = float(p14c["fork_sim_time"])
    print(f"fork t0={t0}（day {t0/DAY:.2f}）")
    print("=" * 92)
    res = {"fork_sim_time": t0, "conds": {}}
    for name, d, w in CONDS:
        res["conds"][name] = analyze_cond(d, t0, w)
        m = res["conds"][name]
        print(f"  {name:8s} n30={m['n_post30']:3d} ρ_inst={m['rho_inst']} "
              f"ρ_bin={m['rho_bin']}({m['n_bins']}箱) "
              f"ρ_oos={m['rho_oos']}(对 {m['n_pairs_oos']}，仅信息)")
    print("=" * 92)

    c = res["conds"]
    f60, f180, s60, s180 = c["full60"], c["full180"], c["shuf60"], c["shuf180"]

    v = {}
    # H15b1 分箱校准（去噪后应成立）
    h1 = (f180["rho_bin"] is not None and f180["rho_bin"] >= 0.5
          and f60["rho_bin"] is not None and f180["rho_bin"] > f60["rho_bin"])
    v["H15b1_分箱校准(ρ_bin>=0.5且>full60)"] = {
        "pass": bool(h1),
        "detail": f"full180 ρ_bin={f180['rho_bin']}({f180['n_bins']}箱) vs full60 ρ_bin={f60['rho_bin']}"}
    # H15b2 逐次 ρ 提升
    d_inst = ((f180["rho_inst"] or 0) - (f60["rho_inst"] or 0)) if f180["rho_inst"] is not None else None
    h2 = (d_inst is not None and d_inst >= 0.15)
    v["H15b2_逐次提升(Δρ_inst>=0.15)"] = {
        "pass": bool(h2),
        "detail": f"ρ_inst：full180={f180['rho_inst']} − full60={f60['rho_inst']} = {d_inst}"}
    # H15b3 归因判定
    if f180["rho_bin"] is not None and f180["rho_bin"] >= 0.5:
        attr = "噪声所限（去噪后校准成立）"
    elif d_inst is not None and d_inst < 0.1:
        attr = "能力所限（E 仅承载序信息、不承载量信息）"
    else:
        attr = "部分去噪有效，但仍未达 0.5（混合）"
    v["H15b3_归因判定"] = {"pass": bool(f180["rho_bin"] is not None and f180["rho_bin"] >= 0.5),
                        "detail": f"{attr}；Δρ_inst={d_inst}"}
    res["verdicts"] = v
    res["attribution"] = attr
    res["info_rho_oos"] = {
        "full60": f60["rho_oos"], "shuf60": s60["rho_oos"],
        "full180": f180["rho_oos"], "shuf180": s180["rho_oos"],
        "note": "外推 ρ 不具区分性（E 在任何臂都追踪真实结果），仅作信息记录，不作判据。"}
    res["power_ok"] = f180["n_post30"] >= 80

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("落盘：", OUT)
    for k, d in v.items():
        print(f"  [{'PASS' if d['pass'] else 'FAIL'}] {k} — {d['detail']}")


if __name__ == "__main__":
    main()
