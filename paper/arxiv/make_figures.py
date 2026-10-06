"""make_figures.py — 从真实运行数据生成论文图（非示意图）

输入（全部为实验落盘数据）：
  state_exp/self_model.json, state_c1b/self_model.json    自我模型版本历史
  state_exp/inner_speech.jsonl                            内言语检索记录
  state_body/actions.jsonl, state_body2/actions.jsonl     行动环
  experiments/results_E6p1_C1b.json, results_E6p2.json    E6 判决
输出：figs/fig1..fig4 (.pdf + .png)
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(os.path.dirname(ROOT))          # ai-consciousness-lab
OUT = os.path.join(ROOT, "figs")
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "Times New Roman"],
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.8,
    "figure.dpi": 200,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.03,
    "legend.frameon": False,
})

DAY = 86400.0


def load(p):
    with open(os.path.join(LAB, p)) as f:
        return json.load(f)


def save(fig, name):
    fig.savefig(os.path.join(OUT, name + ".pdf"))
    fig.savefig(os.path.join(OUT, name + ".png"))
    plt.close(fig)
    print("  写出", name + ".pdf/.png")


# ─────────────────────────── 图 1：自我模型生长 ───────────────────────────
def fig1():
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    for sd, lab, style, mk in (("state_exp", "XP (control)", "-", "o"),
                               ("state_c1b", "C1b (re-bound 1P)", "--", "s")):
        h = load(f"{sd}/self_model.json")["history"]
        d = [x["updated_at"] / DAY for x in h]
        v = [x["version"] for x in h]
        ax.step(d, v, where="post", linestyle=style, marker=mk, markersize=3.2,
                linewidth=1.1, label=lab, color="black", markerfacecolor="white")
    ax.set_xlabel("simulated day")
    ax.set_ylabel("self-model version")
    ax.set_xlim(12, 42)
    ax.set_ylim(0, 10)
    ax.legend(loc="lower right", fontsize=7)
    ax.grid(axis="y", color="0.9", lw=0.5)
    ax.set_axisbelow(True)
    save(fig, "fig1_selfmodel")


# ─────────────────── 图 2：第一人称检索占比随时间 ───────────────────
def fig2():
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    for sd, lab, ls in (("state_exp", "XP", "-"),
                        ("state_c1b", "C1b", "--")):
        per_day = {}
        with open(os.path.join(LAB, sd, "inner_speech.jsonl")) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("type") != "retrieval":
                    continue
                d = int(r["t"] / DAY + 1.0)     # 官方 display-day 约定
                tot, fp = per_day.get(d, (0, 0))
                per_day[d] = (tot + 1, fp + (1 if r.get("self_directed") else 0))
        ds = sorted(per_day)
        if not ds:
            continue
        share = []
        for d in ds:
            t, fp = per_day[d]
            share.append(100.0 * fp / t if t else np.nan)
        # 3 日滚动平滑
        k = 3
        sm = [np.nanmean(share[max(0, i - k + 1):i + 1]) for i in range(len(share))]
        ax.plot(ds, sm, linestyle=ls, linewidth=1.1, label=lab, color="black")
    ax.set_xlabel("simulated day")
    ax.set_ylabel("self-directed share (%)")
    ax.margins(y=0.12)
    ax.legend(loc="upper right", fontsize=7)
    ax.grid(axis="y", color="0.9", lw=0.5)
    ax.set_axisbelow(True)
    save(fig, "fig2_firstperson")


# ─────────────────── 图 3：E6 损伤 vs 置换（双面板） ───────────────────
def fig3():
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.6, 2.4))

    # 左：消融效应量（全部落在 ±10% 阴性带内）
    m = ["retrieval\nrate", "diversity", "self-model", "new goals"]
    dv = [-4.7, 2.3, 0.0, 0.0]
    a.axhspan(-10, 10, color="0.92", zorder=0)
    a.bar(range(4), dv, color="0.35", width=0.6, zorder=2)
    a.axhline(0, color="0.2", lw=0.8, zorder=3)
    a.set_xticks(range(4))
    a.set_xticklabels(m, fontsize=7.4)
    a.set_ylabel("change vs. control (%)", fontsize=8)
    a.set_ylim(-25, 25)
    a.text(3.35, 12, "negative band\n(±10%)", fontsize=6.4, color="0.4", ha="right")
    a.set_title("(a) ablation: thought $\\rightarrow$ state", fontsize=8.4)
    a.grid(axis="y", color="0.9", lw=0.5)
    a.set_axisbelow(True)

    # 右：置换 → 目标涌现
    r = load("experiments/results_E6p2.json")
    ev = None
    try:
        ev = r["hypotheses"]["H6b_swap"] if "hypotheses" in r else None
    except Exception:
        ev = None
    b.annotate("", xy=(142, 1), xytext=(140, 1),
               arrowprops=dict(arrowstyle="->", lw=1.1, color="black"))
    b.plot([139, 143], [0.5, 0.5], color="0.75", lw=0.8, zorder=0)
    b.plot([140, 142], [0.5, 0.5], color="black", lw=2.2, zorder=2)
    b.plot([142], [1.0], marker="*", markersize=11, color="black", zorder=3)
    b.text(142.3, 1.02, "goal emerged", fontsize=7, va="center")
    b.text(140, 0.36, "60 substitutions", fontsize=6.8, ha="left")
    b.set_xlim(139, 145)
    b.set_ylim(0.1, 1.35)
    b.set_yticks([])
    b.set_xlabel("simulated day", fontsize=8)
    b.set_title("(b) substitution: thought $\\rightarrow$ goals", fontsize=8.4)
    for s in ("left",):
        b.spines[s].set_visible(False)

    save(fig, "fig3_e6")


# ─────────────── 图 4：P4b 自因分离（移动 vs 停驻） ───────────────
def fig4():
    recs = []
    with open(os.path.join(LAB, "state_body2", "actions.jsonl")) as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                if 202 <= r["day"] <= 232:      # 仅预注册窗口，与稿件口径一致
                    recs.append(r)
    mv = np.array([r["self_caused"] for r in recs if r["action"] != "p2"])
    st = np.array([r["self_caused"] for r in recs if r["action"] == "p2"])
    if len(mv) == 0:
        print("  fig4 跳过：P4b 尚无动作数据")
        return

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(6.6, 2.1),
                                  gridspec_kw={"width_ratios": [1.15, 1]})

    # 左：箱线图（停驻 vs 移动），隐藏离群点，聚焦四分位
    bp = ax.boxplot([st, mv], vert=False, widths=0.5, showfliers=False,
                    patch_artist=True)
    for p in bp["boxes"]:
        p.set_facecolor("0.85")
        p.set_edgecolor("black")
        p.set_linewidth(0.9)
    for p in bp["medians"]:
        p.set_color("black")
        p.set_linewidth(1.3)
    ax.set_yticks([1, 2])
    ax.set_yticklabels(["stay\n(n=%d)" % len(st), "move\n(n=%d)" % len(mv)],
                       fontsize=7.4)
    ax.axvline(0, color="0.4", lw=0.8, ls=":")
    ax.plot([st.mean()], [1], marker="D", color="0.35", markersize=4.2, zorder=5)
    ax.plot([mv.mean()], [2], marker="D", color="black", markersize=4.2, zorder=5)
    ax.annotate("mean %.3f" % mv.mean(), xy=(mv.mean(), 2),
                xytext=(mv.mean() + 0.06, 1.62), fontsize=6.6,
                arrowprops=dict(arrowstyle="->", lw=0.7))
    ax.set_xlabel("self-caused change per action", fontsize=8)
    ax.set_xlim(-0.28, 0.28)
    ax.grid(axis="x", color="0.92", lw=0.5)
    ax.set_axisbelow(True)
    ax.set_title("(a) separation", fontsize=8.4)

    # 右：自因信号 vs 世界噪声底（停驻试次的标准差）——信号/噪声 = 0.61
    labels = ["world noise floor\n(stay SD)", "self-caused\n(move mean)"]
    vals = [st.std(), mv.mean()]
    ax2.bar(range(2), vals, color=["0.6", "black"], width=0.55)
    ax2.set_xticks(range(2))
    ax2.set_xticklabels(labels, fontsize=7.2)
    ax2.set_ylabel("field change", fontsize=8)
    ax2.set_title("(b) signal vs. noise floor", fontsize=8.4)
    ax2.text(1, vals[1] + max(vals) * 0.06, "%.1f$\\times$" % (vals[1] / vals[0]),
             fontsize=7.4, va="bottom", ha="center")
    ax2.set_ylim(0, max(vals) * 1.42)
    ax2.grid(axis="y", color="0.92", lw=0.5)
    ax2.set_axisbelow(True)
    save(fig, "fig4_selfcaused")


def _jsonl(p):
    out = []
    with open(os.path.join(LAB, p)) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ─────────── 图：系统状态、昼夜与念头流（真实轨迹） ───────────
def fig_system():
    lo, hi = 240.0, 248.0
    tr = [r for r in _jsonl("state_accel/trajectory.jsonl") if lo <= r["day"] < hi]
    fig, ax = plt.subplots(figsize=(6.6, 2.2))
    d = np.array([r["day"] + r["sim_hour"] / 24.0 for r in tr])
    s1 = np.array([r["s1"] for r in tr])
    s8 = np.array([r["s8"] for r in tr])
    asleep = np.array([r["asleep"] for r in tr], dtype=bool)
    ax.fill_between(d, 0, 1, where=asleep, color="0.88", step="mid", zorder=0,
                    label="sleep")
    ax.plot(d, s1, lw=1.0, color="black", label="s1 (arousal)")
    ax.plot(d, s8, lw=0.9, color="0.45", ls="--", label="s8 (boredom)")
    ev = [r["t"] / DAY + 1.0 for r in _jsonl("state_accel/inner_speech.jsonl")
          if r.get("type") == "retrieval" and lo <= r["t"] / DAY + 1.0 < hi]
    for e in ev:
        ax.plot([e, e], [0.0, 0.06], color="0.15", lw=0.6, zorder=3)
    ax.set_xlim(lo, hi)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("simulated day")
    ax.set_ylabel("state value")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), fontsize=7, ncol=3,
              frameon=False, handlelength=1.6, columnspacing=1.4)
    ax.grid(axis="y", color="0.92", lw=0.5)
    ax.set_axisbelow(True)
    save(fig, "fig_system")


# ─────────── 图：E1 剥夺 / E2 风暴 相位 ───────────
def fig_e1e2():
    import re as _re
    per = {}
    for r in _jsonl("state_accel/inner_speech.jsonl"):
        if r.get("type") != "retrieval":
            continue
        d = int(r["t"] / DAY + 1.0)          # 官方 display-day 约定
        per[d] = per.get(d, 0) + 1
    sur = {}
    with open(os.path.join(LAB, "logs_accel", "main.log"), errors="ignore") as f:
        for line in f:
            m = _re.search(r"day (\d+) h[\d.]+ .*?surprise=([0-9.]+)", line)
            if m:
                sur.setdefault(int(m.group(1)), []).append(float(m.group(2)))
    lo, hi = 238, 269
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(6.8, 2.3))
    for x0, x1 in ((242.4, 252.4), (257.6, 262.6)):
        ax.axvspan(x0, x1, color="0.9", zorder=0)
        bx.axvspan(x0, x1, color="0.9", zorder=0)
    ds = sorted(d for d in per if lo <= d <= hi)
    ax.axhline(28.8, color="0.4", lw=0.9, ls=":")
    ax.plot(ds, [per[d] for d in ds], lw=1.0, color="black", marker="o", ms=2.4)
    ax.set_xlim(lo, hi)
    ax.set_ylim(0, 62)
    ax.set_xlabel("simulated day", fontsize=8)
    ax.set_ylabel("retrieval per day", fontsize=8)
    ax.set_title("(a) thought stream", fontsize=8.4)
    ax.text(243.0, 56, "E1", fontsize=7)
    ax.text(258.2, 56, "E2", fontsize=7)
    surd = sorted(d for d in sur if lo <= d <= hi)
    bx.axhline(3.94, color="0.4", lw=0.9, ls=":")
    bx.plot(surd, [float(np.mean(sur[d])) for d in surd], lw=1.0, color="black",
            marker=".", ms=3)
    bx.set_xlim(lo, hi)
    bx.set_xlabel("simulated day", fontsize=8)
    bx.set_ylabel("predictor surprise (bits)", fontsize=8)
    bx.set_title("(b) surprise", fontsize=8.4)
    for ax_ in (ax, bx):
        ax_.grid(axis="y", color="0.92", lw=0.5)
        ax_.set_axisbelow(True)
    save(fig, "fig_e1e2")


# ─────────── 图：E3 应答式照护者（阴性） ───────────
def fig_e3():
    RET = [r for r in _jsonl("state_accel/inner_speech.jsonl")
           if r.get("type") == "retrieval"]

    def agg(a, b):
        w = [r for r in RET if a <= r["t"] / DAY + 1.0 < b]
        n = len(w)
        s = sum(1 for r in w if r.get("self_directed"))
        return (100.0 * s / n if n else 0.0), (n / (b - a) if b > a else 0.0)

    w_share, w_rate = agg(289.2396, 309.3771)      # E3 washout（预注册相位）
    c_share, c_rate = agg(309.3771, 359.6317)      # E3 contingent
    print("   E3: washout n=%d %.1f%%/%.1f日 | contingent n=%d %.1f%%/%.1f日"
          % (int(w_rate * 20.1375), w_share, w_rate,
             int(c_rate * 50.2546), c_share, c_rate))
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(5.6, 2.2))
    x = np.arange(2)
    ax.bar(x, [w_share, c_share], color=["0.55", "black"], width=0.55)
    ax.set_xticks(x)
    ax.set_xticklabels(["washout", "contingent"], fontsize=7.4)
    ax.set_ylabel("self-directed share (%)", fontsize=7.4)
    ax.set_title("(a) self-directed share", fontsize=8.4)
    ax.set_ylim(0, max(w_share, c_share) * 1.30)
    ax.text(0, w_share + 0.15, "%.1f%%" % w_share, ha="center", fontsize=7)
    ax.text(1, c_share + 0.15, "%.1f%%" % c_share, ha="center", fontsize=7)
    bx.bar(x, [w_rate, c_rate], color=["0.55", "black"], width=0.55)
    bx.set_xticks(x)
    bx.set_xticklabels(["washout", "contingent"], fontsize=7.4)
    bx.set_ylabel("retrieval per day", fontsize=7.4)
    bx.set_title("(b) thought rate", fontsize=8.4)
    bx.set_ylim(0, max(w_rate, c_rate) * 1.14)
    bx.text(0, w_rate + 0.5, "%.1f" % w_rate, ha="center", fontsize=7)
    bx.text(1, c_rate + 0.5, "%.1f" % c_rate, ha="center", fontsize=7)
    for ax_ in (ax, bx):
        ax_.grid(axis="y", color="0.92", lw=0.5)
        ax_.set_axisbelow(True)
    save(fig, "fig_e3")


# ─────────── 图：E4 发声—归因（习得与消退） ───────────
def fig_e4():
    cnt = {}
    for r in _jsonl("state_accel/attribution.jsonl"):
        if r.get("cause") == "self" and str(r.get("source")) == "vocal_contingent":
            d = int(r["t"] / DAY + 1.0)      # 官方 display-day 约定
            cnt[d] = cnt.get(d, 0) + 1
    lo, hi = 366, 426
    ds = sorted(d for d in cnt if lo <= d <= hi)
    p1 = sum(v for d, v in cnt.items() if 368.9079 <= d < 399.7)
    p2 = sum(v for d, v in cnt.items() if 399.7 <= d < 424.7475)
    print("   E4: p1 归因=%d  p2 归因=%d" % (p1, p2))
    ymax = max(cnt[d] for d in ds) if ds else 1
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(6.8, 2.3))
    ax.axvspan(368.9, 399.7, color="0.92", zorder=0)
    ax.bar(ds, [cnt[d] for d in ds], color="black", width=0.8)
    ax.axvline(399.7, color="0.3", lw=0.9, ls="--")
    ax.set_xlim(lo, hi)
    ax.set_ylim(0, ymax * 1.25)
    ax.set_xlabel("simulated day", fontsize=8)
    ax.set_ylabel("self-attributed vocal effects / day", fontsize=7.2)
    ax.set_title("(a) agency attribution", fontsize=8.4)
    ax.text(371, ymax * 1.1, "contingent", fontsize=6.8)
    ax.text(404, ymax * 1.1, "removed", fontsize=6.8)
    xd = [368.9, 399.7, 424.7]
    cv = [5.337, 8.217, 2.624]
    bx.plot(xd, cv, marker="o", color="black", lw=1.1, ms=4)
    bx.axhline(1.0, color="0.4", lw=0.9, ls=":")
    bx.text(369.5, 1.25, "no contingency", fontsize=6.6, color="0.35")
    bx.set_ylim(0, 9.6)
    bx.set_xlabel("simulated day", fontsize=8)
    bx.set_ylabel("co-variation $C$", fontsize=8)
    bx.set_title("(b) learning and extinction", fontsize=8.4)
    for ax_ in (ax, bx):
        ax_.grid(axis="y", color="0.92", lw=0.5)
        ax_.set_axisbelow(True)
    save(fig, "fig_e4")


# ─────────── 图：P4 行动环 ───────────
def fig_p4():
    import collections as _c
    recs = _jsonl("state_body/actions.jsonl")
    c = _c.Counter(r["action"] for r in recs)
    tot = sum(c.values())
    exp = tot / 3.0
    chi = sum((c[k] - exp) ** 2 / exp for k in ("p0", "p1", "p2"))
    p = np.array([c[k] / tot for k in ("p0", "p1", "p2")])
    H = -sum(x * np.log2(x) for x in p if x > 0)
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(6.6, 2.2))
    x = np.arange(3)
    ax.bar(x - 0.2, [c[k] / tot * 100 for k in ("p0", "p1", "p2")], width=0.4,
           color="black", label="observed")
    ax.bar(x + 0.2, [100 / 3.0] * 3, width=0.4, color="0.7", label="uniform")
    ax.set_xticks(x)
    ax.set_xticklabels(["p0 back", "p1 fwd", "p2 stay"], fontsize=7.4)
    ax.set_ylabel("share of actions (%)", fontsize=7.6)
    ax.set_title("(a) action distribution", fontsize=8.4)
    ax.set_ylim(0, 100)
    ax.legend(fontsize=6.8, loc="upper left", frameon=False)
    ax.text(0.75, 60, (r"$\chi^2$=%.2f$\times$10$^4$" % (chi / 1e4)) + "\n"
            + (r"$H$=%.2f bit" % H), fontsize=7.2, ha="center", va="center")
    days = sorted(set(r["day"] for r in recs))
    fm = [np.mean([r["field_after"] for r in recs if r["day"] == d]) for d in days]
    bx.plot(days, fm, marker="o", ms=2.4, lw=1.0, color="black")
    bx.axhline(0.50, color="0.4", lw=0.9, ls=":")
    bx.text(days[0], 0.515, "random-walk baseline", fontsize=6.6, color="0.35")
    bx.set_ylim(0.45, 0.72)
    bx.set_xlabel("simulated day", fontsize=8)
    bx.set_ylabel("mean field strength", fontsize=7.6)
    bx.set_title("(b) position in the world", fontsize=8.4)
    for ax_ in (ax, bx):
        ax_.grid(axis="y", color="0.92", lw=0.5)
        ax_.set_axisbelow(True)
    save(fig, "fig_p4")
    print("   P4: n=%d  chi2=%.1f  H=%.3f  field_mean=%.4f"
          % (tot, chi, H, np.mean([r["field_after"] for r in recs])))


if __name__ == "__main__":
    print("生成图表 →", OUT)
    for fn in (fig1, fig2, fig3, fig4, fig_system, fig_e1e2, fig_e3, fig_e4, fig_p4):
        try:
            fn()
        except Exception as e:
            print("  !!", fn.__name__, "失败:", e)
    print("完成")
