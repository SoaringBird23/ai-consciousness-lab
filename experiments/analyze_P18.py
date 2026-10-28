"""analyze_P18.py — P18 组合（词级）

读取 state_P18_{off,full,shuf}/inner_speech.jsonl：取**末 30 日**的 retrieval 记录，
统计组合率、词法纯净、结构（相邻词对真实相继命中率）、整体新（未逐字听过）比例。

判据 H18a–H18d；落盘 experiments/results_P18.json。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 86400.0
T0_DEFAULT = 22002086.380798087
OUT = os.path.join(ROOT, "experiments", "results_P18.json")
ARMS = ["off", "full", "shuf"]
COMPOSE_RATE_THRESH = 0.10     # H18a：末窗组合率下限（组合确实发生）
STRUCT_GAP = 0.30              # H18c：full 结构指标须高于 shuf 的下限
PURITY_THRESH = 0.999          # H18b：零幻觉硬约束
NOVEL_THRESH = 0.60            # H18d：组合须「整体新」


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


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def analyze_arm(arm, t0):
    st = os.path.join(ROOT, f"state_P18_{arm}")
    rows = [r for r in load_jsonl(os.path.join(st, "inner_speech.jsonl"))
            if r.get("type") == "retrieval"]
    lo, hi = t0 + 30 * DAY, t0 + 60 * DAY
    win = [r for r in rows if lo <= float(r["t"]) < hi]
    comp = [r for r in win if r.get("composed")]
    n = len(win)
    res = {"arm": arm, "n_retrieval": n, "n_composed": len(comp),
           "composed_rate": (len(comp) / n) if n else 0.0}
    if comp:
        res["purity_mean"] = mean([r.get("purity") for r in comp])
        res["purity_min"] = min([r.get("purity", 1.0) for r in comp])
        res["struct_mean"] = mean([(r.get("n_pairs_real", 0) / r["n_pairs"])
                                   if r.get("n_pairs") else None for r in comp])
        res["novel_rate"] = mean([1.0 if r.get("novel") else 0.0 for r in comp])
        res["len_mean"] = mean([len(r.get("words", [])) for r in comp])
    else:
        res.update({"purity_mean": None, "purity_min": None, "struct_mean": None,
                    "novel_rate": None, "len_mean": None})
    return res


def main():
    t0 = load_json(os.path.join(ROOT, "experiments", "results_P14c.json"), {}).get(
        "fork_sim_time", T0_DEFAULT)
    t0 = float(t0)
    print(f"fork t0={t0}（day {t0/DAY:.2f}）；判据窗口=末30日")
    print("=" * 92)
    res = {"fork_sim_time": t0, "arms": {}}
    for a in ARMS:
        res["arms"][a] = analyze_arm(a, t0)
        m = res["arms"][a]
        print(f"  {a:5s} retrieval={m['n_retrieval']:5d} composed={m['n_composed']:4d} "
              f"rate={m['composed_rate']:.3f} purity={m['purity_min']} "
              f"struct={m['struct_mean'] and round(m['struct_mean'],3)} "
              f"novel={m['novel_rate'] and round(m['novel_rate'],3)} "
              f"len={m['len_mean'] and round(m['len_mean'],2)}")
    print("=" * 92)
    off, full, shuf = res["arms"]["off"], res["arms"]["full"], res["arms"]["shuf"]
    v = {}
    v["H18a_组合发生(full rate>=%.2f)" % COMPOSE_RATE_THRESH] = {
        "pass": bool(full["composed_rate"] >= COMPOSE_RATE_THRESH),
        "detail": f"full={full['composed_rate']:.3f} shuf={shuf['composed_rate']:.3f} off={off['composed_rate']:.3f}"}
    v["H18b_词法纯净(purity>=%.3f)" % PURITY_THRESH] = {
        "pass": bool(full["purity_min"] is not None and full["purity_min"] >= PURITY_THRESH),
        "detail": f"full purity_min={full['purity_min']}"}
    sf = full["struct_mean"] or 0.0
    ss = shuf["struct_mean"] or 0.0
    v["H18c_结构合理(full-shuf>=%.2f)" % STRUCT_GAP] = {
        "pass": bool((full["struct_mean"] is not None) and sf >= ss + STRUCT_GAP),
        "detail": f"full struct={ sf and round(sf,3)} shuf struct={ ss and round(ss,3)}"}
    v["H18d_整体新(novel>=%.2f)" % NOVEL_THRESH] = {
        "pass": bool(full["novel_rate"] is not None and full["novel_rate"] >= NOVEL_THRESH),
        "detail": f"full novel={full['novel_rate'] and round(full['novel_rate'],3)}"}
    res["verdicts"] = v
    res["note"] = ("词级组合：零幻觉=词法级（组合词均实听过，purity=1），重组=句法级（整体未逐字听过）。"
                   "shuf 为内容对照（词汇不变、词→词关联打乱）。")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("落盘：", OUT)
    for k, d in v.items():
        print(f"  [{'PASS' if d['pass'] else 'FAIL'}] {k} — {d['detail']}")


if __name__ == "__main__":
    main()
