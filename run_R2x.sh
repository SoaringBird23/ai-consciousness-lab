#!/bin/bash
# run_R2x.sh — R2x 边界探针（>1σ）：把念头→背景态回流耦合推到 s4 自然 sd 的 1.5σ / 2.0σ
#
# 见 experiments/prereg_R2x.json。
#   xl   target=s4、threshold=0.008、reflow.s2=0.50（1.5σ）、s5=0.375
#   xl2  target=s4、threshold=0.008、reflow.s2=0.66（2.0σ）、s5=0.495
#
# 为什么跑：R2 已用**正确目标 s4** 跑完 0.02/0.10/0.30（≤0.91σ）剂量阶梯，全部阴性；
#   >1σ 是否仍阴性从未测过（prereg_R2x 在册未执行）。这是"双向工作空间"最后一个未测点。
#   对照沿用 R2 口径 state_R2_ctl_none（e6.ablation=true，通道全切，day 285）。
#
# 调度与 run_R2b.sh 逐行同构（fork 清理动作必须一致，否则与 ctl_none 不可比）：
#   幂等——已达 TGT 跳过、未完成从断点接续；并发上限 2（控温）。
cd "$(dirname "$0")"
MAX=2
LOG=chain_R2x.log
TGT=285                      # fork 点 day 255 + 30
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(xl xl2)

log "===== R2x 边界探针启动（seed_python_random=true，MAX=${MAX}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_R2x_$a; l=logs_R2x_$a; i=inbox_R2x_$a; c=config_R2x_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "R2x:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "R2x:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"
      log "R2x:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"
      cp -R state_exp "$s"
      rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_R2x_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "R2x:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "R2x:$a 达 day $dd/${TGT}，停止"
    else
      log "R2x:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
done

log "===== R2x 两臂全部完成 ====="
