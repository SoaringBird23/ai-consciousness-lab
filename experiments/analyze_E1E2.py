#!/usr/bin/env python3
# E1/E2 干预实验结果分析——严格按预注册判据判定（experiments/prereg_E1E2.json）
# 用法: ./venv/bin/python experiments/analyze_E1E2.py
import json, re, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

DAY = 86400.0

# ---------- 解析相位边界（display day → sim_time: t=(d-1)*86400） ----------
log = open("experiments/phase_log.txt").read()
def parse_start(marker):
    m = re.search(re.escape(marker) + r".*?起点仿真日 ([0-9.]+)|" + re.escape(marker) + r".*?起点 ([0-9.]+)", log)
    return float(m.group(1) or m.group(2)) if m else None
# 兼容两种写法
def phase_day(name):
    m = re.search(name + r".*?(?:起点仿真日|起点) ([0-9.]+)", log)
    return float(m.group(1)) if m else None

D0 = phase_day("E1 deprivation")   # 剥夺开始
D1 = phase_day("E1 recovery")      # 恢复开始
D2 = phase_day("E2 storm")         # 风暴开始
D3 = phase_day("E2 aftermath")     # 余波开始
done = "DONE" in log
if None in (D0, D1, D2, D3) or not done:
    print("相位不完整: D0=%s D1=%s D2=%s D3=%s done=%s" % (D0, D1, D2, D3, done)); sys.exit(1)

def w(d):  # display day → sim_time
    return (d - 1.0) * DAY

E1   = (w(D0), w(D0 + 10))   # 剥夺 10 仿真日
REC  = (w(D1), w(D1 + 5))    # 恢复 5
STO  = (w(D2), w(D2 + 5))    # 风暴 5
AFT  = (w(D3), w(D3 + 3))    # 余波 3

# ---------- 读数据 ----------
speech = [json.loads(l) for l in open("state_accel/inner_speech.jsonl")]
speech_E1  = [r for r in speech if E1[0] <= r["t"] < E1[1]]
speech_REC = [r for r in speech if REC[0] <= r["t"] < REC[1]]
speech_STO = [r for r in speech if STO[0] <= r["t"] < STO[1]]
echo_E1   = [r for r in speech_E1  if r["type"] == "echo"]
ret_E1    = [r for r in speech_E1  if r["type"] == "retrieval"]
ret_REC   = [r for r in speech_REC if r["type"] == "retrieval"]
echo_REC  = [r for r in speech_REC if r["type"] == "echo"]
ret_STO   = [r for r in speech_STO if r["type"] == "retrieval"]

# 事件语境片段集合（与 language.py CORPUS_EVENT 一致）
sys.path.insert(0, ".")
import language
EVSET = set(language.CORPUS_EVENT)

R = {}   # 结果
def verdict(name, ok, detail):
    R[name] = {"pass": bool(ok), "detail": detail}
    print(("  ✓ PASS " if ok else "  ✗ FAIL ") + name + " — " + detail)

print("=" * 62)
print("E1 语言剥夺（%s → %s 仿真日）" % (D0, D0 + 10))
print("=" * 62)

# H1a echo≈0
verdict("H1a echo≈0", len(echo_E1) <= 2,
        "E1 期 echo 总数 = %d（判据 ≤2）" % len(echo_E1))

# H1b 内言语持续但衰减：最后 3 仿真日速率 ∈ [2, 17.3]/日
last3 = [r for r in ret_E1 if r["t"] >= E1[1] - 3 * DAY]
rate_last3 = len(last3) / 3.0
rate_all = len(ret_E1) / 10.0
verdict("H1b 内化（retrieval 持续且衰减）",
        2 <= rate_last3 <= 17.3,
        "E1 全程 %.1f/日 → 最后3日 %.1f/日（判据 2–17.3，基线 28.8）" % (rate_all, rate_last3))

# H1c '真乖' 占比 ≥15%
zg = sum(1 for r in ret_E1 if r["text"] == "真乖")
frac = zg / len(ret_E1) if ret_E1 else 0.0
verdict("H1c 内化片段不坍塌", frac >= 0.15,
        "'真乖' 占 E1 检索 %d/%d = %.1f%%（判据 ≥15%%，基线 19.5%%）" % (zg, len(ret_E1), frac * 100))

# H1d 自我模型冻结
hist = json.load(open("state_accel/self_model_history.json"))
versions_during_E1 = []
for h in (hist if isinstance(hist, list) else hist.get("history", [])):
    t = h.get("t") or h.get("sim_time")
    if t and E1[0] <= t < E1[1]:
        versions_during_E1.append(h.get("version"))
