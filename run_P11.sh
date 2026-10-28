#!/bin/bash
# run_P11.sh — P11 软先验采集（把工作集从『硬候选帽』改为『全长候选池上的打分加权』）
#
# 见 experiments/prereg_P11_soft.json。
#
# 三臂同 fork 自 state_P6_childes（day 315，与 P6B/P8/P9/P10 完全同一基底与窗口），目标 day 345。
# 代码侧同批修复：workspace.decay() 的守卫 bug 使衰减在 tick 级步长下从未执行
# （tau 为死参数、act 终身累积 → uniq=10 坍缩）。本批 tau=720min（12h）与语率(~4.7次沉积/时)匹配。
# 各臂仅 workspace 块不同（非 workspace 键逐字取自 config_P10_off.json，已校验）：
#   hardcap    k=6 硬候选帽保留，无先验        → 检验『衰减首次真正生效』（对照 P6B full 的 0.0424/uniq10）
#   soft       soft_prior=true, γ=1.0          → 候选=全长池，act 作打分加权 —— 主臂
#   soft_shuf  同 soft + shuffle_assoc         → 内容对照
#
# 并发上限默认 1（控温、串行），可用 P11_MAX 覆盖。可续跑（已达 TGT 跳过、未完成从断点接续）。
cd "$(dirname "$0")"
MAX=${P11_MAX:-1}
COOL=${P11_COOL:-300}         # 臂间散热间歇（秒）：避免三臂背靠背连续满载 2.5h
LOG=chain_P11.log
BASE=state_P6_childes
TGT=345                       # fork 315 + 30
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(hardcap soft soft_shuf)

log "===== P11 软先验采集启动（fork 自 ${BASE}，MAX=${MAX}，TGT=${TGT}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_P11_$a; l=logs_P11_$a; i=inbox_P11_$a; c=config_P11_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "P11:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "P11:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"
      log "P11:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"
      cp -R "$BASE" "$s"
      rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json" \
            "$s/spont.json" "$s/spont.jsonl" "$s/affect.json" "$s/workspace.json"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_P11_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "P11:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "P11:$a 达 day $dd/${TGT}，停止"
    else
      log "P11:$a 进程退出（day $dd/${TGT}）"
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

log "===== P11 三臂全部完成 ====="
