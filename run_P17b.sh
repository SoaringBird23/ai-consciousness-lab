#!/bin/bash
# run_P17b.sh — P17b 词汇爆发（人类式扩词，三臂 fixed/grow/growfast）
#
# 见 experiments/prereg_P17b.json。
# 环境侧：world_contingent 照护者（wc_rate=2/时）；**言语率 speech_per_hour_quiet=20/时（人类 IDS 量级）**。
# 系统侧：corpus_vocab_cap（top-cap）+ vocab_growth（adaptive/fixed_fast/none）。
# fork 自 state_exp（day 255），60 日窗口，TGT=315。
cd "$(dirname "$0")"
MAX=${P17b_MAX:-3}
COOL=${P17b_COOL:-120}
LOG=chain_P17b.log
BASE=state_exp
TGT=${P17b_TGT:-315}
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(fixed grow growfast)

log "===== P17b（指称落地，world_contingent）采集启动（fork 自 ${BASE}，MAX=${MAX}，TGT=${TGT}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_P17b_$a; l=logs_P17b_$a; i=inbox_P17b_$a; c=config_P17b_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then log "P17b:$a 已完成（day $dd/${TGT}），跳过"; continue; fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "P17b:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"; an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"; log "P17b:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"; cp -R "$BASE" "$s"
      rm -f "$s/pid" "$s/rng_state.json" "$s/response_model.json" \
            "$s/counterfactual.jsonl" "$s/semantics.json" "$s/grounding.jsonl" \
            "$s/e6_state.json" "$s/affect.json" "$s/spont.json" "$s/spont.jsonl"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_P17b_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "P17b:$a 启动（PID $(cat "$s/pid")）"
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
    elif [ $alive -eq 1 ]; then kill -TERM "$p" 2>/dev/null; log "P17b:$a 达 day $dd/${TGT}，停止"
    else log "P17b:$a 进程退出（day $dd/${TGT}）"; fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
  if [ ${#an[@]} -eq 0 ] && [ $next -lt $n ]; then
    log "散热间歇 ${COOL}s（下一臂：${ARMS[$next]}）"; sleep "$COOL"
  fi
done
log "===== P17b 三臂全部完成 ====="
