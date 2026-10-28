#!/bin/bash
# watch_P12_analyze.sh — 等 P12 三臂全部达 day 345 且 harness 退出后，自动跑分析器并落盘。
#
# 就绪判据：三臂 trajectory day >= 345，且无 main.py --time-scale 1e9 进程，且 run_P12.sh 已退出。
# 产出：experiments/results_P12.json + 控制台表格到 chain_P12_analyze.log
# 主判据 H12b：adj_top3(soft) − adj_top3(soft_shuf) ≥ 0.07
export PATH=/bin:/usr/bin:/usr/sbin:/sbin
cd "$(dirname "$0")"
LOG=chain_P12_analyze.log
TGT=345
LOCK=.watch_P12_analyze.lock
ARMS=(pool soft soft_shuf)
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }

if ! mkdir "$LOCK" 2>/dev/null; then log "已有分析守望在运行，退出"; exit 0; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

log "分析守望启动：等待 P12 三臂达 day ${TGT} 且 harness 退出…"
while true; do
  if [ -f experiments/results_P12.json ]; then log "results_P12.json 已存在，守望退出"; exit 0; fi
  allok=1
  for a in "${ARMS[@]}"; do
    dd=$(day_of "state_P12_$a"); [ -z "$dd" ] && dd=0
    if [ "$dd" -lt "$TGT" ]; then allok=0; log "等待中：$a day=${dd}/${TGT}"; break; fi
  done
  if [ "$allok" -eq 1 ]; then
    if pgrep -f "[m]ain.py --time-scale 1e9" >/dev/null 2>&1; then
      log "三臂已达 day ${TGT} 但仍有运行中进程，稍候"
    elif pgrep -f "[r]un_P12.sh" >/dev/null 2>&1; then
      log "三臂已达 day ${TGT} 但 run_P12.sh 仍在，稍候"
    else
      log "就绪：三臂到齐且 harness 退出，运行分析器（H12b）"
      WSP_STATE_PREFIX=state_P12_ WSP_TRUTH_STATE=state_P6_childes \
        WSP_RESULTS_ID=P12 WSP_LABEL=P12 WSP_HYP=H12b \
        WSP_ARMS=pool,soft,soft_shuf WSP_BASE=pool \
        ./venv/bin/python experiments/analyze_R5.py --json >> "$LOG" 2>&1
      log "分析器完成（退出码 $?）；结果见 experiments/results_P12.json"
      exit 0
    fi
  fi
  sleep 60
done
