#!/bin/bash
# C1 对照线：第一人称语料语境反转（频率匹配），day 0 出生
# 停止：kill $(cat state_c1/pid)
cd "$(dirname "$0")"
export STATE_DIR=state_c1 LOG_DIR=logs_c1 CONFIG=config_c1.json INBOX_DIR=inbox_c1
mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
  echo "C1 线已在运行（PID $(cat $STATE_DIR/pid)）"; exit 0
fi
nohup ./venv/bin/python main.py --time-scale 1e9 > logs_c1_console.out 2>&1 &
echo $! > "$STATE_DIR/pid"
echo "C1 对照线已启动（PID $(cat "$STATE_DIR/pid")）。预注册：experiments/prereg_C1.json"
