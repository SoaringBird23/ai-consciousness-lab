#!/bin/bash
# watch_P12_thermal.sh — P12 无人值守热保护
#
# 为什么需要它：加速模式（time_scale=1e9）下 main.py 的 wall_sleep=5e-11 < 0.001 →
# 不 sleep，仿真必然占满 1 核；且 en.low_power 的 low_power_factor 在该模式下同样失效。
# 即软件侧没有任何节流，唯一的无人值守安全网在本脚本。
#
# 行为：每 60 s 读一次 pmset -g therm（只读，不 sudo）。
#   一旦出现真实降频字段（CPU_Speed_Limit < 95 或 CPU_Scheduler_Limit < 100），
#   就 SIGSTOP 所有 --time-scale 1e9 的仿真进程，退避 120 s 后 SIGCONT。
#   机器凉时「没有任何数字字段」（只有 No ... has been recorded 的 Note），本脚本不做任何事。
# 停止进程用 SIGSTOP 而非 SIGKILL：harness 的 kill -0 对已停进程仍为真，不会误判为退出，
# 仿真恢复后从原 tick 继续，数据无损（已实测：STOP 15s 日志冻结 / CONT 20s 从 h1.49→h7.38）。
export PATH=/bin:/usr/bin:/usr/sbin:/sbin
cd "$(dirname "$0")"
LOG=chain_P12_thermal.log
LIMIT=${P12_THERM_LIMIT:-95}
PAUSE=${P12_THERM_PAUSE:-120}
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }
sim_pids(){ pgrep -f "[m]ain.py --time-scale 1e9" 2>/dev/null; }

log "启动（阈值 CPU_Speed_Limit<${LIMIT} 或 CPU_Scheduler_Limit<100，退避 ${PAUSE}s）"
paused=0
while true; do
  if ! pgrep -f "[r]un_P12.sh" >/dev/null 2>&1; then
    if [ "$paused" -eq 1 ]; then for p in $(sim_pids); do kill -CONT "$p" 2>/dev/null; done; fi
    log "run_P12.sh 已退出，热保护结束"; exit 0
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
