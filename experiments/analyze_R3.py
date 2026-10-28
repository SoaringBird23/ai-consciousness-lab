"""analyze_R3.py —— R3 离线分析（不改系统）

读 state_R3_{spont_off,spont_gen,spont_loop,spont_full,spont_shuf,spont_replay}，
按 experiments/prereg_R3.json 的 metrics 出表：

  MC_开口 : n_acts / n_probes / n_writes（spont.json 计数器）
  M_生成  : 重组率 = composed / retrieval；重组占比随天数的 OLS 斜率
  M_回路  : 自预期误差 err 的逐日 OLS 斜率（spont.jsonl 的 err）
  M_耦合  : max_σi |g|、g_pos/g_neg；full vs shuf 的 |g| 置换检验
  M_行为  : vs spont_off 的逐 tick 检索重合（短语命中 / Jaccard / 首分歧）
  M_说明  : 全部相对 spont_off 的增量

对齐约定（与 R2 一致）：各臂同 fork 自 state_exp，剔除继承前缀（inner_speech.jsonl
的 N_INHERIT 条）；tick 网格相同，故 t 可对齐。天数由 trajectory 的 (day,sim_time)
对 + 算术映射：day(t) = fork_day + floor((t − fork_t)/86400)。

注意：M_耦合 的置换检验在"每臂单次运行"下样本极薄（仅 16 个 (σ,i) 单元），
其 p 值只作序性参考，不构成统计显著性的强证据——见 prereg 的 falsification 边界。

用法：./venv/bin/python experiments/analyze_R3.py [--json]
输入缺失（某臂未跑/未完成）时该行标注 n/a，不报错。
"""
import json
import os
import random
import sys

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARMS = ["spont_off", "spont_gen", "spont_loop",
        "spont_full", "spont_shuf", "spont_replay"]
ON_ARMS = [a for a in ARMS if a != "spont_off"]
BASE = "spont_off"                 # 行为对照 = 回归基线
N_PERM = 2000
SEC_PER_DAY = 86400.0


def _jsonl(path):
    if not os.path.exists(path):
        return None
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _state(arm):
    return os.path.join(LAB, "state_R3_" + arm)


def fork_params():
    """(fork_day, fork_t)：取自 state_exp 轨迹末条。"""
    traj = _jsonl(os.path.join(LAB, "state_exp", "trajectory.jsonl"))
    if not traj:
        return None, None
    last = traj[-1]
    return int(last.get("day", 0)), float(last.get("sim_time", 0.0))


