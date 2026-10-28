#!/bin/bash
# run_R5.sh — R5 采集（激活式工作集：扩散激活 × 容量受限检索 × 复述回写）
#
# 见 experiments/prereg_R5.json。
#
# 六臂同 fork 自 state_exp，目标 day 285（fork 255 + 30）。各臂仅 workspace 开关/参数不同：
#   off       {enabled:false}                      回归基线（须逐位一致）
#   full      κ=1.0,k=6,tau=10min,正常            主臂
#   shuf      同 full + shuffle_assoc              内容特定性阴性对照（打乱联想行）
#   nodep     同 full + no_deposit                 只读不写（检验『写』是否必要）
#   nodecay   同 full + tau=1e5（近似不衰减）       检验衰减是否必要
#   bigk      同 full + k=20                       工作集容量对照
#
# 并发上限默认 2，可用 R5_MAX 覆盖。可续跑（已达 TGT 跳过、未完成从断点接续）。
cd "$(dirname "$0")"
MAX=${R5_MAX:-2}
LOG=chain_R5.log
TGT=285
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(off full shuf nodep nodecay bigk)

log "===== R5 采集启动（seed_python_random=true，MAX=${MAX}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_R5_$a; l=logs_R5_$a; i=inbox_R5_$a; c=config_R5_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "R5:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "R5:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"
      log "R5:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"
      cp -R state_exp "$s"
      rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json" \
            "$s/spont.json" "$s/spont.jsonl" "$s/affect.json" "$s/workspace.json"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_R5_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "R5:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "R5:$a 达 day $dd/${TGT}，停止"
    else
      log "R5:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
done

log "===== R5 六臂全部完成 ====="
