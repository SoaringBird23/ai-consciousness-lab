#!/bin/bash
# run_P19b.sh — P19b 组合（词级，三臂 off/full/shuf）
#
# 见 experiments/prereg_P19b.json。
# 基底=config_P19_full；唯一变量=habituation（off/full/shuf）。
# 唯一变量=word_compose：off 关 / full 开 / shuf 开但词→词关联打乱（内容对照）。
# fork 自 state_exp（day 255），60 日窗口，TGT=315。
cd "$(dirname "$0")"
MAX=${P19b_MAX:-3}
COOL=${P19b_COOL:-120}
LOG=chain_P19b.log
BASE=state_exp
TGT=${P19b_TGT:-315}
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(off full shuf)

log "===== P19b 组合（词级）采集启动（fork 自 ${BASE}，MAX=${MAX}，TGT=${TGT}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_P19b_$a; l=logs_P19b_$a; i=inbox_P19b_$a; c=config_P19b_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then log "P19b:$a 已完成（day $dd/${TGT}），跳过"; continue; fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "P19b:$a 已在运行（PID ${p}，day $dd/${TGT}），接管监听"; an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"; log "P19b:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"; cp -R "$BASE" "$s"
      rm -f "$s/pid" "$s/rng_state.json" "$s/response_model.json" \
            "$s/counterfactual.jsonl" "$s/semantics.json" "$s/grounding.jsonl" \
            "$s/word_compose.json" "$s/dialogue.json" "$s/habituation.json" "$s/dialogue_turns.jsonl" "$s/inner_speech.jsonl" \
            "$s/e6_state.json" "$s/affect.json" "$s/spont.json" "$s/spont.jsonl"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_P19b_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "P19b:$a 启动（PID $(cat "$s/pid")）"
    an+=("$a"); ad+=("$s")
  done
  sleep 60
  kn=(); kd=(); j=0
  while [ $j -lt ${#an[@]} ]; do
    a=${an[$j]}; d=${ad[$j]}
    dd=$(day_of "$d"); [ -z "$dd" ] && dd=0
    p=$(cat "$d/pid" 2>/dev/null); alive=0
    [ -n "$p" ] && kill -0 "$p" 2>/dev/null && alive=1
    if [ $alive -eq 1 ] && [ "$dd" -lt "$TGT" ]; then kn+=("$a"); kd+=("$d")
    elif [ $alive -eq 1 ]; then kill -TERM "$p" 2>/dev/null; log "P19b:$a 达 day $dd/${TGT}，停止"
    else log "P19b:$a 进程退出（day $dd/${TGT}）"; fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
  if [ ${#an[@]} -eq 0 ] && [ $next -lt $n ]; then
    log "散热间歇 ${COOL}s（下一臂：${ARMS[$next]}）"; sleep "$COOL"
  fi
done
log "===== P19b 三臂全部完成 ====="
