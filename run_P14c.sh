#!/bin/bash
# run_P14c.sh — P14c 内容敏感听者（Content-Sensitive Listener）三臂采集
#
# 见 experiments/prereg_P14c.json。
#
# 与 P14 唯一差异：caregiver.content_response（应答概率按发声的型 r(f)，
# HIGH=0.9/LOW=0.1，映射冻结于 experiments/p14b_content_map.json）。
# 其余（fork 自 state_exp 的 day255、60 日窗口、response_model 三臂）与 P14 逐位相同。
#
# 全速：MAX=3（三臂并行，10 核机器留足余量）；安全由 watch_P14c_thermal.sh 兜底
#   （降频即 SIGSTOP 全部仿真、退避后恢复，数据无损）。
# 可续跑（已达 TGT 跳过、断点接续）。
cd "$(dirname "$0")"
MAX=${P14C_MAX:-3}
COOL=${P14C_COOL:-120}
LOG=chain_P14c.log
BASE=state_exp
TGT=${P14C_TGT:-375}
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(off full shuf)

log "===== P14c（内容敏感听者）采集启动（fork 自 ${BASE}，MAX=${MAX}，TGT=${TGT}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_P14c_$a; l=logs_P14c_$a; i=inbox_P14c_$a; c=config_P14c_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "P14c:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "P14c:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"
      log "P14c:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"
      cp -R "$BASE" "$s"
      rm -f "$s/pid" "$s/rng_state.json" "$s/response_model.json" \
            "$s/e6_state.json" "$s/affect.json" "$s/spont.json" "$s/spont.jsonl"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_P14c_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "P14c:$a 启动（PID $(cat "$s/pid")）"
    an+=("$a"); ad+=("$s")
  done
  sleep 60
  kn=(); kd=(); j=0
  while [ $j -lt ${#an[@]} ]; do
    a=${an[$j]}; d=${ad[$j]}
    dd=$(day_of "$d"); [ -z "$dd" ] && dd=0
    p=$(cat "$d/pid" 2>/dev/null); alive=0
    [ -n "$p" ] && kill -0 "$p" 2>/dev/null && alive=1
    if [ $alive -eq 1 ] && [ "$dd" -lt "$TGT" ]; then
      kn+=("$a"); kd+=("$d")
    elif [ $alive -eq 1 ]; then
      kill -TERM "$p" 2>/dev/null; log "P14c:$a 达 day $dd/${TGT}，停止"
    else
      log "P14c:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
  if [ ${#an[@]} -eq 0 ] && [ $next -lt $n ]; then
    log "散热间歇 ${COOL}s（下一臂：${ARMS[$next]}）"
    sleep "$COOL"
  fi
done

log "===== P14c 三臂全部完成 ====="
