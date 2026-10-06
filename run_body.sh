#!/bin/bash
# P4 行动环实验线：fork 自结晶线（day 157），给它一个能施力的世界（1e9× 加速）
# 停止：kill $(cat state_body/pid)
cd "$(dirname "$0")"
export STATE_DIR=state_body LOG_DIR=logs_body CONFIG=config_body.json INBOX_DIR=inbox_body
mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
  echo "P4 行动环线已在运行（PID $(cat $STATE_DIR/pid)）"; exit 0
fi
nohup ./venv/bin/python main.py --time-scale 1e9 > logs_body_console.out 2>&1 &
echo $! > "$STATE_DIR/pid"
nohup caffeinate -i -w $(cat "$STATE_DIR/pid") >/dev/null 2>&1 &
echo "P4 行动环线已启动（PID $(cat $STATE_DIR/pid)）。把心装进身体：已有心智 + 可施力的世界。"
