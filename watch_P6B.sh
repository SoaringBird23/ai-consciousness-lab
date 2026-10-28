#!/bin/bash
# watch_P6B.sh — 守望 P6-A（run_P6.sh，两臂 TGT=315）停采后，自动启动 Step B（run_P6B.sh）。
#
# 就绪判据（须同时满足，避免在部分/损坏状态上 fork）：
#   builtin 与 childes 两臂 day >= 315，且两臂进程均已退出，且 run_P6.sh 主体已退出。
# 防重入：原子 mkdir 锁 + 检测 chain_P6B.log 是否已含启动横幅。
export PATH=/bin:/usr/bin:/usr/sbin:/sbin
cd "$(dirname "$0")"
LOG=chain_P6B_watch.log
TGT_A=315
LOCK=.watch_P6B.lock
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }

if ! mkdir "$LOCK" 2>/dev/null; then
  log "已有守望进程在运行，退出"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }
alive_pid(){ p=$(cat "$1/pid" 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }

log "守望启动：等待 P6-A 两臂达 day ${TGT_A} 且停采…"
while true; do
  if grep -q "P6-B 双向重探采集启动" chain_P6B.log 2>/dev/null; then
    log "检测到 run_P6B.sh 已启动，守望退出"
    exit 0
  fi
  db=$(day_of state_P6_builtin); [ -z "$db" ] && db=0
  dc=$(day_of state_P6_childes); [ -z "$dc" ] && dc=0
  ab=0; alive_pid state_P6_builtin && ab=1
  ac=0; alive_pid state_P6_childes && ac=1
  if [ "$db" -ge "$TGT_A" ] && [ "$dc" -ge "$TGT_A" ] && [ "$ab" -eq 0 ] && [ "$ac" -eq 0 ]; then
    if pgrep -f "[r]un_P6.sh" >/dev/null 2>&1; then
      log "两臂已停采但 run_P6.sh 仍在，稍候（builtin=${db} childes=${dc}）"
    else
      log "P6-A 停采确认（builtin=${db} childes=${dc}），启动 run_P6B.sh"
      nohup ./run_P6B.sh >> chain_P6B_nohup.out 2>&1 &
      log "run_P6B.sh 已启动（PID $!）"
      exit 0
    fi
  else
    log "等待中：builtin=${db}/${TGT_A}(alive=${ab}) childes=${dc}/${TGT_A}(alive=${ac})"
  fi
  sleep 90
done
