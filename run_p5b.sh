#!/bin/bash
# run_p5b.sh — p5 重跑（v2）：臂间 RNG 对齐
#
# 背景（同 R2 v2）：
#   首轮 p5 三臂（off/rec_only/on）fork 自同一 state_exp，但 language.py 用未播种的
#   Python 全局 random → 臂间念头流互不对齐，和 R2 v1 是同一种混杂：
#   "四指标 <10%" 里混入了逐次运行差异，不能读成"无影响"。
#   （首轮 off vs rec_only 仅差 −1.4%/−4.0%，而 rec_only 行为上应与 off 等价——
#    这个差值就是逐次运行的噪声底。）
#
# 本轮：config 开 time.seed_python_random=true（显式播种 + RNG 落盘/恢复），
#   三臂共享同一条 RNG 流。旧数据保留在 state_p5pre_* 作"未对齐"对照。
#
# 并发上限 2（控温；系统 10 核，实验占 2-4 核）。
#
# 可续跑（2026-10-06 晚补，同 run_R2b.sh）：调度器裸跑会随终端会话被 SIGHUP 杀死。
#   此处加幂等守卫——已达 TGT 的臂跳过、仍在跑的臂接管监听，只补跑未完成臂；
#   启动时务必用 nohup 脱离会话。
cd "$(dirname "$0")"
MAX=2
LOG=chain_p5b.log
TGT=285                      # fork 点 day 255 + 30
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(off rec_only on)

log "===== p5 v2 重跑启动（seed_python_random=true，MAX=${MAX}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_p5_$a; l=logs_p5_$a; i=inbox_p5_$a; c=config_p5_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "p5:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "p5:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    rm -rf "$s"
    cp -R state_exp "$s"
    rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json" "$s/affect.json"
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_p5_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "p5:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "p5:$a 达 day $dd/${TGT}，停止"
    else
      log "p5:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
done

log "===== p5 v2 三臂全部完成 ====="
