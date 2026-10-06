#!/bin/bash
# E3 应答式照护者：冲刷期(random, 20仿真日, 同期对照) → contingent(50仿真日) → 复原 random
cd "$(dirname "$0")/.."
mkdir -p experiments/e3
LOG=experiments/e3/phase_log.txt
: > "$LOG"
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

simday() { tail -1 logs_accel/main.log | grep -oE "day [0-9]+ h[0-9.]+" | awk '{print $2 + substr($3,2)/24}'; }

snap() {  # $1=快照名
  ./venv/bin/python - "$1" <<'PYEOF'
import json, sys, re
name = sys.argv[1]
ls = json.load(open("state_accel/language_state.json"))
sm = json.load(open("state_accel/self_model.json"))
line = open("logs_accel/main.log").readlines()[-1]
m = re.search(r"day (\d+) h([\d.]+)", line)
day = int(m.group(1)) + float(m.group(2)) / 24.0
json.dump({"sim_day": day, "n_heard": ls["n_heard"], "n_retrieval": ls["n_retrieval"],
           "self_model_version": sm["version"], "self_model_desc": sm["description"]},
          open(f"experiments/e3/{name}.json", "w"), ensure_ascii=False, indent=2)
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
  grep "恢复运行状态" logs_accel/main.log | tail -1 | sed 's/^/  /' | tee -a "$LOG"
}

set_mode() {  # $1=random|contingent
  ./venv/bin/python - "$1" <<'PYEOF'
import json, sys
p = "config_accel.json"
cfg = json.load(open(p))
cfg.setdefault("caregiver", {})["mode"] = sys.argv[1]
json.dump(cfg, open(p, "w"), ensure_ascii=False, indent=2)
PYEOF
}

# ============ 冲刷期（random，同期对照） ============
D0=$(simday)
snap washout_start
say "==== washout 开始 | simday $D0 | random 模式 | 计划 20 仿真日 ===="
wait_until "$(awk -v d="$D0" 'BEGIN{print d+20}')" 1800

# ============ E3：contingent 模式 ============
D1=$(simday)
snap washout_end
say "==== E3 contingent 开始 | simday $D1 | 应答式照护 | 计划 50 仿真日 ===="
set_mode contingent
restart_accel
say "  模式已切换: $(./venv/bin/python -c "import json;print(json.load(open('config_accel.json'))['caregiver']['mode'])")"
wait_until "$(awk -v d="$D1" 'BEGIN{print d+50}')" 4200

# ============ 结束：复原 + 快照 ============
D2=$(simday)
snap e3_end
set_mode random
restart_accel
say "==== E3 结束 | simday $D2 | 已复原 random 模式 ===="
./venv/bin/python -c "
import json
w0=json.load(open('experiments/e3/washout_start.json')); w1=json.load(open('experiments/e3/washout_end.json')); e=json.load(open('experiments/e3/e3_end.json'))
print('washout: %d 日 | heard +%d (%.1f/日) | 检索 +%d | 版本 %d→%d' % (w1['sim_day']-w0['sim_day'], w1['n_heard']-w0['n_heard'], (w1['n_heard']-w0['n_heard'])/(w1['sim_day']-w0['sim_day']), w1['n_retrieval']-w0['n_retrieval'], w0['self_model_version'], w1['self_model_version']))
print('E3:      %d 日 | heard +%d (%.1f/日) | 检索 +%d | 版本 %d→%d' % (e['sim_day']-w1['sim_day'], e['n_heard']-w1['n_heard'], (e['n_heard']-w1['n_heard'])/(e['sim_day']-w1['sim_day']), e['n_retrieval']-w1['n_retrieval'], w1['self_model_version'], e['self_model_version']))
" | tee -a "$LOG"
say "DONE — 等待 analyze_E3.py 判定"
