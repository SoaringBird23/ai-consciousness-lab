"""analyze_P16.py — P16 指称落地

读取 state_P16_{off,full,shuf}/grounding.jsonl：
  用前半段（前 30 日）学 P(φ_class | w)，在后半段（后 30 日）做**二值解码**——
  对每次听到的 w 预测其世界类（field>0.5=HIGH / ≤0.5=LOW），命中率 acc（chance=0.5）。
分别报告 world 词 与 其它词；另报 N=5 时刻匹配（次级）。

判据 H16a–H16d；落盘 experiments/results_P16.json。
"""
import json
import os
import random
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 86400.0
WINDOW_S = 60 * DAY
T0_DEFAULT = 22002086.380798087
OUT = os.path.join(ROOT, "experiments", "results_P16.json")
WORLD_HI = {"球", "亮亮", "看那儿"}
WORLD_LO = {"灯", "那个", "在那儿"}
WORLD = WORLD_HI | WORLD_LO


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


def build_table(rows):
    """P(φ_class|w) 表（拉普拉斯平滑）。w -> {0: p, 1: p}。"""
    cnt = {}
    for r in rows:
        w, c = r["w"], int(r["phi"])
        row = cnt.setdefault(w, [0, 0])
        row[c] += 1
    tab = {}
    for w, (a, b) in cnt.items():
        tab[w] = {0: (a + 1.0) / (a + b + 2.0), 1: (b + 1.0) / (a + b + 2.0)}
    return tab


def decode_acc(train, test, subset=None):
    tab = build_table(train)
    ok = n = 0
    for r in test:
        w = r["w"]
        if subset is not None and w not in subset:
            continue
        p = tab.get(w)
        if p is None:
            pred = int(random.random() > 0.5)
        else:
            pred = 0 if p[0] >= p[1] else 1
        ok += 1 if pred == int(r["phi"]) else 0
        n += 1
    return (ok / n if n else None), n


def match5_acc(train, test, seed=16):
    """N=5 时刻匹配：1 真 + 4 随机干扰，按 P(cls(cand)|w) 选，随机断平。"""
    tab = build_table(train)
    rng = random.Random(seed)
    ok = n = 0
    for r in test:
        cands = [r] + [rng.choice(test) for _ in range(4)]
        p = tab.get(r["w"])
        if p is None:
            continue
        best, bs = [], -1.0
        for c in cands:
            s = p[int(c["phi"])]
            if s > bs:
                bs, best = s, [c]
            elif s == bs:
                best.append(c)
        pick = rng.choice(best)
        ok += 1 if pick is r else 0
        n += 1
    return (ok / n if n else None), n


def analyze_arm(arm, t0):
    st = os.path.join(ROOT, f"state_P16_{arm}")
    rows = load_jsonl(os.path.join(st, "grounding.jsonl"))
    split = t0 + 30 * DAY
    hi = t0 + WINDOW_S
    train = [r for r in rows if float(r["t"]) < split]
    test = [r for r in rows if split <= float(r["t"]) < hi]
    acc_all, n_all = decode_acc(train, test)
    acc_w, n_w = decode_acc(train, test, WORLD)
    acc_o, n_o = decode_acc(train, test, None)
    # 其它词 = 全部 - world
    ok_o = n2_o = 0
    tab = build_table(train)
    for r in test:
        if r["w"] in WORLD:
            continue
        p = tab.get(r["w"])
        pred = (0 if p[0] >= p[1] else 1) if p else int(random.random() > 0.5)
        ok_o += 1 if pred == int(r["phi"]) else 0
        n2_o += 1
    acc_other = (ok_o / n2_o) if n2_o else None
    # 学习曲线（world 词）
    def acc_range(lo, hi_):
        tr = [r for r in rows if float(r["t"]) < split]
        te = [r for r in rows if lo <= float(r["t"]) < hi_ and r["w"] in WORLD]
        return decode_acc(tr, te, WORLD)[0], len(te)
    acc_pre, n_pre = acc_range(t0, t0 + 15 * DAY)
    acc_post, n_post = acc_range(hi - 15 * DAY, hi)
    m5, n5 = match5_acc(train, test)
    return {"arm": arm, "n_train": len(train), "n_test": len(test),
            "acc_world": (round(acc_w, 4) if acc_w is not None else None), "n_world": n_w,
            "acc_other": (round(acc_other, 4) if acc_other is not None else None), "n_other": n2_o,
            "acc_pre15_world": (round(acc_pre, 4) if acc_pre is not None else None), "n_pre": n_pre,
            "acc_post15_world": (round(acc_post, 4) if acc_post is not None else None), "n_post": n_post,
            "match5": (round(m5, 4) if m5 is not None else None), "n_match5": n5}


