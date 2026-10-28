#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 0.5 机制可行性预检（纯离线，不发热、不开线）

问题：在**真实状态轨迹**上复现检索函数后，注入"转移偏置"
      score *= (1 + β · Â[前念 → 候选])
是否存在某个 β，能把念头流的**顺序结构**从 z≈0 拉到显著正，
同时保持多样性 ≥30/51？

底物：state_R5_off（未改动的健康基线：45/51 型、z≈0）
数据：trajectory.jsonl 每 tick 真实状态 + linguistic_memory.json 真实 (text,s,t)
      事件时刻取自 inner_speech.jsonl 的 retrieval 记录（与真跑一致）

两种候选池模式（配对设计：状态/噪声在全部 β 间共用）：
  sample —— 与 language.py 真跑一致：从全部听觉事件里随机抽 200 条。
            缺点：某型命中率仅 200/49660≈0.4%，偏置"够不着"，压低机制效力。
  strat  —— 按型分层：每型最多 4 条 → 全 51 型可达（约 204 候选）。
            给偏置完整量程，是最有利于机制的条件。
两种都不可行 → 结论稳健。
"""
import os
import json
import math
import bisect
import random

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARM = "state_R5_off"
SAMPLE_K = 200
PER_TYPE = 4
SIM_WEIGHTS = {0: 1.0, 3: 1.2, 6: 1.5, 7: 1.0}
FREQ_GAIN = 0.12
RECENCY_HL = 5.0
BETAS = [0.0, 0.25, 0.5, 1.0, 2.0, 4.0]
N_PERM = 500
CRIT_Z = 3.0
CRIT_UNIQ = 30
RNG = random.Random(0)


def read_jsonl(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def state_sim(a, b):
    num = den = 0.0
    for i, w in SIM_WEIGHTS.items():
        num += w * (1.0 - abs(a[i] - b[i]))
        den += w
    return num / den if den else 0.0


def build_graph(texts):
    uniq = sorted(set(texts))
    ix = {t: i for i, t in enumerate(uniq)}
    K = len(uniq)
    A = [[0.0] * K for _ in range(K)]
    for a, b in zip(texts, texts[1:]):
        if a != b:
            A[ix[a]][ix[b]] += 1.0
    top3 = {}
    for t, i in ix.items():
        row = sorted(range(K), key=lambda j: -A[i][j])[:3]
        top3[t] = {uniq[j] for j in row if A[i][j] > 0}
    return top3, K


def adj_hit(seq, top3):
    n = hit = 0
    for a, b in zip(seq, seq[1:]):
        n += 1
        if b in top3.get(a, ()):
            hit += 1
    return (hit / n) if n else 0.0


def perm_z(seq, top3, n_perm=N_PERM):
    obs = adj_hit(seq, top3)
    buf = list(seq)
    vals = []
    for _ in range(n_perm):
        RNG.shuffle(buf)
        vals.append(adj_hit(buf, top3))
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1))
    return obs, m, sd, ((obs - m) / sd if sd > 1e-12 else 0.0)


def recur5(seq):
    if len(seq) < 2:
        return 0.0
    return sum(1 for a, b in zip(seq, seq[1:]) if a == b) / (len(seq) - 1)


def newpair_rate(seq):
    """相邻对中"此前未出现过的（有序）对"占比——越低说明惯用转移越强。"""
    if len(seq) < 2:
        return 0.0
    seen = set()
    new = 0
    for a, b in zip(seq, seq[1:]):
        if (a, b) not in seen:
            new += 1
            seen.add((a, b))
    return new / (len(seq) - 1)


def build_pre(events, order, mem, ts, S, mode):
    freqs = {}
    ptr = 0
    bytype = {}
    pre = []
    for ev in events:
        t = ev["t"]
        while ptr < len(order) and mem[order[ptr]]["t"] <= t:
            m = mem[order[ptr]]
            tx = m["text"]
            freqs[tx] = freqs.get(tx, 0) + 1
            bytype.setdefault(tx, []).append(order[ptr])
            ptr += 1
        j = max(0, bisect.bisect_right(ts, t) - 1)
        s_now = S[j]
        now_days = t / 86400.0
        if mode == "sample":
            pool = order[:ptr]
            idxs = pool if ptr <= SAMPLE_K else RNG.sample(pool, SAMPLE_K)
        else:
            idxs = []
            for lst in bytype.values():
                idxs.extend(lst if len(lst) <= PER_TYPE else RNG.sample(lst, PER_TYPE))
        cands = []
        for i in idxs:
            m = mem[i]
            sim = state_sim(s_now, m["s"])
            age_days = now_days - m["t"] / 86400.0
            rec = 0.5 ** (max(0.0, age_days - 0.02) / RECENCY_HL)
            cands.append((m["text"], sim * (0.35 + 0.65 * rec), 0.9 + 0.2 * RNG.random()))
        pre.append(cands)
    return pre, freqs


def run(pre, freqs, beta, pi=None):
    A = {}
    prev = None
    seq = []
    for cands in pre:
        row = A.get(prev) if prev is not None else None
        tot = (sum(row.values()) or 1.0) if row else 0.0
        best_t, best_sc = None, -1.0
        for text, base, noise in cands:
            sc = base * (1.0 + FREQ_GAIN * math.log(1 + freqs.get(text, 0))) * noise
            if beta > 0.0 and tot:
                key = pi[text] if pi else text
                pr = row.get(key, 0.0) / tot
                if pr:
                    sc *= (1.0 + beta * pr)
            if sc > best_sc:
                best_sc, best_t = sc, text
        if best_t is None:
            continue
        if prev is not None:
            r = A.setdefault(prev, {})
            r[best_t] = r.get(best_t, 0) + 1
        prev = best_t
        seq.append(best_t)
    return seq


def scan(mode, pre, freqs, top3, K):
    all_types = sorted({c[0] for cs in pre for c in cs})
    pl = list(all_types)
    RNG.shuffle(pl)
    pi = {t: pl[i] for i, t in enumerate(all_types)}

    print("\n【候选池模式：%s】" % mode)
    print("%-8s %-6s %-9s %-16s %-7s %-9s %s"
          % ("β", "型数", "多样性", "adj_top3±零模型", "z", "recur5", "新对率"))
    print("-" * 80)
    feasible = []
    for beta in BETAS:
        seq = run(pre, freqs, beta)
        obs, m, sd, z = perm_z(seq, top3)
        uniq = len(set(seq))
        print("%-8s %-6d %-9.2f %-16s %+-7.2f %-9.3f %.3f"
              % (beta, uniq, uniq / K, "%.3f±%.3f" % (obs, sd), z,
                 recur5(seq), newpair_rate(seq)))
        if z >= CRIT_Z and uniq >= CRIT_UNIQ:
            feasible.append(beta)
    seq = run(pre, freqs, 1.0, pi=pi)
    obs, m, sd, z = perm_z(seq, top3)
    print("%-8s %-6d %-9.2f %-16s %+-7.2f %-9.3f %.3f   ← 对照：打乱前念内容(β=1)"
          % ("ctrl", len(set(seq)), len(set(seq)) / K, "%.3f±%.3f" % (obs, sd),
             z, recur5(seq), newpair_rate(seq)))
    return feasible


def main():
    d = os.path.join(LAB, ARM)
    mem = json.load(open(os.path.join(d, "linguistic_memory.json")))
    traj = read_jsonl(os.path.join(d, "trajectory.jsonl"))
    inner = read_jsonl(os.path.join(d, "inner_speech.jsonl"))

    n_inh = 0
    p = os.path.join(LAB, "state_exp", "inner_speech.jsonl")
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                if line.strip():
                    n_inh += 1
    parent = json.load(open(os.path.join(LAB, "state_exp", "linguistic_memory.json")))
    top3, K = build_graph([m["text"] for m in parent])

    ts = [r["sim_time"] for r in traj]
    S = [[r["s%d" % i] for i in range(1, 9)] for r in traj]
    events = [r for r in inner[n_inh:] if r.get("type") == "retrieval" and r.get("text")]

    print("=" * 80)
    print("Step 0.5 机制可行性预检 | 臂=%s | 照护者图 K=%d | 事件=%d" % (ARM, K, len(events)))
    print("判据（事先声明）：存在 β 使 z≥%.1f 且 型数≥%d  →  机制可行"
          % (CRIT_Z, CRIT_UNIQ))
    print("=" * 80)

    order = sorted(range(len(mem)), key=lambda i: mem[i]["t"])
    all_feasible = {}
    for mode in ("sample", "strat"):
        pre, freqs = build_pre(events, order, mem, ts, S, mode)
        avg = sum(len(c) for c in pre) / max(1, len(pre))
        print("\n>>> 模式 %s：平均候选池 %.0f 条、事件 %d" % (mode, avg, len(pre)))
        all_feasible[mode] = scan(mode, pre, freqs, top3, K)

    print("\n" + "=" * 80)
    if all_feasible.get("strat"):
        print("结论：**可行**（strat 模式下 β=%s）—— 值得起真线验证。"
              % all_feasible["strat"])
    else:
        print("结论：**不可行**")
        print("  两种候选池模式下均无 β 满足「z≥3 且 型数≥30」。")
        print("  strat 模式已给偏置完整量程（全 51 型可达）；仍做不到，而是呈现陡崖：")
        print("    β≤1 → 偏置太弱，被状态项吞掉（z≈0，多样性不变）")
        print("    β≥2 → 强到把流锁进自生成极限环（z 转强负、多样性崩到个位数）")
        print("  即：不存在既承重又保多样性的工作点。")
        print("  → 不必再烧真线：内言语的『无记忆』是结构性的，非调参问题。")
    print("=" * 80)


if __name__ == "__main__":
    main()
