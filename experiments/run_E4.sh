#!/bin/bash
# E4 发声与能动归因：等 E3 结束 → p1 习得(30日, contingent+发声) → p2 消退(25日, random+发声)
cd "$(dirname "$0")/.."
mkdir -p experiments/e4
LOG=experiments/e4/phase_log.txt
: > "$LOG"
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

simday() { tail -1 logs_accel/main.log | grep -oE "day [0-9]+ h[0-9.]+" | awk '{print $2 + substr($3,2)/24}'; }

snap() {  # $1=快照名
  ./venv/bin/python - "$1" <<'PYEOF'
import json, sys, re
name = sys.argv[1]
ls = json.load(open("state_accel/language_state.json"))
sm = json.load(open("state_accel/self_model.json"))
pr = json.load(open("state_accel/predictor.json"))
vc = json.load(open("state_accel/vocal.json"))
line = open("logs_accel/main.log").readlines()[-1]
m = re.search(r"day (\d+) h([\d.]+)", line)
day = int(m.group(1)) + float(m.group(2)) / 24.0
json.dump({"sim_day": day, "n_heard": ls["n_heard"], "n_retrieval": ls["n_retrieval"],
           "n_vocal": vc.get("n_vocal", 0), "contingency": pr.get("contingency"),
           "efficacy": pr.get("efficacy"),
           "self_model_version": sm["version"], "self_model_desc": sm["description"]},
          open(f"experiments/e4/{name}.json", "w"), ensure_ascii=False, indent=2)
PYEOF
}

wait_until() {
  local deadline=$(( $(date +%s) + $2 ))
  while :; do
    local cur; cur=$(simday)
    if awk -v c="$cur" -v t="$1" 'BEGIN{exit !(c>=t)}'; then return 0; fi
    if [ "$(date +%s)" -ge "$deadline" ]; then say "!! TIMEOUT at $(simday) (target $1)"; return 1; fi
    sleep 30
  done
}

restart_accel() {
  pkill -f "main.py --time-scale"
  for i in $(seq 1 15); do pgrep -f "main.py --time-scale" >/dev/null || break; sleep 1; done
  nohup caffeinate -i ./run_accel.sh >/dev/null 2>&1 &
  sleep 5
}

set_config() {  # $1=caregiver mode $2=vocal enabled
  ./venv/bin/python - "$1" "$2" <<'PYEOF'
import json, sys
p = "config_accel.json"
cfg = json.load(open(p))
cfg.setdefault("caregiver", {})["mode"] = sys.argv[1]
cfg["caregiver"]["vocal_response_prob"] = 0.7
cfg["vocal"] = {"enabled": sys.argv[2] == "true", "arousal_gate": 0.55,
                "base_prob": 0.25, "energy_cost": 1.0}
json.dump(cfg, open(p, "w"), ensure_ascii=False, indent=2)
PYEOF
}

# ---- 等 E3 结束 ----
say "等待 E3 完成（phase_log 出现 DONE）..."
while ! grep -q "DONE" experiments/e3/phase_log.txt 2>/dev/null; do sleep 60; done
say "E3 已完成，E4 启动。"

# ---- p1：习得（contingent 照护 + 发声开） ----
set_config contingent true
restart_accel
sleep 20
D0=$(simday)
snap p1_start
say "==== p1 习得开始 | simday $D0 | vocal=on caregiver=contingent | 计划 30 仿真日 ===="
wait_until "$(awk -v d="$D0" 'BEGIN{print d+30}')" 2400

# ---- p2：消退（random 照护 + 发声开） ----
set_config random true
restart_accel
sleep 20
D1=$(simday)
snap p2_start
say "==== p2 消退开始 | simday $D1 | vocal=on caregiver=random | 计划 25 仿真日 ===="
wait_until "$(awk -v d="$D1" 'BEGIN{print d+25}')" 2400

# ---- 结束：保留发声能力，照护者回到 random 基线世界 ----
snap e4_end
set_config random true
restart_accel
say "==== E4 结束 | simday $(simday) | vocal 保留，caregiver=random ===="

# ---- 快速汇总 ----
./venv/bin/python - <<'PYEOF' | tee -a experiments/e4/phase_log.txt
import json
p1 = json.load(open("experiments/e4/p1_start.json"))
p2 = json.load(open("experiments/e4/p2_start.json"))
e = json.load(open("experiments/e4/e4_end.json"))
print("p1 习得(%d日): 发声 +%d (%.1f/日) | C: %s→%s | self_model v%d→v%d" % (
    p2["sim_day"]-p1["sim_day"], p2["n_vocal"]-p1["n_vocal"],
    (p2["n_vocal"]-p1["n_vocal"])/(p2["sim_day"]-p1["sim_day"]),
    p1.get("contingency"), p2.get("contingency"),
    p1["self_model_version"], p2["self_model_version"]))
print("p2 消退(%d日): 发声 +%d | C: %s | efficacy: %s | self_model v%d→v%d" % (
    e["sim_day"]-p2["sim_day"], e["n_vocal"]-p2["n_vocal"],
    e.get("contingency"), e.get("efficacy"),
    p2["self_model_version"], e["self_model_version"]))
PYEOF
say "DONE — 等待 analyze_E4.py 判定"
