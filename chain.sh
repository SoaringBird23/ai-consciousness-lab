#!/bin/bash
# chain.sh — 限流串行器：加速线最多 2 路并发（控温）
#   先等 P4c 收尾 → 再把 S1(3) + S2(4) + R(6) 放进一个"最多 2 并发"的池里依次跑
#   进度日志：chain.log        停止整条链：kill $(cat chain.pid)
cd "$(dirname "$0")"
LOG=chain.log
MAX=2
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# 从 trajectory.jsonl 末行取当前仿真日；取不到返回空
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

# 依据 kind/key 设定目录与配置（写入全局变量）
job_dirs(){
  case "$1" in
    repl) STATE_DIR=state_repl_$2; CONFIG=config_repl_$2.json; LOG_DIR=logs_repl_$2; INBOX_DIR=inbox_repl_$2 ;;
    s2)   STATE_DIR=state_s2_$2;   CONFIG=config_s2_$2.json;   LOG_DIR=logs_s2_$2;   INBOX_DIR=inbox_s2_$2 ;;
    R)    STATE_DIR=state_R_$2;    CONFIG=config_R_$2.json;    LOG_DIR=logs_R_$2;    INBOX_DIR=inbox_R_$2 ;;
    R2)   STATE_DIR=state_R2_$2;   CONFIG=config_R2_$2.json;   LOG_DIR=logs_R2_$2;   INBOX_DIR=inbox_R2_$2 ;;
    p5)   STATE_DIR=state_p5_$2;   CONFIG=config_p5_$2.json;   LOG_DIR=logs_p5_$2;   INBOX_DIR=inbox_p5_$2 ;;
  esac
}

# 启动单个任务（已在跑则复用）；目标日写入 $STATE_DIR/.target
#   目标日：repl/s2 = day 60；R = fork 点 day + 30（旧脚本误写为 30，会一启动就误判达标）
start_job(){
  local kind=$1 key=$2
  JOB_DONE=0
  job_dirs "$kind" "$key"
  mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
  # R / R2 / p5 首次运行需从成熟线 fork
  if { [ "$kind" = "R" ] || [ "$kind" = "R2" ] || [ "$kind" = "p5" ]; } && [ ! -f "$STATE_DIR/stage.json" ]; then
    rm -rf "$STATE_DIR"; cp -R state_exp "$STATE_DIR"; rm -f "$STATE_DIR/pid" "$STATE_DIR/e6_state.json"
    [ "$kind" = "p5" ] && rm -f "$STATE_DIR/affect.json"
    log "$kind:$key 已从 state_exp fork"
  fi
  # 目标日：repl/s2 = day 60；R/R2/p5 = fork 点 day + 30（旧脚本误写为 30，会一启动就误判达标）
  if [ ! -f "$STATE_DIR/.target" ]; then
    local base; base=$(day_of "$STATE_DIR"); [ -z "$base" ] && base=0
    if [ "$kind" = "R" ] || [ "$kind" = "R2" ] || [ "$kind" = "p5" ]; then echo $((base + 30)) > "$STATE_DIR/.target"
    else echo 60 > "$STATE_DIR/.target"; fi
  fi
  local tgt; tgt=$(cat "$STATE_DIR/.target")
  local cur; cur=$(day_of "$STATE_DIR"); [ -z "$cur" ] && cur=0
  if [ "$cur" -ge "$tgt" ]; then log "$kind:$key 已完成（day $cur/$tgt），跳过"; JOB_DONE=1; return; fi
  if [ -f "$STATE_DIR/pid" ] && kill -0 "$(cat "$STATE_DIR/pid")" 2>/dev/null; then
    log "$kind:$key 复用已在跑的进程（PID $(cat "$STATE_DIR/pid")）"
  else
    # 关键：必须逐任务隔离环境变量，否则 main.py 回退到默认 state/（曾导致 2 路子进程同时写主线）
    STATE_DIR="$STATE_DIR" LOG_DIR="$LOG_DIR" CONFIG="$CONFIG" INBOX_DIR="$INBOX_DIR" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_${kind}_${key}_console.out" 2>&1 &
    echo $! > "$STATE_DIR/pid"
    nohup caffeinate -i -w "$(cat "$STATE_DIR/pid")" >/dev/null 2>&1 &
    log "$kind:$key 启动（PID $(cat "$STATE_DIR/pid")）"
  fi
}

echo $$ > chain.pid
log "===== 限流串行器启动（PID $$，MAX=${MAX} 路并发）====="

# ── 0. 等 P4c 收尾（fork 点 day 248 + 30 = 278）──
if [ -f state_body3/pid ] && kill -0 "$(cat state_body3/pid)" 2>/dev/null; then
  log "等待 P4c 收尾（目标 day 278）"
  while true; do
    d=$(day_of state_body3); [ -z "$d" ] && d=0
    p=$(cat state_body3/pid 2>/dev/null)
    if [ -z "$p" ] || ! kill -0 "$p" 2>/dev/null; then log "P4c 进程已退出（day $d）"; break; fi
    if [ "$d" -ge 278 ]; then log "P4c 达到 day $d，停止"; kill -TERM "$p" 2>/dev/null; break; fi
    sleep 60
  done
fi

# ── 1. 统一任务池：任意时刻最多 MAX 路并发 ──
# R 阶梯（prereg_R）已作废：采集前审计发现那根通道双重失效（门开火率 0.00% + 目标变量
# 无人消费），跑它只能得到关于"从未打开且打开也没人看"的通道的零结果。改为 R2：
# 把"门"与"目标"各自变成自变量，直接判定零结果的来源。见 experiments/prereg_R2.json。
# P5（痛/乐）排在 R2 之后，三臂 off/rec_only/on 同 fork 自 state_exp。见 experiments/prereg_P5_affect.json。
JOBS=(repl:101 repl:102 repl:103 s2:D s2:NC s2:NG s2:BO R2:ctl_none R2:dead_gate R2:open_dead_target R2:open_s4_lo R2:open_s4_mid R2:open_s4_hi p5:off p5:rec_only p5:on)
n=${#JOBS[@]}; next=0
an=(); ad=(); at=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    j=${JOBS[$next]}; next=$((next+1))
    start_job "${j%%:*}" "${j##*:}"
    [ "$JOB_DONE" = "1" ] && continue
    an+=("$j"); ad+=("$STATE_DIR"); at+=("$(cat "$STATE_DIR/.target")")
  done
  sleep 60
  kn=(); kd=(); kt=(); i=0
  while [ $i -lt ${#an[@]} ]; do
    d=${ad[$i]}; t=${at[$i]}; nm=${an[$i]}
    dd=$(day_of "$d"); [ -z "$dd" ] && dd=0
    p=$(cat "$d/pid" 2>/dev/null); alive=0
    [ -n "$p" ] && kill -0 "$p" 2>/dev/null && alive=1
    if [ $alive -eq 1 ] && [ "$dd" -lt "$t" ]; then
      kn+=("$nm"); kd+=("$d"); kt+=("$t")
    elif [ $alive -eq 1 ]; then
      kill -TERM "$p" 2>/dev/null; log "$nm 达 day $dd/$t，停止"
    elif [ "$dd" -lt "$t" ]; then
      log "$nm 进程异常退出（day $dd/$t）"
    else
      log "$nm 达 day $dd/$t"
    fi
    i=$((i+1))
  done
  an=("${kn[@]}"); ad=("${kd[@]}"); at=("${kt[@]}")
done

log "===== 三批全部完成 ====="
