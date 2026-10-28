#!/bin/bash
# run_P12.sh — P12 真·全长池采集（零缺陷代码上的双向工作空间最终测试）
#
# 见 experiments/prereg_P12_pool.json。
#
# 三臂同 fork 自 state_P6_childes（day 315，与 P6B/P8/P9/P10/P11 完全同一基底与窗口），目标 day 345。
# 代码侧本批清零：① soft_prior 候选池短路（回退到 200 抽样）；② vocal 应答逐 tick 重试；
# ③ workspace._acc_h 未持久化；④ language._last_thought/_last_evoke_t 未持久化。
# 各臂仅 workspace 块不同（非 workspace 键逐字取自 config_P11_soft.json，已校验）：
#   pool       soft_prior=true, soft_gamma=0.0  → 全池候选、零加权（分解出候选池本身的效应）
#   soft       soft_prior=true, soft_gamma=1.0  → 全池 + act 软加权 —— 主臂
#   soft_shuf  同 soft + shuffle_assoc          → 内容对照
#
# 并发上限默认 1（控温、串行），臂间散热 300s。可续跑（已达 TGT 跳过、未完成从断点接续）。
cd "$(dirname "$0")"
MAX=${P12_MAX:-1}
COOL=${P12_COOL:-300}         # 臂间散热间歇（秒）
LOG=chain_P12.log
BASE=state_P6_childes
TGT=345                       # fork 315 + 30
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(pool soft soft_shuf)

log "===== P12 真·全长池采集启动（fork 自 ${BASE}，MAX=${MAX}，TGT=${TGT}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_P12_$a; l=logs_P12_$a; i=inbox_P12_$a; c=config_P12_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "P12:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "P12:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"
      log "P12:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"
      cp -R "$BASE" "$s"
      rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json" \
            "$s/spont.json" "$s/spont.jsonl" "$s/affect.json" "$s/workspace.json"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_P12_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "P12:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "P12:$a 达 day $dd/${TGT}，停止"
    else
      log "P12:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
  # 无人值守散热：一臂结束后、还有下一臂时，先空转降温再启动（不改变任何实验语义）
  if [ ${#an[@]} -eq 0 ] && [ $next -lt $n ]; then
    log "散热间歇 ${COOL}s（下一臂：${ARMS[$next]}）"
    sleep "$COOL"
  fi
done

log "===== P12 三臂全部完成 ====="
