#!/bin/bash
# run_R2b.sh — R2 重跑（v2）：臂间 RNG 对齐
#
# 背景（见 experiments/prereg_R2.json 的 amendments）：
#   首轮 R2 的六臂虽 fork 自同一 state_exp（继承段逐字节一致），但 language.py
#   用的是 **未播种的 Python 全局 random**（OS 熵种子，不随 fork 复制、不落盘），
#   于是臂间的"念头流"互不对齐——实测两臂逐条相同率仅 ~3%，连几乎未扰动的
#   dead_gate 也一样。这意味着"四指标 <10%"里混入了逐次运行的随机差异，
#   而不是只差一个被操纵的变量。
#
# 本轮：config 里开 time.seed_python_random=true（显式播种 + RNG 状态落盘/恢复），
#   使同一父本 fork 出的各臂共享同一条 RNG 流。已用两条完全同参臂冒烟验证：
#   逐条 100% 相同（修复前 2.7%）。
#
# 并发上限 2（控温）。旧数据保留在 state_R2pre_* 作为"未对齐"对照。
#
# 可续跑（2026-10-06 晚补）：调度器此前裸跑、随终端会话被 SIGHUP 杀死，
#   已完成 2 臂后中断。此处加幂等守卫——已达 TGT 的臂跳过、仍在跑的臂接管监听，
#   只补跑未完成臂；启动时请用 nohup 脱离会话，避免再次被终端关闭带走。
cd "$(dirname "$0")"
MAX=2
LOG=chain_R2b.log
TGT=285                      # fork 点 day 255 + 30
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(ctl_none dead_gate open_dead_target open_s4_lo open_s4_mid open_s4_hi)

log "===== R2 v2 重跑启动（seed_python_random=true，MAX=${MAX}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_R2_$a; l=logs_R2_$a; i=inbox_R2_$a; c=config_R2_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "R2:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "R2:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    rm -rf "$s"
    cp -R state_exp "$s"
    rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json"
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_R2_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "R2:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "R2:$a 达 day $dd/${TGT}，停止"
    else
      log "R2:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
done

log "===== R2 v2 六臂全部完成 ====="
