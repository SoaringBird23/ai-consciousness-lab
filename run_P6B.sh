#!/bin/bash
# run_P6B.sh — P6-B 双向重探采集（扩容模型上的激活式工作集：扩散激活 × 容量受限检索 × 复述回写）
#
# 见 experiments/prereg_P6B_bidirectional.json。
#
# 六臂同 fork 自 state_P6_childes（P6-A 扩容终态，say day 315），目标 day fork+30。
# 各臂仅 workspace 开关/参数不同（非 workspace 键一律逐字取自 config_P6_childes.json）：
#   off       {enabled:false}                      回归基线（须与基底自然续跑逐位一致）
#   full      κ=1.0,k=6,tau=10min,正常            主臂
#   shuf      同 full + shuffle_assoc              内容特定性阴性对照（打乱联想行）
#   nodep     同 full + no_deposit                 只读不写（检验『写』是否必要）
#   nodecay   同 full + tau=1e5（近似不衰减）       检验衰减是否必要
#   bigk      同 full + k=20                       工作集容量对照
#
# 时序前置：须待 run_P6.sh 两臂（TGT=315）停采后再启动，避免 CPU/热载竞争。
# 并发上限默认 2，可用 P6B_MAX 覆盖。可续跑（已达 TGT 跳过、未完成从断点接续）。
cd "$(dirname "$0")"
MAX=${P6B_MAX:-2}
LOG=chain_P6B.log
BASE=state_P6_childes
TGT=345                       # fork 315 + 30
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(off full shuf nodep nodecay bigk)

log "===== P6-B 双向重探采集启动（fork 自 ${BASE}，seed_python_random=true，MAX=${MAX}，TGT=${TGT}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_P6B_$a; l=logs_P6B_$a; i=inbox_P6B_$a; c=config_P6B_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "P6B:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "P6B:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      rm -f "$s/pid"
      log "P6B:$a 断点续跑（从 day $dd 接续）"
    else
      rm -rf "$s"
      cp -R "$BASE" "$s"
      rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json" \
            "$s/spont.json" "$s/spont.jsonl" "$s/affect.json" "$s/workspace.json"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_P6B_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "P6B:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "P6B:$a 达 day $dd/${TGT}，停止"
    else
      log "P6B:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
done

log "===== P6-B 六臂全部完成 ====="
