#!/bin/bash
# P4b 时间化行动环：fork 自 state_body，世界相同、心智相同，仅切换动作学习信号（1e9×）
# 停止：kill $(cat state_body2/pid)
cd "$(dirname "$0")"
export STATE_DIR=state_body2 LOG_DIR=logs_body2 CONFIG=config_body2.json INBOX_DIR=inbox_body2
mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
  echo "P4b 线已在运行（PID $(cat $STATE_DIR/pid)）"; exit 0
fi
nohup ./venv/bin/python main.py --time-scale 1e9 > logs_body2_console.out 2>&1 &
echo $! > "$STATE_DIR/pid"
nohup caffeinate -i -w $(cat "$STATE_DIR/pid") >/dev/null 2>&1 &
echo "P4b 线已启动（PID $(cat $STATE_DIR/pid)）。时间化后果 + 自因分离。"