def day_of_t(t, fork_day, fork_t):
    return fork_day + int((float(t) - fork_t) // SEC_PER_DAY)


def ols_slope(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / sxx


def gen_stats(arm, n_inherit, fork_day, fork_t):
    """M_生成：窗口内 retrieval 数、重组数、重组率、逐日斜率的输入。"""
    recs = _jsonl(os.path.join(_state(arm), "inner_speech.jsonl"))
    if recs is None:
        return None
    win = recs[n_inherit:]
    n_echo = sum(1 for r in win if r.get("type") == "echo")
    retr = [r for r in win if r.get("type") == "retrieval"]
    n_comp = sum(1 for r in retr if r.get("composed"))
    per_day = {}
    for r in retr:
        d = day_of_t(r["t"], fork_day, fork_t)
        comp, tot = per_day.get(d, (0, 0))
        per_day[d] = (comp + (1 if r.get("composed") else 0), tot + 1)
    days = sorted(per_day)
    fr = [per_day[d][0] / per_day[d][1] for d in days]
    return {
        "n_window": len(win), "n_echo": n_echo, "n_retrieval": len(retr),
        "n_composed": n_comp,
        "composed_rate": (n_comp / len(retr)) if retr else 0.0,
        "composed_rate_slope_per_day": ols_slope(days, fr),
        "days_span": (days[0], days[-1]) if days else (None, None),
        "n_days": len(days),
    }


def spont_stats(arm):
    """MC_开口 / M_耦合：spont.json。"""
    p = os.path.join(_state(arm), "spont.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        s = json.load(f)
    gpos = list(s.get("g_pos", []))
    gneg = list(s.get("g_neg", []))
    allg = gpos + gneg
    return {
        "enabled": s.get("enabled"), "compose": s.get("compose"),
        "self_predict": s.get("self_predict"),
        "learn_coupling": s.get("learn_coupling"), "shuffle": s.get("shuffle"),
        "n_obs": s.get("n_obs", 0), "n_acts": s.get("n_acts", 0),
        "n_writes": s.get("n_writes", 0), "n_probes": s.get("n_probes", 0),
        "err_ema": s.get("err_ema", 0.0), "err_now": s.get("err_now", 0.0),
        "g_pos": gpos, "g_neg": gneg,
        "max_abs_g": max((abs(x) for x in allg), default=0.0),
        "max_abs_g_pos": max((abs(x) for x in gpos), default=0.0),
        "max_abs_g_neg": max((abs(x) for x in gneg), default=0.0),
    }


def err_slope(arm, fork_day, fork_t):
    """M_回路：spont.jsonl 逐写回 err 的逐日均值 → 天数 OLS 斜率。"""
    recs = _jsonl(os.path.join(_state(arm), "spont.jsonl"))
    if not recs:
        return None, None
    per_day = {}
    for r in recs:
        if "err" not in r:
            continue
        d = day_of_t(r.get("t", 0.0), fork_day, fork_t)
        per_day.setdefault(d, []).append(float(r["err"]))
    days = sorted(per_day)
    means = [sum(per_day[d]) / len(per_day[d]) for d in days]
    return per_day, ols_slope(days, means)


def retrieval_map(arm, n_inherit):
    """{t:(text, heard_at)}，窗口内 type=retrieval（供行为重合比对）。"""
    recs = _jsonl(os.path.join(_state(arm), "inner_speech.jsonl"))
    if recs is None:
        return None
    out = {}
    for r in recs[n_inherit:]:
        if r.get("type") == "retrieval":
            out[r["t"]] = (r.get("text"), round(float(r.get("heard_at", -1.0)), 1))
    return out


def overlap(ctl, m, rng):
    common = sorted(set(ctl) & set(m))
    if not common:
        return {"n_common": 0}
    same_txt = sum(1 for t in common if ctl[t][0] == m[t][0])
    same_ent = sum(1 for t in common if ctl[t] == m[t])
    arm_txt = [m[t][0] for t in common]
    ctl_txt = [ctl[t][0] for t in common]
    hits = []
    for _ in range(N_PERM):
        rng.shuffle(arm_txt)
        hits.append(sum(1 for a, b in zip(ctl_txt, arm_txt) if a == b) / len(common))
    allt = sorted(set(ctl) | set(m))
    first = None
    for t in allt:
        a, b = ctl.get(t), m.get(t)
        if (a is None) != (b is None) or (a and b and a[0] != b[0]):
            first = t
            break
    return {
        "n_common": len(common),
        "phrase_agreement": same_txt / len(common),
        "entry_agreement": same_ent / len(common),
        "permutation_baseline": sum(hits) / len(hits),
        "jaccard": len(common) / len(set(ctl) | set(m)),
        "first_divergence_t": first,
    }


def coupling_test(full, shuf, rng):
    """full vs shuf：max|g| 差的 (σ,i)-单元置换检验（薄样本，序性参考）。"""
    if not full or not shuf:
        return None
    a = list(full["g_pos"]) + list(full["g_neg"])
    b = list(shuf["g_pos"]) + list(shuf["g_neg"])
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    obs = max(abs(x) for x in a) - max(abs(x) for x in b)
    pool = a + b
    na = len(a)
    cnt = 0
    for _ in range(N_PERM):
        rng.shuffle(pool)
        d = max(abs(x) for x in pool[:na]) - max(abs(x) for x in pool[na:])
        if abs(d) >= abs(obs):
            cnt += 1
    return {"full_max_abs_g": max(abs(x) for x in a),
            "shuf_max_abs_g": max(abs(x) for x in b),
            "diff": obs, "perm_p_two_sided": cnt / N_PERM, "n_cells": n,
            "caveat": "单次运行、n=16 单元，p 仅作序性参考"}


def main():
    fork_day, fork_t = fork_params()
    n_inherit = len(_jsonl(os.path.join(LAB, "state_exp", "inner_speech.jsonl")) or [])
    rng = random.Random(0)
    print("R3 离线分析（对照行为 = %s；继承前缀 %d 条已剔除；fork day=%s）"
          % (BASE, n_inherit, fork_day))

    base_map = retrieval_map(BASE, n_inherit)
    res = {"fork_day": fork_day, "n_inherit": n_inherit, "arms": {}}

    print()
    hdr = ("%-14s %7s %7s %7s | %6s %6s %7s | %8s %6s | %9s %9s %7s"
           % ("arm", "n_retr", "n_comp", "comp%", "n_acts", "n_prob",
              "max|g|", "err_ema", "slope", "jac", "phrase%", "1stdiv"))
    print(hdr)
    print("-" * len(hdr))

    for arm in ARMS:
        g = gen_stats(arm, n_inherit, fork_day, fork_t)
        sp = spont_stats(arm)
        _, eslope = err_slope(arm, fork_day, fork_t)
        m = retrieval_map(arm, n_inherit)
        ov = overlap(base_map, m, rng) if (base_map is not None and m is not None
                                           and arm != BASE) else None
        row = {"gen": g, "spont": sp, "err_slope_per_day": eslope, "overlap": ov}
        res["arms"][arm] = row

        def f(v, fmt="%s", na="n/a"):
            return na if v is None else (fmt % v)
        print("%-14s %7s %7s %7s | %6s %6s %7s | %8s %6s | %9s %9s %7s"
              % (arm,
                 f(g and g["n_retrieval"], "%d"), f(g and g["n_composed"], "%d"),
                 f(g and g["composed_rate"] * 100, "%.1f"),
                 f(sp and sp["n_acts"], "%d"), f(sp and sp["n_probes"], "%d"),
                 f(sp and sp["max_abs_g"], "%.4f"),
                 f(sp and sp["err_ema"], "%.2g"),
                 f(eslope, "%.2g"),
                 f(ov and ov.get("jaccard"), "%.3f"),
                 f(ov and ov.get("phrase_agreement", 0) * 100, "%.1f"),
                 f(ov and ov.get("first_divergence_t"), "%.0f")))

    print()
    print("【M_耦合】full vs shuf 置换检验")
    ct = coupling_test(res["arms"].get("spont_full", {}).get("spont"),
                       res["arms"].get("spont_shuf", {}).get("spont"), rng)
    res["coupling_test"] = ct
    if ct:
        print("  full max|g|=%.4f  shuf max|g|=%.4f  Δ=%.4f  perm_p=%.3f（%s）"
              % (ct["full_max_abs_g"], ct["shuf_max_abs_g"], ct["diff"],
                 ct["perm_p_two_sided"], ct["caveat"]))
    else:
        print("  n/a（缺 full 或 shuf）")

    print()
    print("【g 向量】(σ=+1 与 σ=−1 各 8 维)")
    for arm in ARMS:
        sp = res["arms"][arm]["spont"]
        if sp:
            print("  %-12s pos=%s" % (arm, sp["g_pos"]))
            print("  %-12s neg=%s" % ("", sp["g_neg"]))

    print()
    print("comp%   = composed/retrieval；slope=自预期误差逐日斜率（负=在学）")
    print("jac/phrase%% = 相对 %s 的逐 tick 检索重合（1.0=与基线一致）" % BASE)

    if "--json" in sys.argv:
        out = os.path.join(LAB, "experiments", "results_R3.json")
        with open(out, "w") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        print("\n已写", out)


if __name__ == "__main__":
    main()
