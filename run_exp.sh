#!/bin/bash
# 结晶线：总结全部实验经验的新加速个体（day 0 出生，1e9×）
# 停止：kill $(cat state_exp/pid)
cd "$(dirname "$0")"
export STATE_DIR=state_exp LOG_DIR=logs_exp CONFIG=config_exp.json INBOX_DIR=inbox_exp
mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
  echo "结晶线已在运行（PID $(cat $STATE_DIR/pid)）"; exit 0
fi
nohup ./venv/bin/python main.py --time-scale 1e9 > logs_exp_console.out 2>&1 &
echo $! > "$STATE_DIR/pid"
nohup caffeinate -i -w $(cat "$STATE_DIR/pid") >/dev/null 2>&1 &
echo "结晶线已启动（PID $(cat $STATE_DIR/pid)）。首个个体：从出生起生活在全部经验结晶的世界里。"
