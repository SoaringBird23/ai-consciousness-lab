#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2x 边界探针离线分析（>1σ）：xl(1.5σ) / xl2(2σ) 对结构指标的影响

对照：state_R2_ctl_none（e6.ablation=true，通道全切，day 285）——沿用 R2 口径。
窗口：fork 点 day 255 → 285（继承前缀 = state_exp/inner_speech.jsonl 行数）。

先验 MC（prereg_R2x 强制项，必须先过再看主判据）：
  MC0a 通道真的开火：background_state.json 的 reflow_fires 计数必须 >0
  MC0b 剂量真的超过噪声：reflow.s2 / s4 实测 sd ≥ 1.5，且 s4 未被 _clip 夹死
       （贴边比例过高 → "踢击被吸收"，不得把"没打开"读成"打开无效"）

主判据（四指标，与 R2/E6 同口径）：
  M1 检索速率(条/仿真日)  M2 多样性(窗口内独立型数)  M3 自我模型  M4 目标数
  阴性 = 全部与对照差异 <10%（沿用 R2 的判定带）
"""
import os
import json
import math
import sys

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTL = "state_R2_ctl_none"
ARMS = ["xl", "xl2"]
WINDOW_DAYS = 30.0
FORK_DAY = 255
BAND = 0.10


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def jload(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def inherit_prefix():
    p = os.path.join(LAB, "state_exp", "inner_speech.jsonl")
    n = 0
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                if line.strip():
                    n += 1
    return n


def max_day(state_dir):
    tj = read_jsonl(os.path.join(state_dir, "trajectory.jsonl"))
    return tj[-1].get("day", FORK_DAY) if tj else FORK_DAY


def window_retrievals(state_dir, n_inh):
    recs = read_jsonl(os.path.join(state_dir, "inner_speech.jsonl"))
    win = recs[n_inh:]
    retr = [r for r in win if r.get("type") == "retrieval" and r.get("text")]
    return win, retr


def s4_stats(state_dir):
    """窗口内（day > FORK_DAY）s4 的 sd / 贴边比例。"""
    vals = []
    for r in read_jsonl(os.path.join(state_dir, "trajectory.jsonl")):
        if r.get("day", 0) > FORK_DAY:
            vals.append(float(r.get("s4", 0.0)))
    if not vals:
        return None
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1))
    edge = sum(1 for v in vals if v <= 0.001 or v >= 0.999) / len(vals)
    return {"n": len(vals), "mean": m, "sd": sd,
            "min": min(vals), "max": max(vals), "edge_frac": edge}


def sm_summary(state_dir):
    d = jload(os.path.join(state_dir, "self_model.json"))
    if not isinstance(d, dict):
        return "无"
    txt = d.get("text") or d.get("current") or ""
    hist = jload(os.path.join(state_dir, "self_model_history.json"))
    nv = len(hist) if isinstance(hist, list) else "?"
    return "版本=%s 历史=%s 文本=『%s』" % (d.get("version", "?"), nv, txt)


def goals_summary(state_dir):
    d = jload(os.path.join(state_dir, "goals.json"))
    if isinstance(d, list):
        return "%d 条" % len(d)
    if isinstance(d, dict):
        for k in ("goals", "items", "list"):
            if isinstance(d.get(k), list):
                return "%d 条" % len(d[k])
        return "dict(%s)" % ",".join(list(d.keys())[:6])
    return "无"


def overlap(a_dir, c_dir, n_inh):
    """同 tick 命中率：jaccard + 共同 tick 上的措辞一致率。"""
    _, ra = window_retrievals(a_dir, n_inh)
    _, rc = window_retrievals(c_dir, n_inh)
    a = {r["t"]: r["text"] for r in ra}
    c = {r["t"]: r["text"] for r in rc}
    common = set(a) & set(c)
    if not common:
        return {"n_common": 0, "jaccard": 0.0, "agreement": 0.0}
    same = sum(1 for t in common if a[t] == c[t])
    return {"n_common": len(common),
            "jaccard": len(common) / len(set(a) | set(c)),
            "agreement": same / len(common)}


def vdiff(m, base):
    if not base:
        return None
    return (m - base) / base


def main():
    n_inh = inherit_prefix()
    print("=" * 84)
    print("R2x 边界探针分析 | 对照=%s | 继承前缀=%d | 窗口=day %d→%d (%.0f 仿真日)"
          % (CTL, n_inh, FORK_DAY, FORK_DAY + int(WINDOW_DAYS), WINDOW_DAYS))
    print("=" * 84)

    ctl_dir = os.path.join(LAB, CTL)
    _, ctl_r = window_retrievals(ctl_dir, n_inh)
    ctl_days = max(1.0, max_day(ctl_dir) - FORK_DAY)
    ctl_rate = len(ctl_r) / ctl_days
    ctl_div = len({r["text"] for r in ctl_r})
    print("\n【对照 %s】检索 %d 条 → %.1f 条/日 | 多样性 %d 型"
          % (CTL, len(ctl_r), ctl_rate, ctl_div))
    print("  自我模型：%s" % sm_summary(ctl_dir))
    print("  目标：%s" % goals_summary(ctl_dir))
    cs4 = s4_stats(ctl_dir)
    if cs4:
        print("  s4 窗口：mean=%.3f sd=%.3f [%.3f,%.3f] 贴边=%.1f%%"
              % (cs4["mean"], cs4["sd"], cs4["min"], cs4["max"],
                 100 * cs4["edge_frac"]))

    rows = []
    for arm in ARMS:
        d = os.path.join(LAB, "state_R2x_%s" % arm)
        if not os.path.isdir(d):
            print("\n【R2x:%s】目录不存在（未跑？）" % arm)
            continue
        day = 0
        tj = read_jsonl(os.path.join(d, "trajectory.jsonl"))
        if tj:
            day = tj[-1].get("day", 0)
        _, retr = window_retrievals(d, n_inh)
        elapsed = max(1.0, day - FORK_DAY)
        rate = len(retr) / elapsed
        div = len({r["text"] for r in retr})

        bg = jload(os.path.join(d, "background_state.json"), {}) or {}
        fires = bg.get("reflow_fires", {}) or {}
        n_fire = sum(v for v in fires.values() if isinstance(v, (int, float)))
        st = s4_stats(d) or {}
        cfg = jload(os.path.join(LAB, "config_R2x_%s.json" % arm), {}) or {}
        amp = (cfg.get("reflow", {}) or {}).get("s2")
        sd = st.get("sd") or 0.0
        nat_sd = (cs4 or {}).get("sd") or 0.0      # 预注册口径：对照线的 s4 自然 sd
        ratio = (amp / nat_sd) if amp and nat_sd > 1e-9 else None
        ratio_own = (amp / sd) if amp and sd > 1e-9 else None

        ov = overlap(d, ctl_dir, n_inh)

        print("\n" + "-" * 84)
        print("【R2x:%s】day=%s | reflow.target=%s 剂量=%.2f | 检索 %d 条 → %.1f 条/日 | 多样性 %d 型"
              % (arm, day, bg.get("reflow_target"), amp or -1, len(retr), rate, div))
        print("  MC0a 开火：%s 合计=%d %s"
              % (dict(fires), n_fire, "✓" if n_fire > 0 else "✗ 通道未开火→臂作废"))
        if not st:
            print("  MC0b 剂量/噪声：窗口内无轨迹数据（臂尚未推进到 day>%d）→ 暂不可判"
                  % FORK_DAY)
        else:
            print("  MC0b 剂量/噪声：reflow.s2=%.2f / 自然 sd=%.3f → %.2fσ %s"
                  "（本臂实测 sd=%.3f→%.2fσ，压缩即饱和征兆）| s4 贴边=%.1f%% %s"
                  % (amp or -1, nat_sd, ratio if ratio else -1,
                     "✓" if ratio and ratio >= 1.5 else "✗ 未超 1.5σ",
                     sd, ratio_own if ratio_own else -1,
                     100 * st.get("edge_frac", 0.0),
                     "✓" if st.get("edge_frac", 1.0) < 0.20 else "✗ 贴边过多(踢击被吸收)"))
        print("  M1 检索速率 %d 条/%s 日 = %.1f 条/日 | M2 多样性 %d 型"
              % (len(retr), ("%.0f" % elapsed) if elapsed == int(elapsed) else "%.1f" % elapsed,
                 rate, div))
        print("  M1 检索速率差=%s | M2 多样性差=%s"
              % (("%+.1f%%" % (100 * vdiff(rate, ctl_rate))) if ctl_rate else "n/a",
                 ("%+.1f%%" % (100 * (div - ctl_div) / ctl_div)) if ctl_div else "n/a"))
        print("  M3 自我模型：%s" % sm_summary(d))
        print("  M4 目标：%s" % goals_summary(d))
        print("  重叠 vs 对照：共同 tick=%d jaccard=%.3f 措辞一致率=%.1f%%"
              % (ov["n_common"], ov["jaccard"], 100 * ov["agreement"]))
        rows.append({"arm": arm, "day": day, "n_retr": len(retr), "rate": rate,
                     "div": div, "fires": fires, "n_fire": n_fire,
                     "amp": amp, "s4_sd": sd, "ratio": ratio,
                     "edge_frac": st.get("edge_frac"), "overlap": ov,
                     "sm": sm_summary(d), "goals": goals_summary(d)})

    # ---- 剂量单调性：lo/mid/hi(R2) + xl/xl2(R2x) ----
    print("\n" + "=" * 84)
    print("剂量阶梯汇总（R2 已跑 lo/mid/hi + 本次 xl/xl2；全部 vs 同一 ctl_none）")
    print("%-10s %-8s %-10s %-12s %-14s %s"
          % ("臂", "剂量", "σ", "检索/日", "多样性", "jaccard(对对照)"))
    print("-" * 84)
    prior = [("R2:lo", "state_R2_open_s4_lo"), ("R2:mid", "state_R2_open_s4_mid"),
             ("R2:hi", "state_R2_open_s4_hi")]
    for tag, dd in prior:
        p = os.path.join(LAB, dd)
        if not os.path.isdir(p):
            continue
        _, rr = window_retrievals(p, n_inh)
        cfg = jload(os.path.join(LAB, "config_%s.json" % dd.replace("state_", "")), {}) or {}
        amp = (cfg.get("reflow", {}) or {}).get("s2")
        st = s4_stats(p) or {}
        ov = overlap(p, ctl_dir, n_inh)
        print("%-10s %-8s %-10s %-12s %-14s %.3f"
              % (tag, amp, ("%.2f" % (amp / st["sd"])) if st.get("sd") else "?",
                 "%.1f" % (len(rr) / WINDOW_DAYS), len({r["text"] for r in rr}),
                 ov["jaccard"]))
    print("%-10s %-8s %-10s %-12s %-14s %.3f"
          % ("ctl", 0.0, "0", "%.1f" % ctl_rate, ctl_div, 1.0))
    for r in rows:
        print("%-10s %-8s %-10s %-12s %-14s %.3f"
              % ("R2x:" + r["arm"], r["amp"],
                 ("%.2f" % r["ratio"]) if r["ratio"] else "?",
                 "%.1f" % r["rate"], r["div"], r["overlap"]["jaccard"]))

    print("\n" + "=" * 84)
    print("判读：MC0 未过 → 该臂作废（不得把『没打开』读成『打开无效』）。")
    print("      MC0 通过且四指标全部 <%.0f%% 差异 → >1σ 仍阴性 → 『单向工作空间』定论闭合。"
          % (100 * BAND))
    print("=" * 84)


if __name__ == "__main__":
    main()
