#!/bin/bash
# watch_P9_launch.sh — 等 P8 三臂全部达 day 345 且 harness 退出后，自动启动 P9 采集。
#
# 目的：避免 P8 与 P9 两批实验并发抢 CPU（M4 Air 无风扇，双满载即过热）。
# 就绪判据：P8 三臂均 >= 345，且无 main.py --time-scale 1e9 进程，且 run_P8.sh 已退出。
export PATH=/bin:/usr/bin:/usr/sbin:/sbin
cd "$(dirname "$0")"
LOG=chain_P9.log
TGT=345
LOCK=.watch_P9_launch.lock
ARMS=(k20_shuf k40_full k40_shuf)
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }

if ! mkdir "$LOCK" 2>/dev/null; then log "已有接力守望在运行，退出"; exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

log "接力守望启动：等待 P8 三臂完成（避免并发）…"
while true; do
  if grep -q "P9 联想启动（priming）采集启动" "$LOG" 2>/dev/null; then
    log "检测到 P9 已启动，守望退出"; exit 0
  fi
  allok=1
  for a in "${ARMS[@]}"; do
    dd=$(day_of "state_P8_$a"); [ -z "$dd" ] && dd=0
    if [ "$dd" -lt "$TGT" ]; then allok=0; log "等待中：P8:$a day=${dd}/${TGT}"; break; fi
  done
  if [ "$allok" -eq 1 ]; then
    if pgrep -f "[m]ain.py --time-scale 1e9" >/dev/null 2>&1; then
      log "P8 三臂已达 day ${TGT} 但仍有运行中进程，稍候"
    elif pgrep -f "[r]un_P8.sh" >/dev/null 2>&1; then
      log "P8 三臂已达 day ${TGT} 但 run_P8.sh 仍在，稍候"
    else
      log "P8 完成，启动 P9 联想启动采集（串行，MAX=1）"
      nohup ./run_P9.sh >> chain_P9_nohup.out 2>&1 &
      log "run_P9.sh 已启动（PID $!）"
      exit 0
    fi
  fi
  sleep 90
done
