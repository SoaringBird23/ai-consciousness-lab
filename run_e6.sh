#!/bin/bash
# E6 因果中介线（p1 损伤期）：fork 自结晶线，回流通道切断
# 停止：kill $(cat state_e6/pid)
cd "$(dirname "$0")"
export STATE_DIR=state_e6 LOG_DIR=logs_e6 CONFIG=config_e6.json INBOX_DIR=inbox_e6
mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
  echo "E6 线已在运行（PID $(cat $STATE_DIR/pid)）"; exit 0
fi
nohup ./venv/bin/python main.py --time-scale 1e9 > logs_e6_console.out 2>&1 &
echo $! > "$STATE_DIR/pid"
echo "E6 损伤线已启动（PID $(cat "$STATE_DIR/pid")）。预注册：experiments/prereg_E6.json"
