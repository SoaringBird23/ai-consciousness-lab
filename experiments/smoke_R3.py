"""smoke_R3.py —— R3 冒烟（离线，短窗，不改在跑的线）

两项判据（见 experiments/prereg_R3.json 的 discipline / run_harness）：
  1. off 臂逐位一致：config_R3_spont_off 与 R2 基线 config_R2_ctl_none 同 fork
     state_exp，"确定性事件通道"（inner_speech.jsonl，逐唤起事件写、非墙钟节流）
     的实验窗口追加段必须逐字节相同 → 证明"默认关 = 行为与改动前逐位一致"。
     （trajectory.jsonl 在加速模式下按墙钟节流，采样相位不齐，不能按行比。）
  2. on 臂 MC 开火：C2（n_obs>0）、C3（n_acts>0 且 n_writes>0、日志非空）、
     C1（n_composed>0）必须真的激活。注意：g 是否长出"结构"属 H3c 的结论，
     不在冒烟判据内（预注册明言"可能一直不长"）。

做法：直接跑真 main.py（--time-scale 1e9）短窗，到点 SIGTERM。用临时 state 目录，
不碰 state_exp 与在跑的线。
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(LAB, "venv", "bin", "python")
RUN_SECONDS = float(os.environ.get("SMOKE_SECONDS", "60"))
N_INHERIT = None  # inner_speech.jsonl 继承前缀长度（fork 点）


def _rm(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def _lines(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [l.rstrip("\n") for l in f if l.strip()]


def prep(state_dir, log_dir):
    _rm(state_dir)
    shutil.copytree(os.path.join(LAB, "state_exp"), state_dir)
    for f in ("pid", "e6_state.json", "rng_state.json",
              "spont.json", "spont.jsonl"):
        _rm(os.path.join(state_dir, f))
    _rm(log_dir)
    os.makedirs(log_dir, exist_ok=True)


def launch(cfg, state_dir, log_dir):
    env = dict(os.environ)
    env["STATE_DIR"] = state_dir
    env["LOG_DIR"] = log_dir
    env["CONFIG"] = os.path.join(LAB, cfg)
    out = open(os.path.join(LAB, log_dir + "_console.out"), "w")
    return subprocess.Popen([PY, "main.py", "--time-scale", "1e9"],
                            cwd=LAB, env=env, stdout=out, stderr=subprocess.STDOUT)


def stop(proc):
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


def run_pair(tag, cfgs):
    dirs, procs = {}, []
    for arm, cfg in cfgs.items():
        s = os.path.join(LAB, "_smoke_%s_%s_state" % (tag, arm))
        l = "_smoke_%s_%s_logs" % (tag, arm)
        prep(s, os.path.join(LAB, l))
        procs.append((arm, launch(cfg, s, l)))
        dirs[arm] = s
    time.sleep(RUN_SECONDS)
    for arm, p in procs:
        stop(p)
    return dirs


def window(state_dir):
    """inner_speech.jsonl 的"实验窗口"段（剔除 fork 点继承前缀）。"""
    return _lines(os.path.join(state_dir, "inner_speech.jsonl"))[N_INHERIT:]


def check_off(base, off):
    a, b = window(base), window(off)
    n = min(len(a), len(b))
    d = next((i for i in range(n) if a[i] != b[i]), n)
    ok = (d == n)
    print("  [1] off 逐位一致（inner_speech 窗口，继承 %d 条）：ctl=%d off=%d "
          "共同前缀=%d → %s"
          % (N_INHERIT, len(a), len(b), d, "PASS" if ok else "FAIL"))
    if not ok:
        print("      DIFF@%d\n       ctl=%s\n       off=%s"
              % (d, a[d][:160], b[d][:160]))
    return ok


def _spont(state_dir):
    p = os.path.join(state_dir, "spont.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def check_full(state_dir):
    sp = _spont(state_dir)
    lines = _lines(os.path.join(state_dir, "spont.jsonl"))
    if sp is None:
        print("  [2a] full：无 spont.json → FAIL")
        return False
    g = list(sp.get("g_pos", [])) + list(sp.get("g_neg", []))
    ok = (sp.get("n_obs", 0) > 0 and sp.get("n_acts", 0) > 0
          and sp.get("n_writes", 0) > 0 and len(lines) > 0)
    print("  [2a] full 开火：C2 n_obs=%d  C3 n_acts=%d n_writes=%d 日志=%d  "
          "err_ema=%.3g |g|max=%.3g → %s"
          % (sp.get("n_obs", 0), sp.get("n_acts", 0), sp.get("n_writes", 0),
             len(lines), sp.get("err_ema", 0.0),
             max((abs(x) for x in g), default=0.0), "PASS" if ok else "FAIL"))
    return ok


def check_gen(state_dir):
    p = os.path.join(state_dir, "language_state.json")
    nc = None
    if os.path.exists(p):
        with open(p) as f:
            nc = json.load(f).get("n_composed")
    ok = (nc or 0) > 0
    print("  [2b] gen 开火：C1 n_composed=%s → %s"
          % (nc, "PASS" if ok else "FAIL"))
    return ok


def main():
    global N_INHERIT
    N_INHERIT = len(_lines(os.path.join(LAB, "state_exp", "inner_speech.jsonl")))
    print("== R3 冒烟（每臂 %.0fs @ time-scale 1e9；继承前缀 %d 条）=="
          % (RUN_SECONDS, N_INHERIT))

    d = run_pair("off", {"ctl_none": "config_R2_ctl_none.json",
                         "off": "config_R3_spont_off.json"})
    ok_off = check_off(d["ctl_none"], d["off"])

    print()
    print("== on 臂开火 ==")
    d2 = run_pair("on", {"full": "config_R3_spont_full.json",
                         "gen": "config_R3_spont_gen.json"})
    ok_full = check_full(d2["full"])
    ok_gen = check_gen(d2["gen"])

    allok = ok_off and ok_full and ok_gen
    print()
    print("===== 冒烟总判：%s =====" % ("全部 PASS" if allok else "存在 FAIL"))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
