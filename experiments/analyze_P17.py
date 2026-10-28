"""analyze_P17.py — P17 词汇爆发（人类式扩词）

读取 state_P17_{fixed,grow,growfast}/grounding.jsonl，复用 P16 的指称探针。
判据：H17a 扩词发生 / H17b 指称保持（承重）/ H17c 稀疏安全 / H17d 巩固纪律。
落盘 experiments/results_P17.json。
"""
import json
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 86400.0
WINDOW_S = 60 * DAY
T0_DEFAULT = 22002086.380798087
OUT = os.path.join(ROOT, "experiments", "results_P17.json")
ARMS = ["fixed", "grow", "growfast"]

import sys
sys.path.insert(0, os.path.join(ROOT, "experiments"))
import analyze_P16 as A16   # 复用 decode_acc / load_jsonl / WORLD


def analyze_arm(arm, t0):
    st = os.path.join(ROOT, f"state_P17_{arm}")
    rows = A16.load_jsonl(os.path.join(st, "grounding.jsonl"))
    split = t0 + 30 * DAY
    hi = t0 + WINDOW_S
    train = [r for r in rows if float(r["t"]) < split]
    test = [r for r in rows if split <= float(r["t"]) < hi]
    # 末30日实听唯一型数 & 每型样本量
    cnt = {}
    for r in test:
        cnt[r["w"]] = cnt.get(r["w"], 0) + 1
    n_types = len(cnt)
    med = statistics.median(cnt.values()) if cnt else 0
    acc_w, n_w = A16.decode_acc(train, test, A16.WORLD)
    # 分窗 acc 曲线（5 日一窗）——查 H17d
    curve = []
    for b in range(12):
        lo = t0 + b * 5 * DAY
        h_ = t0 + (b + 1) * 5 * DAY
        te = [r for r in rows if lo <= float(r["t"]) < h_]
        tr = [r for r in rows if float(r["t"]) < lo]
        if te and tr:
            a, _ = A16.decode_acc(tr, te, A16.WORLD)
            curve.append((b, round(a, 3) if a is not None else None))
    return {"arm": arm, "n_test": len(test), "types_end30": n_types,
            "median_per_type": med, "acc_world": (round(acc_w, 4) if acc_w is not None else None),
            "n_world": n_w, "curve": curve}


def main():
    t0 = T0_DEFAULT
    r = A16.load_json(os.path.join(ROOT, "experiments", "results_P14c.json"), {})
    if r.get("fork_sim_time"):
        t0 = float(r["fork_sim_time"])
    print(f"fork t0={t0}（day {t0/DAY:.2f}）；判据窗口=末30日")
    print("=" * 84)
    res = {"fork_sim_time": t0, "human_mode": "grow", "arms": {}}
    for a in ARMS:
        res["arms"][a] = analyze_arm(a, t0)
        m = res["arms"][a]
        print(f"  {a:9s} 末端型数={m['types_end30']:5d} 每型中位={m['median_per_type']:6.1f} "
              f"指称acc={m['acc_world']}(n={m['n_world']})")
    print("=" * 84)
    fx, gr, gf = res["arms"]["fixed"], res["arms"]["grow"], res["arms"]["growfast"]
    v = {}
    v["H17a_扩词发生(grow>=3x fixed)"] = {
        "pass": bool(fx["types_end30"] > 0 and gr["types_end30"] >= 3 * fx["types_end30"]),
        "detail": f"grow={gr['types_end30']} fixed={fx['types_end30']}"}
    v["H17b_指称保持(acc>=0.75 且 >=fixed-0.05)"] = {
        "pass": bool(gr["acc_world"] is not None and gr["acc_world"] >= 0.75
                     and (fx["acc_world"] is None or gr["acc_world"] >= fx["acc_world"] - 0.05)),
        "detail": f"grow acc={gr['acc_world']} fixed acc={fx['acc_world']}"}
    v["H17c_稀疏安全(每型中位>=10)"] = {
        "pass": bool(gr["median_per_type"] >= 10),
        "detail": f"grow 每型中位={gr['median_per_type']}"}
    drops = []
    for (b, a), (b2, a2) in zip(gr["curve"], gr["curve"][1:]):
        if a is not None and a2 is not None:
            drops.append(a - a2)
    v["H17d_巩固纪律(扩词后跌<0.10)"] = {
        "pass": bool((not drops) or max(drops) < 0.10),
        "detail": f"最大单窗跌幅={round(max(drops),3) if drops else None}"}
    res["verdicts"] = v
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("落盘：", OUT)
    for k, d in v.items():
        print(f"  [{'PASS' if d['pass'] else 'FAIL'}] {k} — {d['detail']}")


if __name__ == "__main__":
    main()
