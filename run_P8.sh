#!/bin/bash
# run_P8.sh — P8 工作集容量扫描采集（区分『内容特定性』与『候选基数效应』）
#
# 见 experiments/prereg_P8_kscan.json。
#
# 三臂同 fork 自 state_P6_childes（day 315，与 P6B 完全同一基底与窗口），目标 day fork+30=345。
# 相对 P6B 只动 workspace 的 k 与 shuffle_assoc，其余键一律逐字取自 config_P6B_bigk.json：
#   k20_shuf  k=20 + shuffle_assoc   补 P6B bigk（k20 正常联想，adj_top3=0.066）缺失的配对
#   k40_full  k=40，正常联想          向上扫描
#   k40_shuf  k=40 + shuffle_assoc   配对对照
#
# 已有可复用数据（同一基底/窗口/判据）：P6B off(0.003) full(0.042) shuf(0.008) bigk(0.066)
# 并发上限默认 2，可用 P8_MAX 覆盖。可续跑（已达 TGT 跳过、未完成从断点接续）。
cd "$(dirname "$0")"
MAX=${P8_MAX:-2}
LOG=chain_P8.log
BASE=state_P6_childes
TGT=345                       # fork 315 + 30
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(k20_shuf k40_full k40_shuf)

log "===== P8 工作集容量扫描采集启动（fork 自 ${BASE}，seed_python_random=true，MAX=${MAX}，TGT=${TGT}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_P8_$a; l=logs_P8_$a; i=inbox_P8_$a; c=config_P8_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "P8:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "P8:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"
      log "P8:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"
      cp -R "$BASE" "$s"
      rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json" \
            "$s/spont.json" "$s/spont.jsonl" "$s/affect.json" "$s/workspace.json"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_P8_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "P8:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "P8:$a 达 day $dd/${TGT}，停止"
    else
      log "P8:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
done

log "===== P8 三臂全部完成 ====="
