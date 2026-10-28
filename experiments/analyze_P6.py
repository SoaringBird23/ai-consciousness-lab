"""analyze_P6.py —— P6 语料扩容离线分析（只读，不改系统）

读 state_P6_{builtin,childes}，按 experiments/prereg_P6_corpus.json 出 M1–M5 与 H1–H3：

  M1 自我模型版本轨迹 : 首个碎片日龄、达 v3 日龄、末版本号、fork 后新增版本数
  M2 检索率/日        : fork 后检索条数 / 窗口日数
  M3 检索多样性       : 去重片段数（及占听到词表比）
  M4 涌现目标数       : language_state.json['goals'] 长度
  M5 语境绑定强度     : 高紧张态检索中『听到时高惊奇』片段占比 vs 基线（lift，双通道：
                        主 surprise=s7，副 valence=s2；见 m5_binding 说明）

判据（事前冻结）：
  H1_structure_holds : M2(childes)/M2(builtin) ∈ [0.5, 2.0] → PASS
  H2_growth_rate     : 探索性。fork 后两臂自我模型生长（新增版本数 / 首个新版日龄），不设 PASS/FAIL
  H3_binding_strength: M5(childes) ≥ M5(builtin) → PASS

设计要点：
  * 两臂由 `cp -R state_exp` fork，inner_speech.jsonl 的前 N 条为继承自母本的前缀，须剔除。
  * 母本已到 v6，故 v1–v6 为继承；H2 只对 fork 之后的新版本有意义（v3 日龄在臂间恒等，如实标注）。
  * 语料注入的旁证：听到词表去重数（childes 应远超 builtin）。M5 的『高紧张』用 trajectory.s4
    分位阈值；『高惊奇』用该臂听到事件 s7（=下标 6）的分位阈值（副通道报 s2 效价对照）。

用法：./venv/bin/python experiments/analyze_P6.py [--json]
"""
import json
import os
import sys
import time
from bisect import bisect_right

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARMS = ["builtin", "childes"]
BASE = "builtin"
TREAT = "childes"
DAY = 86400.0
P_HI = 0.75


def _jsonl(path):
    """读 JSONL。容忍被写入中残留的半行末尾（末行解析失败则丢弃）。"""
    if not os.path.exists(path):
        return None
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _state(arm):
    return os.path.join(LAB, "state_P6_" + arm)


def _mother_dir():
    return os.path.join(LAB, "state_exp")


def _count_lines(path):
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path) as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _inherit_prefix():
    """继承前缀 = 父态 state_exp/inner_speech.jsonl 的记录数（各臂 cp -R 全量继承该文件）。"""
    return _count_lines(os.path.join(_mother_dir(), "inner_speech.jsonl"))


