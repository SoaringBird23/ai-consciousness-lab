#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 0 离线诊断：R5 为什么阴性（纯读盘，不开新线）

两问：
 (A) 胜者是否被高频型垄断？
     language.py 的候选池 = random.sample(self.memory, 200)，而 memory 是
     **逐次听觉事件**（约 5 万条 / 51 个型）→ P(某型进入候选) ∝ 它的出现次数。
     检验：① 胜者的频率排名分布；② 每型"进候选概率" p_include 归一化后的
     预测份额 vs 观测胜出份额（若两者吻合 → 打分前的候选池偏置已决定胜负）。
 (B) 念头流是否存在"超越重复"的内容结构？
     用保边缘的序列置换零模型重测 adj_top3_hit，并只统计异型转移 a≠b。
     若观测 ≈ 零模型 → 念头流是纯边际驱动的更新过程，无联想信息。
"""
import os
import json
import math
import random

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "state_R5_off"
ARMS = ["off", "full", "shuf", "nodep", "nodecay", "bigk"]
N_PERM = 1000
K_SAMPLE = 200          # 与 language.py 一致
RNG = random.Random(20261008)


def load_memory(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def inherit_prefix():
    """继承前缀 = 父态 inner_speech.jsonl 行数（臂内前 N 条为继承，须剔除）。"""
    p = os.path.join(LAB, "state_exp", "inner_speech.jsonl")
    n = 0
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                if line.strip():
                    n += 1
    return n


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def build_graph(mem):
    """从"听到顺序"重建一阶共现 → 每个型的 top3 后继集合。"""
    texts = [m["text"] for m in mem]
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
    return top3, K, uniq


def adj_hit(seq, top3, distinct_only=False):
    """相邻转移命中 top3 的比率。"""
    n = 0
    hit = 0
    for a, b in zip(seq, seq[1:]):
        if distinct_only and a == b:
            continue
        n += 1
        if b in top3.get(a, ()):  # noqa
            hit += 1
    return (hit / n) if n else 0.0, n


def perm_null(seq, top3, distinct_only, n_perm=N_PERM):
    obs, n_pairs = adj_hit(seq, top3, distinct_only)
    buf = list(seq)
    vals = []
    for _ in range(n_perm):
        RNG.shuffle(buf)
        v, _ = adj_hit(buf, top3, distinct_only)
        vals.append(v)
    m = sum(vals) / len(vals)
    var = sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1)
    sd = math.sqrt(var)
    z = (obs - m) / sd if sd > 1e-12 else 0.0
    return obs, m, sd, z, n_pairs


def p_include(c, N, k=K_SAMPLE):
    """不放回抽 k 个事件，某型（c 个事件）至少被抽中一次的概率。"""
    if c <= 0:
        return 0.0
    if N <= k:
        return 1.0
    prod = 1.0
    for i in range(k):
        num = N - c - i
        if num <= 0:
            return 1.0
        prod *= num / (N - i)
    return 1.0 - prod


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx < 1e-12 or sy < 1e-12:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def main():
    n_inh = inherit_prefix()
    parent_mem = load_memory(os.path.join(LAB, "state_exp", "linguistic_memory.json"))
    top3, K, uniq = build_graph(parent_mem)
    print("=" * 78)
    print("Step 0 离线诊断 | 继承前缀=%d | 照护者联想图 K=%d | 零模型置换=%d 次"
          % (n_inh, K, N_PERM))
    print("=" * 78)

    for arm in ARMS:
        d = os.path.join(LAB, "state_R5_%s" % arm)
        mem = load_memory(os.path.join(d, "linguistic_memory.json"))
        recs = read_jsonl(os.path.join(d, "inner_speech.jsonl"))
        win = recs[n_inh:]
        retr = [r for r in win if r.get("type") == "retrieval"]
        seq = [r.get("text") for r in retr if r.get("text")]

        print("\n" + "-" * 78)
        print("【%s】记忆=%d 条 | 窗口内念头=%d（检索 %d / 私语 %d）"
              % (arm, len(mem), len(win), len(retr), len(win) - len(retr)))

        # ---------- (A) 胜者频率垄断 ----------
        N = len(mem)
        freq = {}
        for m in mem:
            t = m.get("text")
            if t:
                freq[t] = freq.get(t, 0) + 1
        types = sorted(freq.items(), key=lambda kv: -kv[1])
        rank_of = {t: i + 1 for i, (t, _) in enumerate(types)}
        nty = len(types)
        if types:
            print("  频率头名：『%s』%d 条（占听觉 %.1f%%）| 型数=%d"
                  % (types[0][0], types[0][1], 100.0 * types[0][1] / max(1, N), nty))

        if seq:
            total = len(seq)
            from collections import Counter
            cnt = Counter(seq)
            ranks = sorted(rank_of.get(t, nty + 1) for t in seq)
            med = ranks[len(ranks) // 2]
            def share_within(kk):
                return sum(1 for t in seq if rank_of.get(t, 10 ** 9) <= kk) / total
            print("  胜者频率排名：中位=第 %d/%d 名 | 落在 top1=%.1f%% top3=%.1f%% "
                  "top5=%.1f%% top10=%.1f%%"
                  % (med, nty, 100 * share_within(1), 100 * share_within(3),
                     100 * share_within(5), 100 * share_within(10)))
            top = cnt.most_common(5)
            print("  最高频胜者：" + " | ".join("『%s』%.1f%%" % (t, 100.0 * c / total)
                                                for t, c in top))

            # 候选池偏置预测：p_include 归一化 vs 观测份额
            pi = {t: p_include(c, N) for t, c in types}
            s_pi = sum(pi.values()) or 1.0
            xs = [pi.get(t, 0.0) for t, _ in types]
            ys = [cnt.get(t, 0) / total for t, _ in types]
            r = pearson(xs, ys)
            pred = sorted(((pi.get(t, 0.0) / s_pi, t) for t, _ in types), reverse=True)
            print("  p_include(进候选概率) 与 观测份额 的 Pearson r = %.3f" % r)
            print("  预测份额 top3：" + " | ".join("『%s』%.1f%%" % (t, 100 * p)
                                                  for p, t in pred[:3]))
            obs_top3 = [t for t, _ in cnt.most_common(3)]
            print("  观测份额 top3：" + " | ".join("『%s』%.1f%%" % (t, 100.0 * cnt[t] / total)
                                                  for t in obs_top3))
            ovl = len(set(t for _, t in pred[:3]) & set(obs_top3))
            print("  → 预测/观测 top3 重合 %d/3（越高说明候选池偏置解释力越强）" % ovl)
            print("  序列前 24 条：" + " ".join(seq[:24]))

        # ---------- (B) 超越重复的内容结构 ----------
        if len(seq) >= 30:
            for tag, dist in (("全转移", False), ("异型转移 a≠b", True)):
                obs, m, sd, z, npair = perm_null(seq, top3, dist)
                print("  [%s] adj_top3=%.3f | 保边缘置换零模型=%.3f±%.3f | z=%+.2f | 对数=%d"
                      % (tag, obs, m, sd, z, npair))
            from collections import Counter
            cnt = Counter(seq)
            rec5 = (sum(1 for a, b in zip(seq, seq[1:]) if a == b)
                    / max(1, len(seq) - 1))
            print("  recur5(相邻同型率)=%.3f | 型多样性=%d/%d" % (rec5, len(cnt), K))

    print("\n" + "=" * 78)
    print("判读：")
    print(" A) 若胜者几乎全落在 top10 高频型、且 p_include 预测份额≈观测份额 →")
    print("    候选池按『出现次数』抽样已决定胜负，写回/联想在此之上无法起作用。")
    print(" B) 若各臂 z 均≈0（含 full）→ 念头流无超越边际重复的顺序结构，")
    print("    R5 测到的 adj_top3 抬升是『高频型反复获胜』的复读效应而非联想。")
    print("=" * 78)


if __name__ == "__main__":
    main()