def binom_p(ok, n, p0=0.5):
    """单侧二项 p（精确，n 小）。"""
    from math import comb
    if n == 0:
        return 1.0
    return sum(comb(n, k) * p0 ** k * (1 - p0) ** (n - k) for k in range(ok, n + 1))


def main():
    t0 = T0_DEFAULT
    r = load_json(os.path.join(ROOT, "experiments", "results_P14c.json"), {})
    if r.get("fork_sim_time"):
        t0 = float(r["fork_sim_time"])
    print(f"fork t0={t0}（day {t0/DAY:.2f}）；判据窗口=末30日；chance=0.5")
    print("=" * 88)
    res = {"fork_sim_time": t0, "arms": {}}
    for a in ("off", "full", "shuf"):
        res["arms"][a] = analyze_arm(a, t0)
        m = res["arms"][a]
        print(f"  {a:5s} train={m['n_train']:4d} test={m['n_test']:4d} "
              f"acc_world={m['acc_world']}(n={m['n_world']}) acc_other={m['acc_other']}(n={m['n_other']}) "
              f"pre={m['acc_pre15_world']} post={m['acc_post15_world']} match5={m['match5']}")
    print("=" * 88)
    off, full, shuf = res["arms"]["off"], res["arms"]["full"], res["arms"]["shuf"]
    v = {}

    def frac_to_ok(acc, n):
        return None if (acc is None or n == 0) else round(acc * n)

    a_ok = frac_to_ok(full["acc_world"], full["n_world"])
    a_p = binom_p(a_ok, full["n_world"], 0.5) if a_ok is not None else 1.0
    v["H16a_指称存在(acc>=0.75,p<0.01)"] = {
        "pass": bool(full["acc_world"] is not None and full["acc_world"] >= 0.75 and a_p < 0.01),
        "detail": f"full world acc={full['acc_world']}(n={full['n_world']}) p={a_p:.2e}"}
    v["H16b_内容特定(shuf<=0.60 且 full-shuf>=0.15)"] = {
        "pass": bool(full["acc_world"] is not None and shuf["acc_world"] is not None
                     and shuf["acc_world"] <= 0.60 and (full["acc_world"] - shuf["acc_world"]) >= 0.15),
        "detail": f"full={full['acc_world']} shuf={shuf['acc_world']}"}
    v["H16c_特异性(world-other>=0.20)"] = {
        "pass": bool(full["acc_world"] is not None and full["acc_other"] is not None
                     and (full["acc_world"] - full["acc_other"]) >= 0.20),
        "detail": f"world={full['acc_world']} other={full['acc_other']}"}
    v["H16d_学习曲线(post>=1.2x pre)"] = {
        "pass": bool(full["acc_post15_world"] is not None and full["acc_pre15_world"] is not None
                     and full["acc_pre15_world"] > 0
                     and full["acc_post15_world"] >= 1.2 * full["acc_pre15_world"]),
        "detail": f"pre={full['acc_pre15_world']} post={full['acc_post15_world']}"}
    res["verdicts"] = v
    res["note"] = "二值世界（field 双峰），chance=0.5；N=5 匹配为次级指标。"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("落盘：", OUT)
    for k, d in v.items():
        print(f"  [{'PASS' if d['pass'] else 'FAIL'}] {k} — {d['detail']}")


if __name__ == "__main__":
    main()