def _load_json(path, default=None):
    """读 JSON；若正被采集进程写入（解析失败）则短暂重试，重试仍败则报错。"""
    if not os.path.exists(path):
        return default
    for attempt in range(4):
        try:
            with open(path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            if attempt == 3:
                raise RuntimeError("无法解析 %s——该文件可能正被采集进程写入，请待两臂停止后再分析。" % path)
            time.sleep(1.5)
    return default


def t2day(t):
    return t / DAY + 1.0


def q(vals, p):
    """线性插值分位数（纯 python，无依赖）。"""
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / (sxx ** 0.5 * syy ** 0.5)


def _fork_info():
    """母本末态：fork 日龄、母本最后自我模型 source_t（新版判定基线）。"""
    traj = _jsonl(os.path.join(_mother_dir(), "trajectory.jsonl"))
    fork_day = traj[-1].get("day") if traj else 0
    hist = _load_json(os.path.join(_mother_dir(), "self_model_history.json"), [])
    fork_self_t = max((h.get("source_t", 0) for h in hist), default=0)
    return fork_day, fork_self_t


def m1_selfmodel(arm, fork_self_t):
    hist = _load_json(os.path.join(_state(arm), "self_model_history.json"), [])
    if isinstance(hist, dict):
        hist = hist.get("history", [])
    versions = [h.get("version") for h in hist]
    days = [t2day(h.get("source_t", 0)) for h in hist]
    first_day = min(days) if days else None
    v3_day = None
    for h, d in zip(hist, days):
        if h.get("version") == 3:
            v3_day = d
            break
    post = [(h.get("version"), d, t2day(h.get("source_t", 0)))
            for h, d in zip(hist, days)
            if h.get("source_t", 0) > fork_self_t]
    return {
        "n_versions": len(hist),
        "final_version": max(versions) if versions else None,
        "first_fragment_day": first_day,
        "v3_day": v3_day,
        "n_postfork_versions": len(post),
        "first_postfork_version": (post[0][0] if post else None),
        "first_postfork_day": (post[0][1] if post else None),
        "postfork_versions": [{"version": v, "day": round(d, 2)} for v, d, _ in post],
    }


def _window(arm, fork_day):
    traj = _jsonl(os.path.join(_state(arm), "trajectory.jsonl"))
    if not traj:
        return None, None
    last = traj[-1]
    return last.get("day"), (last.get("day", 0) - fork_day)


def m2_m3(arm, n_inherit):
    recs = _jsonl(os.path.join(_state(arm), "inner_speech.jsonl"))
    if recs is None:
        return None
    win = recs[n_inherit:]
    retr = [r for r in win if r.get("type") == "retrieval"]
    seq = [r.get("text") for r in retr if r.get("text")]
    mem = _load_json(os.path.join(_state(arm), "linguistic_memory.json"), [])
    heard_types = set(m.get("text") for m in mem if isinstance(m, dict) and m.get("text"))
    return {
        "n_retr": len(seq),
        "n_uniq": len(set(seq)),
        "n_heard_events": len(mem),
        "n_heard_types": len(heard_types),
    }


def m4_goals(arm):
    ls = _load_json(os.path.join(_state(arm), "language_state.json"), {})
    goals = ls.get("goals", [])
    goals2 = _load_json(os.path.join(_state(arm), "goals.json"), None)
    n = len(goals) if isinstance(goals, list) else 0
    return {"n_goals_langstate": n,
            "goals_langstate": goals if isinstance(goals, list) else [],
            "n_goals_file": (len(goals2) if isinstance(goals2, list) else None)}


def _load_tension(arm):
    traj = _jsonl(os.path.join(_state(arm), "trajectory.jsonl"))
    if not traj:
        return None, None
    ts = [x.get("sim_time", 0) for x in traj]
    s4 = [x.get("s4", 0.0) for x in traj]
    return ts, s4


def m5_binding(arm, n_inherit):
    """高紧张态检索中『听到时高惊奇』片段占比 vs 基线 —— 双通道。

    prereg 的 M5 字面为『高惊奇期听到的片段在后续高紧张态被检索的比例』。
    历史实现误把 rec['heard_s2']（=s2）当作『高惊奇』，但 s2 实为【效价 valence】
    （见 language.py L426 注『念头携带的语境色彩』、config_R5_full.json 变量表）；
    真正的惊奇是 s7（预测误差，状态向量下标 6），且 retrieval 相似度权重
    SIM_WEIGHTS 恰含 s7(1.0) 与 s4(1.2)。故本版双通道并列：

      * 主通道 surprise : 听到时 s7 ≥ τ_7 ；与 prereg『高惊奇』字面一致
      * 副通道 valence  : 听到时 s2 ≥ τ_2 ；保留以对照 language.py 语义

    两通道均以 τ_4 = trajectory.s4 的 P_HI 分位为『高紧张态』。
    heard-time 通道取自 linguistic_memory 的完整状态向量，按 t 精确对齐到每条检索。
    """
    recs = _jsonl(os.path.join(_state(arm), "inner_speech.jsonl"))
    if recs is None:
        return None
    retr = [r for r in recs[n_inherit:]
            if r.get("type") == "retrieval" and r.get("t") is not None
            and r.get("heard_at") is not None]
    mem = _load_json(os.path.join(_state(arm), "linguistic_memory.json"), [])
    by_t = {}
    for m in mem:
        if (isinstance(m, dict) and isinstance(m.get("s"), list)
                and len(m["s"]) >= 8 and m.get("t") is not None):
            by_t[round(float(m["t"]), 1)] = m
    ts, s4 = _load_tension(arm)
    if not retr or not by_t or not ts:
        return {"n_retr": len(retr), "tau_7": None, "tau_2": None, "tau_4": None,
                "m5": None, "base": None, "lift": None, "r": None,
                "m5_v": None, "base_v": None, "lift_v": None, "r_v": None}
    s7_all = [by_t[k]["s"][6] for k in by_t]
    s2_all = [by_t[k]["s"][1] for k in by_t]
    tau_7 = q(s7_all, P_HI)
    tau_2 = q(s2_all, P_HI)
    tau_4 = q(s4, P_HI)
    hi = 0
    hi_hi = 0
    base_n = 0
    base_hi = 0
    hi_hi_v = 0
    base_hi_v = 0
    xs, ys = [], []
    xs_v, ys_v = [], []
    for r in retr:
        m = by_t.get(round(float(r["heard_at"]), 1))
        if m is None:
            continue
        i = bisect_right(ts, r["t"]) - 1
        if i < 0:
            continue
        tension = s4[i]
        s7 = m["s"][6]
        s2 = m["s"][1]
        xs.append(tension)
        ys.append(s7)
        xs_v.append(tension)
        ys_v.append(s2)
        base_n += 1
        if s7 >= tau_7:
            base_hi += 1
        if s2 >= tau_2:
            base_hi_v += 1
        if tension >= tau_4:
            hi += 1
            if s7 >= tau_7:
                hi_hi += 1
            if s2 >= tau_2:
                hi_hi_v += 1
    m5 = (hi_hi / hi) if hi else None
    base = (base_hi / base_n) if base_n else None
    lift = (m5 / base) if (m5 is not None and base) else None
    m5_v = (hi_hi_v / hi) if hi else None
    base_v = (base_hi_v / base_n) if base_n else None
    lift_v = (m5_v / base_v) if (m5_v is not None and base_v) else None
    return {"n_retr": len(retr), "n_used": base_n,
            "tau_7": tau_7, "tau_2": tau_2, "tau_4": tau_4,
            "hi_n": hi, "hi_ctx": hi_hi,
            "m5": m5, "base": base, "lift": lift, "r": pearson(xs, ys),
            "m5_v": m5_v, "base_v": base_v, "lift_v": lift_v, "r_v": pearson(xs_v, ys_v)}


def main():
    fork_day, fork_self_t = _fork_info()
    n_inherit = _inherit_prefix()
    print("P6 语料扩容离线分析 —— 母本 fork 日龄 %s，继承前缀 %d 条已剔除"
          % (fork_day, n_inherit))

    res = {"fork_day": fork_day, "n_inherit": n_inherit, "arms": {}}

    for arm in ARMS:
        last_day, win_days = _window(arm, fork_day)
        m1 = m1_selfmodel(arm, fork_self_t)
        m23 = m2_m3(arm, n_inherit)
        m4 = m4_goals(arm)
        m5 = m5_binding(arm, n_inherit)
        rate = None
        if m23 and win_days and win_days > 0:
            rate = m23["n_retr"] / win_days
        res["arms"][arm] = {
            "last_day": last_day, "window_days": win_days,
            "M1": m1, "M2": {"rate_per_day": rate, "n_retr": m23 and m23["n_retr"]},
            "M3": {"n_uniq": m23 and m23["n_uniq"],
                   "n_heard_types": m23 and m23["n_heard_types"],
                   "n_heard_events": m23 and m23["n_heard_events"]},
            "M4": m4, "M5": m5,
        }

    # ---------- 打印 ----------
    print()
    row = ("%-9s %5s %6s | %6s %7s %7s | %7s %7s | %5s | %8s %6s %6s"
           % ("arm", "last", "win", "rate/d", "n_retr", "uniq", "heardT", "heardN", "goals", "M5", "base", "lift"))
    print(row)
    print("-" * len(row))
    for arm in ARMS:
        a = res["arms"][arm]
        m2, m3, m4, m5 = a["M2"], a["M3"], a["M4"], a["M5"]
        def f(v, fmt="%s", na="n/a"):
            return na if v is None else (fmt % v)
        print("%-9s %5s %6s | %6s %7s %7s | %7s %7s | %5s | %8s %6s %6s"
              % (arm, f(a["last_day"], "%d"), f(a["window_days"], "%d"),
                 f(m2["rate_per_day"], "%.1f"), f(m2["n_retr"], "%d"),
                 f(m3["n_uniq"], "%d"), f(m3["n_heard_types"], "%d"),
                 f(m3["n_heard_events"], "%d"), f(m4["n_goals_langstate"], "%d"),
                 f(m5["m5"], "%.3f"), f(m5["base"], "%.3f"), f(m5["lift"], "%.2f")))

    print()
    print("【M1 自我模型轨迹】")
    for arm in ARMS:
        m1 = res["arms"][arm]["M1"]
        print("  %-9s 末版本 v%s | 曾达 v3 日龄 %.2f | fork 后新增 %d 版 %s"
              % (arm, m1["final_version"], m1["v3_day"], m1["n_postfork_versions"],
                 m1["postfork_versions"]))

    print()
    print("【M5 语境绑定】高紧张(s4≥P75)检索中『听到时高惊奇』占比 / 基线 / lift；r=听到态与检索s4相关")
    print("  主通道 surprise: 听到时 s7≥P75（prereg 字面）；副通道 valence: 听到时 s2≥P75（对照 language.py）")
    for arm in ARMS:
        m5 = res["arms"][arm]["M5"]
        print("  %-9s [惊奇] M5=%s base=%s lift=%s r=%s (n_hi=%s)"
              % (arm, _fmt(m5["m5"]), _fmt(m5["base"]), _fmt(m5["lift"], "%.2f"),
                 _fmt(m5["r"], "%.2f"), m5["hi_n"]))
        print("  %-9s [效价] M5=%s base=%s lift=%s r=%s"
              % ("", _fmt(m5["m5_v"]), _fmt(m5["base_v"]), _fmt(m5["lift_v"], "%.2f"),
                 _fmt(m5["r_v"], "%.2f")))

    # ---------- 判据 ----------
    print()
    print("=" * 60)
    rb = res["arms"][BASE]["M2"]["rate_per_day"]
    rt = res["arms"][TREAT]["M2"]["rate_per_day"]
    ratio = (rt / rb) if (rb and rt) else None
    passed = None if ratio is None else (0.5 <= ratio <= 2.0)
    res["H1"] = {"rate_builtin": rb, "rate_childes": rt, "ratio": ratio, "pass": passed}
    print(("  ✓ PASS " if passed else ("  ✗ FAIL " if passed is False else "  ? n/a ")) +
          "H1_structure_holds — M2 比值 childes/builtin = %s（判据 [0.5,2.0]）"
          % _fmt(ratio))

    m5b = res["arms"][BASE]["M5"]["m5"]
    m5t = res["arms"][TREAT]["M5"]["m5"]
    h3 = None if (m5b is None or m5t is None) else (m5t >= m5b)
    res["H3"] = {"m5_builtin": m5b, "m5_childes": m5t, "pass": h3}
    print(("  ✓ PASS " if h3 else ("  ✗ FAIL " if h3 is False else "  ? n/a ")) +
          "H3_binding_strength — M5[惊奇通道] childes=%s ≥ builtin=%s" % (_fmt(m5t), _fmt(m5b)))

    m1b = res["arms"][BASE]["M1"]
    m1t = res["arms"][TREAT]["M1"]
    print("  ·      H2_growth_rate（探索性，不判 PASS/FAIL）— "
          "fork 后新增版本 builtin=%d childes=%d；首个新版日龄 builtin=%s childes=%s"
          % (m1b["n_postfork_versions"], m1t["n_postfork_versions"],
             _fmt(m1b["first_postfork_day"]), _fmt(m1t["first_postfork_day"])))

    if "--json" in sys.argv:
        out = os.path.join(LAB, "experiments", "results_P6.json")
        with open(out, "w") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        print("\n已写", out)


def _fmt(v, fmt="%.3f"):
    return "n/a" if v is None else (fmt % v)


if __name__ == "__main__":
    main()