verdict("H1d 自我模型冻结", len(versions_during_E1) == 0,
        "E1 期版本更新数 = %d（当前 %s）" % (len(versions_during_E1),
        open("state_accel/self_model.json").read()[:80]))

# H1e 恢复反弹
rate_REC = len(ret_REC) / 5.0
verdict("H1e 恢复反弹", rate_REC >= 20.2 and len(echo_REC) >= 1,
        "恢复期 retrieval %.1f/日（判据 ≥20.2），echo %d 次（判据 ≥1）" % (rate_REC, len(echo_REC)))

print()
print("=" * 62)
print("E2 事件风暴（%s → %s 仿真日，事件率 3→30/小时）" % (D2, D2 + 5))
print("=" * 62)

# H2a 惊奇先升后降：解析心跳日志
hb = []
for line in open("logs_accel/main.log"):
    m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*day (\d+) h([\d.]+).*surprise=([\d.]+|n/a)", line)
    if m:
        try: s = float(m.group(4))
        except ValueError: continue
        hb.append((float(m.group(2)) + float(m.group(3)) / 24.0, s))
sto_hb = [x for x in hb if D2 <= x[0] < D2 + 5]
pre_s = 3.94
if sto_hb:
    early = [s for d, s in sto_hb if d < D2 + 1.5]
    peak = max(s for d, s in sto_hb)
    final = [s for d, s in sto_hb if d >= D2 + 4.5]
    final_s = sum(final) / len(final) if final else None
    rise = max(early) - pre_s if early else 0
    fall = (peak - final_s) / peak if final_s else 0
    verdict("H2a 惊奇适应", rise >= 0.4 and fall >= 0.30,
            "峰值 %.2f bit（升 %.2f），风暴末 %.2f（回落 %.0f%%）；判据 升≥0.4 且 回落≥30%%" %
            (peak, rise, final_s, fall * 100))
else:
    verdict("H2a 惊奇适应", False, "风暴期无 surprise 心跳数据")

# H2b 事件语境片段占比 ≥33%
ev = sum(1 for r in ret_STO if r["text"] in EVSET)
frac_sto = ev / len(ret_STO) if ret_STO else 0.0
verdict("H2b 语境绑定因果", frac_sto >= 0.33,
        "风暴期事件语境片段占检索 %d/%d = %.1f%%（判据 ≥33%%，基线 16.5%%）" % (ev, len(ret_STO), frac_sto * 100))

# H2c 状态转移：风暴期 s4>0.62 且 s8<0.13
traj = [json.loads(l) for l in open("state_accel/trajectory.jsonl")]
sto_tr = [x for x in traj if STO[0] <= x["sim_time"] < STO[1]]
if sto_tr:
    s4m = sum(x["s4"] for x in sto_tr) / len(sto_tr)
    s8m = sum(x["s8"] for x in sto_tr) / len(sto_tr)
    verdict("H2c 状态动力学转移", s4m > 0.62 and s8m < 0.13,
            "风暴期 s4=%.3f（判据 >0.62，基线 0.559），s8=%.3f（判据 <0.13，基线 0.176）" % (s4m, s8m))
else:
    verdict("H2c 状态动力学转移", False, "风暴期无轨迹数据")

# H2d 探索性：新目标
goals = json.load(open("state_accel/goals.json"))
verdict("H2d 新目标（探索性，不判 PASS/FAIL）", None,
        "当前目标: %s" % json.dumps([g.get("goal", g) if isinstance(g, dict) else g for g in goals], ensure_ascii=False))

# ---------- 汇总 ----------
n_pass = sum(1 for v in R.values() if v["pass"] is True)
n_fail = sum(1 for v in R.values() if v["pass"] is False)
summary = {
    "analyzed_at": open("experiments/phase_log.txt").read().strip().splitlines()[-1],
    "phases": {"E1": [D0, D0 + 10], "recovery": [D1, D1 + 5], "storm": [D2, D2 + 5], "aftermath": [D3, D3 + 3]},
    "results": R,
    "pass": n_pass, "fail": n_fail,
}
json.dump(summary, open("experiments/results_E1E2.json", "w"), ensure_ascii=False, indent=2)
print()
print("=" * 62)
print("汇总: %d 通过 / %d 失败（结果已存 experiments/results_E1E2.json）" % (n_pass, n_fail))
