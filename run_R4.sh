#!/bin/bash
# run_R4.sh — R4 采集（C3 修正：后果窗口积分 × 重标度）
#
# 见 experiments/prereg_R4.json（status=预注册（采集前））。
#
# 四臂同 fork 自 state_exp（成熟线），目标 day 285（fork 255 + 30）：
#   off    {enabled:false}                              回归基线（须与 ctl_none 逐位一致）
#   full   全开 + 窗口积分 + base_step=0.25             主臂（H4 主检）
#   shuf   同 full + shuffle                             后果打乱对照（H4b 阴性对照）
#   small  全开 + 窗口积分 + base_step=0.02             机制归因（只验『积分』是否足够）
#
# 并发上限默认 2（控温），可用环境变量 R4_MAX 覆盖（如 R4_MAX=4）。
# 可续跑：已达 TGT 的臂跳过、仍在跑的臂接管监听、未完成臂从断点接续（main.py load）。
#   启动请用 nohup 脱离会话：
#     nohup /bin/bash ./run_R4.sh > chain_R4.out 2>&1 &
cd "$(dirname "$0")"
MAX=${R4_MAX:-2}
LOG=chain_R4.log
TGT=285
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(off full shuf small)

log "===== R4 采集启动（seed_python_random=true，MAX=${MAX}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_R4_$a; l=logs_R4_$a; i=inbox_R4_$a; c=config_R4_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "R4:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "R4:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      # 已有进度：真断点续跑（main.py 各模块 load() 恢复），保留 rng/spont/affect 状态
      rm -f "$s/pid"
      log "R4:$a 断点续跑（从 day $dd 接续）"
    else
      # 首次：从 state_exp 干净 fork
      rm -rf "$s"
      cp -R state_exp "$s"
      rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json" \
            "$s/spont.json" "$s/spont.jsonl" "$s/affect.json"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_R4_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "R4:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "R4:$a 达 day $dd/${TGT}，停止"
    else
      log "R4:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
done

log "===== R4 四臂全部完成 ====="
