#!/bin/bash
# run_P14.sh — P14 从反射到意图（Reflex → Intention）三臂采集
#
# 见 experiments/prereg_P14_reflex_to_intent.json。
#
# fork 自 state_exp（XP 线：55 型旧语料、caregiver.mode=contingent、day255 成熟快照），
# 窗口 60 仿真日 → TGT=315。三臂：
#   off    现状基线（选择 = 检索胜者，response_model.enabled=false）
#   full   候选池 top-5 内按 E[f] 选第一（启用响应模型）
#   shuf   同 full，但 E 的『型→效果』键在候选间打乱（内容对照）
# 三臂仅差 response_model.enabled/shuffle；time.seed_python_random=true 保证臂间 RNG 对齐
# （config_P14_off/full/shuf.json）。不启用 compose（变量分离）。
#
# 并发上限与臂间散热可配（默认 MAX=2 / COOL=180，控温）。可续跑（已达 TGT 跳过、断点接续）。
cd "$(dirname "$0")"
MAX=${P14_MAX:-2}
COOL=${P14_COOL:-180}          # 一臂结束后、还有下一臂时的散热间歇（秒）
LOG=chain_P14.log
BASE=state_exp
TGT=${P14_TGT:-315}            # fork day 255 + 60
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(off full shuf)

log "===== P14（从反射到意图）采集启动（fork 自 ${BASE}，MAX=${MAX}，TGT=${TGT}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_P14_$a; l=logs_P14_$a; i=inbox_P14_$a; c=config_P14_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "P14:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "P14:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"
      log "P14:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"
      cp -R "$BASE" "$s"
      # 清除不可继承的运行期状态：pid、RNG 状态（强制三臂从同一 seed 起步）、
      # 响应模型（全新 E）、E6 状态、affect/spont（非本实验键，保持默认关）
      rm -f "$s/pid" "$s/rng_state.json" "$s/response_model.json" \
            "$s/e6_state.json" "$s/affect.json" "$s/spont.json" "$s/spont.jsonl"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_P14_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "P14:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "P14:$a 达 day $dd/${TGT}，停止"
    else
      log "P14:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
  if [ ${#an[@]} -eq 0 ] && [ $next -lt $n ]; then
    log "散热间歇 ${COOL}s（下一臂：${ARMS[$next]}）"
    sleep "$COOL"
  fi
done

log "===== P14 三臂全部完成 ====="
