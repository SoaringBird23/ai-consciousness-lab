"""analyze_batches.py — S1 / S2 / R 三批实验的自动判定

跑法：  ./venv/bin/python analyze_batches.py            # 全部能判的就判
        ./venv/bin/python analyze_batches.py S1        # 只判某一批

判据全部来自预注册文件（prereg_S1.json / prereg_S2.json / prereg_R.json），
本脚本只做计算与呈现，不修改任何判据。
"""
import json
import os
import sys
from collections import Counter

LAB = os.path.dirname(os.path.abspath(__file__))
DAY = 86400.0


def load(p):
    try:
        with open(os.path.join(LAB, p)) as f:
            return json.load(f)
    except Exception:
        return None


def jl(p, n=None):
    fp = os.path.join(LAB, p)
    if not os.path.exists(fp):
        return []
    out = []
    with open(fp) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out[-n:] if n else out


def day_of(state):
    recs = jl(f"{state}/trajectory.jsonl", 5)
    return recs[-1].get("day") if recs else None


def first_person(frag):
    return "我" in frag


def selfmodel_summary(state):
    d = load(f"{state}/self_model.json")
    if not d:
        return None
    hist = d.get("history", [])
    fp = [h for h in hist if first_person(h.get("description", ""))]
    return {
        "version": d.get("version", 0),
        "text": d.get("description", ""),
        "n_hist": len(hist),
        "first_frag_day": round(hist[0]["updated_at"] / DAY, 1) if hist else None,
        "day_reached_v3": next((round(h["updated_at"] / DAY, 1)
                                for h in hist if h.get("version", 0) >= 3), None),
        "n_first_person_versions": len(fp),
        "first_person_texts": [h["description"] for h in fp][-2:],
    }


