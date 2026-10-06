#!/bin/bash
# E4 重跑（修复后）：p1 习得 30 日(contingent+发声) → p2 消退 25 日(random+发声) → 复原
cd "$(dirname "$0")/.."
LOG=experiments/e4/phase_log.txt
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

simday() { tail -1 logs_accel/main.log | grep -oE "day [0-9]+ h[0-9.]+" | awk '{print $2 + substr($3,2)/24}'; }

snap() {
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
           "n_echo": ls["n_echo"], "n_vocal": vc.get("n_vocal", 0),
           "contingency": pr.get("contingency"), "efficacy": pr.get("efficacy"),
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

set_config() {  # $1=caregiver mode
  ./venv/bin/python - "$1" <<'PYEOF'
import json, sys
p = "config_accel.json"
cfg = json.load(open(p))
cfg.setdefault("caregiver", {})["mode"] = sys.argv[1]
cfg["caregiver"]["vocal_response_prob"] = 0.7
cfg["vocal"] = {"enabled": True, "arousal_gate": 0.55,
                "base_prob": 0.25, "energy_cost": 1.0}
json.dump(cfg, open(p, "w"), ensure_ascii=False, indent=2)
PYEOF
}

say "==== E4 重跑启动（修复：每窗口一次应答；清洗见 deviation_1.json） ===="

set_config contingent
restart_accel
sleep 20
D0=$(simday)
snap p1_start
say "==== p1 习得开始 | simday $D0 | vocal=on caregiver=contingent | 计划 30 仿真日 ===="
wait_until "$(awk -v d="$D0" 'BEGIN{print d+30}')" 2400

set_config random
restart_accel
sleep 20
D1=$(simday)
snap p2_start
say "==== p2 消退开始 | simday $D1 | vocal=on caregiver=random | 计划 25 仿真日 ===="
wait_until "$(awk -v d="$D1" 'BEGIN{print d+25}')" 2400

snap e4_end
set_config random
restart_accel
say "==== E4 结束 | simday $(simday) | vocal 保留，caregiver=random ===="

./venv/bin/python - <<'PYEOF' | tee -a experiments/e4/phase_log.txt
import json
p1 = json.load(open("experiments/e4/p1_start.json"))
p2 = json.load(open("experiments/e4/p2_start.json"))
e = json.load(open("experiments/e4/e4_end.json"))
print("p1 习得(%.1f日): 发声 +%d (%.1f/日) | C: %s→%s | eff: %s | self_ratio见attribution | sm v%d→v%d" % (
    p2["sim_day"]-p1["sim_day"], p2["n_vocal"]-p1["n_vocal"],
    (p2["n_vocal"]-p1["n_vocal"])/(p2["sim_day"]-p1["sim_day"]),
    p1.get("contingency"), p2.get("contingency"), p2.get("efficacy"),
    p1["self_model_version"], p2["self_model_version"]))
print("p2 消退(%.1f日): 发声 +%d | C: %s | eff: %s | sm v%d→v%d" % (
    e["sim_day"]-p2["sim_day"], e["n_vocal"]-p2["n_vocal"],
    e.get("contingency"), e.get("efficacy"),
    p2["self_model_version"], e["self_model_version"]))
PYEOF
say "DONE"
