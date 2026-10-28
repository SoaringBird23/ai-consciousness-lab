#!/bin/bash
# watch_P14b_analyze.sh — 等 P14b 三臂全部达 day 315 且 harness 退出后，自动跑 analyze_P14b.py 落盘。
#
# 就绪判据：三臂 trajectory day >= 315，且无 main.py --time-scale 1e9 进程，且 run_P14b.sh 已退出。
# 产出：experiments/results_P14b.json + 控制台表格到 chain_P14b_analyze.log
# 判据见 experiments/prereg_P14b_content_sensitive_caregiver.json（H14a–H14f，事前冻结）。
export PATH=/bin:/usr/bin:/usr/sbin:/sbin
cd "$(dirname "$0")"
LOG=chain_P14b_analyze.log
TGT=${P14B_TGT:-315}
LOCK=.watch_P14b_analyze.lock
ARMS=(off full shuf)
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }

if ! mkdir "$LOCK" 2>/dev/null; then log "已有分析守望在运行，退出"; exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

log "分析守望启动：等待 P14b 三臂达 day ${TGT} 且 harness 退出…"
while true; do
  if [ -f experiments/results_P14b.json ]; then log "results_P14b.json 已存在，守望退出"; exit 0; fi
  allok=1
  for a in "${ARMS[@]}"; do
    dd=$(day_of "state_P14b_$a"); [ -z "$dd" ] && dd=0
    if [ "$dd" -lt "$TGT" ]; then allok=0; log "等待中：$a day=${dd}/${TGT}"; break; fi
  done
  if [ "$allok" -eq 1 ]; then
    if pgrep -f "[m]ain.py --time-scale 1e9" >/dev/null 2>&1; then
      log "三臂已达 day ${TGT} 但仍有运行中进程，稍候"
    elif pgrep -f "[r]un_P14b.sh" >/dev/null 2>&1; then
      log "三臂已达 day ${TGT} 但 run_P14b.sh 仍在，稍候"
    else
      log "就绪：三臂到齐且 harness 退出，运行 analyze_P14b.py（H14a–H14f）"
      ./venv/bin/python experiments/analyze_P14b.py >> "$LOG" 2>&1
      log "分析器完成（退出码 $?）；结果见 experiments/results_P14b.json"
      exit 0
    fi
  fi
  sleep 60
done