def retrievals(state, day_lo=None, day_hi=None):
    out = []
    for r in jl(f"{state}/inner_speech.jsonl"):
        if r.get("type") != "retrieval":
            continue
        d = int(r["t"] // DAY) + 1
        if day_lo is not None and d < day_lo:
            continue
        if day_hi is not None and d > day_hi:
            continue
        out.append(r)
    return out


# ─────────────────────────── S1 复现 ───────────────────────────
def report_S1():
    TARGET = 60
    print("=" * 66)
    print(f"S1 复现  ——  自我模型能否稳定从 null 形成（判据：{TARGET} 日内 version>=3）")
    print("=" * 66)
    seeds = [101, 102, 103]
    ok = 0
    ready = 0
    for s in seeds:
        st = f"state_repl_{s}"
        day = day_of(st)
        sm = selfmodel_summary(st)
        if sm is None:
            print(f"  种子 {s}: 无数据（day={day}）")
            continue
        passed = (sm["day_reached_v3"] is not None and sm["version"] >= 3)
        ok += 1 if passed else 0
        if day is not None and day >= TARGET:
            ready += 1
        txt = sm["text"] or "(空)"
        print(f"  种子 {s}: day={day}  v{sm['version']}  "
              f"首碎片 day={sm['first_frag_day']}  达 v3 day={sm['day_reached_v3']}  "
              f"第一人称版本数={sm['n_first_person_versions']}  → {'✅' if passed else '❌'}"
              f"\n            '{txt}'")
    if ready < len(seeds):
        print(f"\n  【未到判定日】{ready}/{len(seeds)} 条已达 day {TARGET}，暂不判。"
              f"当前已形成 {ok}/{len(seeds)}（供跟踪，非结论）")
        return
    print(f"\n  判定：{ok}/3")
    if ok == 3:
        print("  → HS1 阳性：'自我模型能从 null 稳定形成'成立（3/3）")
    elif ok == 2:
        print("  → 部分：有稳健性但非必然（2/3），如实报告比例")
    else:
        print("  → HS1 阴性：核心主张降级为个例，必须重估")


# ─────────────────────────── S2 分离 ───────────────────────────
def report_S2():
    print("=" * 66)
    print("S2 分离  ——  原修复里是'语料'还是'门控'在起作用")
    print("=" * 66)
    conds = [("D", "基线（语料+门控都修）"),
             ("NC", "只关语料"),
             ("NG", "只关门控"),
             ("BO", "两者全关（修复前）")]
    res = {}
    for k, note in conds:
        st = f"state_s2_{k}"
        day = day_of(st)
        sm = selfmodel_summary(st)
        if sm is None:
            print(f"  {k:3s} {note:22s}: 无数据（day={day}）")
            continue
        formed = sm["version"] >= 3
        res[k] = formed
        print(f"  {k:3s} {note:22s}: day={day}  v{sm['version']}  "
              f"达 v3 day={sm['day_reached_v3']}  第一人称版本={sm['n_first_person_versions']}  "
              f"→ {'形成' if formed else '未形成'}")
    print()
    days = [day_of(f"state_s2_{k}") for k, _ in conds]
    if len(res) == 4:
        if any(d is None or d < 60 for d in days):
            print(f"  【未到判定日】各条件当前 day={days}，目标 60，暂不归因")
            return
        D, NC, NG, BO = (res.get(k) for k in ("D", "NC", "NG", "BO"))
        if D and NG and not NC and not BO:
            print("  → 归因：『语料为主』——关键在能听到'我'")
        elif D and NC and not NG and not BO:
            print("  → 归因：『门控为主』——关键在'我'的念头能进模型")
        elif D and not NC and not NG and not BO:
            print("  → 归因：『两者都必需』——缺一不可")
        elif all(res.values()):
            print("  → 归因：『都不关键』——原修复的因果叙述整体作废")
        else:
            print("  → 归因：不符合四条预注册模式，如实报告并记 deviation")
    else:
        print("  （数据未齐，暂不判定）")


# ─────────────────────────── R 回流量级阶梯 ───────────────────────────
def _metrics(state, day_lo, day_hi):
    r = retrievals(state, day_lo, day_hi)
    n_days = max(1, (day_hi - day_lo + 1))
    rate = len(r) / n_days
    div = (len(set(x["text"] for x in r)) / len(r)) if r else 0.0
    goals = load(f"{state}/goals.json") or []
    return {"M1_rate": rate, "M2_div": div, "n_retr": len(r), "M4_goals": len(goals)}


def report_R():
    print("=" * 66)
    print("R 阶梯  ——  '只读工作空间'是真无反馈，还是弱通道伪影")
    print("=" * 66)
    levels = [("lo", 0.02), ("mid", 0.10), ("hi", 0.30)]
    print(f"  {'档':>4} {'回流':>6} | {'M1检索/日':>18} {'M2多样性':>16} {'M4目标':>12}")
    print("  " + "-" * 62)
    for lv, v in levels:
        row = {}
        for arm in ("abl", "ctl"):
            st = f"state_R_{lv}_{arm}"
            day = day_of(st)
            if day is None:
                row[arm] = None
                continue
            lo = max(1, day - 30)
            row[arm] = _metrics(st, lo, day)
        if row.get("abl") and row.get("ctl"):
            a, c = row["abl"], row["ctl"]
            d1 = 100 * (a["M1_rate"] - c["M1_rate"]) / c["M1_rate"] if c["M1_rate"] else 0
            d2 = 100 * (a["M2_div"] - c["M2_div"]) / c["M2_div"] if c["M2_div"] else 0
            print(f"  {lv:>4} {v:>6.2f} | {c['M1_rate']:.1f}→{a['M1_rate']:.1f} ({d1:+.1f}%) "
                  f"{c['M2_div']:.3f}→{a['M2_div']:.3f} ({d2:+.1f}%) "
                  f"{c['M4_goals']}→{a['M4_goals']}")
        else:
            got = [k for k in row if row[k]]
            print(f"  {lv:>4} {v:>6.2f} | 数据未齐（已有臂：{got or '无'}）")
    print()
    print("  判据：hi 档四指标差异仍 <10% → 真·无反馈；hi 档 >20% → 弱通道伪影，核心主张作废")


if __name__ == "__main__":
    which = (sys.argv[1] if len(sys.argv) > 1 else "ALL").upper()
    if which in ("ALL", "S1"):
        report_S1(); print()
    if which in ("ALL", "S2"):
        report_S2(); print()
    if which in ("ALL", "R"):
        report_R(); print()
