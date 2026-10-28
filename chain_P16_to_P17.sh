#!/bin/bash
# 等 P16 完成（results_P16.json 存在 且 无仿真 且 run_P16.sh 退出）→ 自动启动 P17（人类式扩词）
cd "$(dirname "$0")"
LOG=chain_P16_to_P17.log
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
log "续跑链启动：等待 P16 完成…"
while true; do
  if [ -f experiments/results_P16.json ] \
     && ! pgrep -f "[m]ain.py --time-scale 1e9" >/dev/null 2>&1 \
     && ! pgrep -f "[r]un_P16.sh" >/dev/null 2>&1; then
    break
  fi
  sleep 60
done
log "P16 完成 → 启动 P17（三臂 fixed/grow/growfast；人类模式=grow）"
nohup ./run_P17.sh > logs_P17_chain.out 2>&1 &
sleep 3
nohup ./watch_P17_thermal.sh >/dev/null 2>&1 &
nohup ./watch_P17_analyze.sh >/dev/null 2>&1 &
log "P17 已启动（run+thermal+analyze）"
