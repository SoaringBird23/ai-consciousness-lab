#!/bin/bash
# run_R3b.sh — R3 采集（自发双向：C1 成句生成 × C2 预期-比较-修正 × C3 后果驱动耦合）
#
# 见 experiments/prereg_R3.json（status=预注册（采集前，含 affect 修正））。
#
# 六臂同 fork 自 state_exp（成熟线，day 255），目标 day 285（fork + 30），
# 每臂仅 spont 开关不同：
#   spont_off     {enabled:false}                       回归基线（须与 ctl_none 逐位一致）
#   spont_gen     {enabled,compose}                     只开 C1
#   spont_loop    {enabled,self_predict}                只开 C2
#   spont_full    {enabled,compose,self_predict,learn_coupling}  全开（H3c 主臂）
#   spont_shuf    同 full + shuffle                     后果打乱对照（H3c 阴性对照）
#   spont_replay  同 full + compose:false               『生成是必要条件』检验
#
# 修正（2026-10-07，采集前，见 prereg amendment）：
#   五个 ON 臂的身体补 affect{enabled:true, k_affect:0.0}——C3 后果 = Δease−Δdistress
#   +(err_before−err_now) 需要乐/痛真实存在；继承自 R2 的身体无 affect 块则后果恒 0、
#   g 永不生长。k_affect=0 ⇒ 乐/痛只被计算供 C3 读取，不回馈背景（不给方向）。
#   spont_off 不变，故 off≡ctl_none 的逐位回归仍成立。
#
# 并发上限默认 2（控温），可用环境变量 R3_MAX 覆盖（如 R3_MAX=6 抢时间）。
# seed_python_random=true（臂间 RNG 对齐，同 R2 v2 纪律）。
# 可续跑：已达 TGT 的臂跳过、仍在跑的臂接管监听，只补跑未完成臂。
#   启动请用 nohup 脱离会话：
#     nohup ./run_R3b.sh > chain_R3b.out 2>&1 &
cd "$(dirname "$0")"
MAX=${R3_MAX:-2}
LOG=chain_R3b.log
TGT=285                      # fork 点 day 255 + 30
set -u
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

ARMS=(spont_off spont_gen spont_loop spont_full spont_shuf spont_replay)

log "===== R3 采集启动（seed_python_random=true，MAX=${MAX}）====="
n=${#ARMS[@]}; next=0
an=(); ad=()

while [ $next -lt $n ] || [ ${#an[@]} -gt 0 ]; do
  while [ ${#an[@]} -lt $MAX ] && [ $next -lt $n ]; do
    a=${ARMS[$next]}; next=$((next+1))
    s=state_R3_$a; l=logs_R3_$a; i=inbox_R3_$a; c=config_R3_$a.json
    dd=$(day_of "$s"); [ -z "$dd" ] && dd=0
    if [ "$dd" -ge "$TGT" ]; then
      log "R3:$a 已完成（day $dd/${TGT}），跳过"
      continue
    fi
    p=$(cat "$s/pid" 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      log "R3:$a 已在运行（PID $p，day $dd/${TGT}），接管监听"
      an+=("$a"); ad+=("$s"); continue
    fi
    if [ -f "$s/trajectory.jsonl" ] && [ "$dd" -gt 0 ]; then
      # 已有进度：真断点续跑（main.py 各模块 load() 恢复），保留 rng/spont/affect 状态
      rm -f "$s/pid"
      log "R3:$a 断点续跑（从 day $dd 接续）"
    else
      # 首次：从 state_exp 干净 fork
      rm -rf "$s"
      cp -R state_exp "$s"
      rm -f "$s/pid" "$s/e6_state.json" "$s/rng_state.json" \
            "$s/spont.json" "$s/spont.jsonl" "$s/affect.json"
    fi
    mkdir -p "$l" "$i"
    STATE_DIR="$s" LOG_DIR="$l" CONFIG="$c" INBOX_DIR="$i" \
      nohup ./venv/bin/python main.py --time-scale 1e9 > "logs_R3_${a}_console.out" 2>&1 &
    echo $! > "$s/pid"
    nohup caffeinate -i -w "$(cat "$s/pid")" >/dev/null 2>&1 &
    log "R3:$a 启动（PID $(cat "$s/pid")）"
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
      kill -TERM "$p" 2>/dev/null; log "R3:$a 达 day $dd/${TGT}，停止"
    else
      log "R3:$a 进程退出（day $dd/${TGT}）"
    fi
    j=$((j+1))
  done
  if [ ${#kn[@]} -eq 0 ]; then an=(); ad=(); else an=("${kn[@]}"); ad=("${kd[@]}"); fi
done

log "===== R3 六臂全部完成 ====="
