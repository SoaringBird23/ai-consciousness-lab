#!/bin/bash
# run_P13.sh — P13 重做 A（念头—念头工作空间）采集
#
# 见 experiments/prereg_P13.json。
#
# 三臂同 fork 自 state_P6_childes（day 315，与 P6B/P8/P9/P10/P11/P12 同一基底与窗口），目标 day 345。
# 本批三处改动（相对 P12）：
#   ① A 只学「念头→念头」：workspace.thought_only=true（hear 不写 A）
#   ② 学习/使用分离：phase_split_day=330（<330 只学 A、priming 关；>=330 priming 开、A 冻结只读）
#   ③ 判据同步换：分析器 WSP_TRUTH_SOURCE=thought（念—念真值图，K≈712）
# 各臂仅 workspace 块不同（非 workspace 键逐字取自 config_P12_soft.json，已校验）：
#   tt        priming real（主臂）
#   tt_shuf   同 tt + shuffle_prime（A 行对应打乱，内容对照）
#   tt_off    priming 关（无注入基线）
#
# 并发上限默认 1（控温、串行），臂间散热 300s。可续跑（已达 TGT 跳过、未完成从断点接续）。
cd "$(dirname "$0")"
MAX=${P13_MAX:-1}
COOL=${P13_COOL:-300}         # 臂间散热间歇（秒）
LOG=chain_P13.log
BASE=state_P6_childes
TGT=345                       # fork 315 + 30
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(tt tt_shuf tt_off)

log "===== P13 重做 A（念头—念头工作空间）采集启动（fork 自 ${BASE}，MAX=${MAX}，TGT=${TGT}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_P13_$a; l=logs_P13_$a; i=inbox_P13_$a; c=config_P13_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "P13:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "P13:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"
      log "P13:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"
      cp -R "$BASE" "$s"
      rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json" \
            "$s/spont.json" "$s/spont.jsonl" "$s/affect.json" "$s/workspace.json"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_P13_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "P13:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "P13:$a 达 day $dd/${TGT}，停止"
    else
      log "P13:$a 进程退出（day $dd/${TGT}）"
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

log "===== P13 三臂全部完成 ====="
