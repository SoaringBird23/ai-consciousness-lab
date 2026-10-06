#!/bin/bash
# P4c 痕迹实验线：fork 自 state_body2，给行动一个不与世界混淆的后果（1e9×）
# 停止：kill $(cat state_body3/pid)
cd "$(dirname "$0")"
export STATE_DIR=state_body3 LOG_DIR=logs_body3 CONFIG=config_body3.json INBOX_DIR=inbox_body3
mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
  echo "P4c 线已在运行（PID $(cat $STATE_DIR/pid)）"; exit 0
fi
nohup ./venv/bin/python main.py --time-scale 1e9 > logs_body3_console.out 2>&1 &
echo $! > "$STATE_DIR/pid"
nohup caffeinate -i -w $(cat "$STATE_DIR/pid") >/dev/null 2>&1 &
echo "P4c 线已启动（PID $(cat $STATE_DIR/pid)）。痕迹层：它可以写下只可能来自它的东西。"
