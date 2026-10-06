#!/bin/bash
# E1 语言剥夺 + E2 事件风暴 干预实验驱动（按仿真日推进，实测速率 ≈2.24 仿真日/墙钟小时）
# 阶段：E1剥夺(10仿真日) → E1恢复(5) → E2风暴(5) → E2余波(3) → 全部复原
# 相位边界写入 experiments/phase_log.txt（含仿真日/小时），供事后分析
cd "$(dirname "$0")/.."
LOG=experiments/phase_log.txt
: > "$LOG"

say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# 当前仿真日（小数）——取自加速线最新心跳
simday() { tail -1 logs_accel/main.log | grep -oE "day [0-9]+ h[0-9.]+" | awk '{print $2 + substr($3,2)/24}'; }

# 等待仿真日达到目标：$1=目标仿真日 $2=墙钟超时秒
wait_until() {
  local deadline=$(( $(date +%s) + $2 ))
  while :; do
    local cur; cur=$(simday)
    if awk -v c="$cur" -v t="$1" 'BEGIN{exit !(c>=t)}'; then return 0; fi
    if [ "$(date +%s)" -ge "$deadline" ]; then say "!! TIMEOUT at simday $(simday) (target $1)"; return 1; fi
    sleep 30
  done
}

# 重启加速线（SIGTERM→KeyboardInterrupt→finally 保存；首次旧进程无 handler，损失≤2秒）
restart_accel() {
  pkill -f "main.py --time-scale"
  for i in $(seq 1 15); do pgrep -f "main.py --time-scale" >/dev/null || break; sleep 1; done
  nohup caffeinate -i ./run_accel.sh >/dev/null 2>&1 &
  sleep 5
  grep "恢复运行状态" logs_accel/main.log | tail -1 | sed 's/^/  /' | tee -a "$LOG"
  say "  相位起点: simday $(simday)"
}

# 改配置（参数为若干赋值语句）
set_cfg() {
  ./venv/bin/python - "$@" <<'PYEOF'
import json, sys
p = "config_accel.json"
cfg = json.load(open(p))
for stmt in sys.argv[1:]:
    exec(stmt, {}, {"cfg": cfg})
json.dump(cfg, open(p, "w"), ensure_ascii=False, indent=2)
PYEOF
}

# ============ E1 语言剥夺：caregiver 全静默 ============
D0=$(simday)
say "==== E1 deprivation 开始 | 起点仿真日 $D0 | 计划 10 仿真日 ===="
set_cfg "cfg['caregiver']={'speech_per_hour_quiet':0.0,'speech_prob_with_event':0.0,'self_directed_prob':0.0}"
restart_accel
wait_until "$(awk -v d="$D0" 'BEGIN{print d+10}')" 660
# 抑制期结束前快照（防止数据文件被后续意外覆盖）
cp state_accel/inner_speech.jsonl experiments/inner_speech_after_E1.jsonl 2>/dev/null

# ============ E1 恢复期：caregiver 复原 ============
D1=$(simday)
say "==== E1 recovery 开始 | 起点 $D1 | 计划 5 仿真日 ===="
set_cfg "cfg['caregiver']={'speech_per_hour_quiet':4.0,'speech_prob_with_event':0.6,'self_directed_prob':0.08}"
restart_accel
wait_until "$(awk -v d="$D1" 'BEGIN{print d+5}')" 360

# ============ E2 事件风暴：事件率 3→30/小时（活跃时段） ============
D2=$(simday)
say "==== E2 storm 开始 | 起点 $D2 | 计划 5 仿真日 ===="
set_cfg "cfg['events']['simulated_user']['rate_per_hour_active']=30.0"
restart_accel
wait_until "$(awk -v d="$D2" 'BEGIN{print d+5}')" 360
cp state_accel/inner_speech.jsonl experiments/inner_speech_after_E2storm.jsonl 2>/dev/null

# ============ E2 余波：事件率复原 ============
D3=$(simday)
say "==== E2 aftermath 开始 | 起点 $D3 | 计划 3 仿真日 ===="
set_cfg "cfg['events']['simulated_user']['rate_per_hour_active']=3.0"
restart_accel
wait_until "$(awk -v d="$D3" 'BEGIN{print d+3}')" 240

# ============ 结束：校验参数全部复原 ============
say "==== 实验结束，校验配置 ===="
./venv/bin/python -c "
import json; c=json.load(open('config_accel.json'))
print('caregiver:', c.get('caregiver')); print('rate_active:', c['events']['simulated_user']['rate_per_hour_active'])" | tee -a "$LOG"
say "DONE — 加速线恢复正常运行，等待分析"
