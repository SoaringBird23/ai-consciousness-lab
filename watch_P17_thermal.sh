#!/bin/bash
# watch_P17_thermal.sh — P17 无人值守热保护（沿用 P13/P14 同款机制）
#
# 加速模式（time_scale=1e9）下 main.py 不 sleep，仿真占满核；软件侧无节流，
# 本脚本是无人值守的唯一安全网：每 60s 读一次 pmset -g therm（只读，不 sudo），
# 一旦降频（CPU_Speed_Limit<95 或 CPU_Scheduler_Limit<100）即 SIGSTOP 全部仿真、
# 退避后 SIGCONT。用 SIGSTOP 而非 SIGKILL：harness 的 kill -0 对已停进程仍为真，
# 不误判退出，恢复后从原 tick 继续，数据无损。
export PATH=/bin:/usr/bin:/usr/sbin:/sbin
cd "$(dirname "$0")"
LOG=chain_P17_thermal.log
LIMIT=${P17_THERM_LIMIT:-95}
PAUSE=${P17_THERM_PAUSE:-120}
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }
sim_pids(){ pgrep -f "[m]ain.py --time-scale 1e9" 2>/dev/null; }

log "启动（阈值 CPU_Speed_Limit<${LIMIT} 或 CPU_Scheduler_Limit<100，退避 ${PAUSE}s）"
paused=0
while true; do
  if ! pgrep -f "[r]un_P17.sh" >/dev/null 2>&1; then
    if [ "$paused" -eq 1 ]; then for p in $(sim_pids); do kill -CONT "$p" 2>/dev/null; done; fi
    log "run_P17.sh 已退出，热保护结束"; exit 0
  fi
  th=$(pmset -g therm 2>/dev/null)
  data=$(printf '%s\n' "$th" | grep -E '^(CPU_Speed_Limit|CPU_Scheduler_Limit|CPU_Available_CPUs)')
  hot=0; detail="cool"
  if [ -n "$data" ]; then
    sp=$(printf '%s\n' "$data" | sed -n 's/^CPU_Speed_Limit[^0-9]*\([0-9][0-9]*\).*/\1/p' | head -1)
    sc=$(printf '%s\n' "$data" | sed -n 's/^CPU_Scheduler_Limit[^0-9]*\([0-9][0-9]*\).*/\1/p' | head -1)
    detail="speed=${sp:-n/a} sched=${sc:-n/a}"
    [ -n "$sp" ] && [ "$sp" -lt "$LIMIT" ] && hot=1
    [ -n "$sc" ] && [ "$sc" -lt 100 ] && hot=1
  fi
  if [ "$hot" -eq 1 ]; then
    n=0; for p in $(sim_pids); do kill -STOP "$p" 2>/dev/null && n=$((n+1)); done
    log "降频（$detail）→ 暂停 $n 个仿真进程，退避 ${PAUSE}s"
    paused=1; sleep "$PAUSE"
  else
    if [ "$paused" -eq 1 ]; then
      n=0; for p in $(sim_pids); do kill -CONT "$p" 2>/dev/null && n=$((n+1)); done
      log "热压解除（$detail）→ 恢复 $n 个仿真进程"; paused=0
    fi
    sleep 60
  fi
done
