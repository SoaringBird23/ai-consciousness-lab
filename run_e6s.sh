#!/bin/bash
# E6 p2 替换线：thought swap 检验念头→目标因果中介
cd "$(dirname "$0")"
export STATE_DIR=state_e6s LOG_DIR=logs_e6s CONFIG=config_e6s.json INBOX_DIR=inbox_e6s
mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
  echo "E6s 已在运行（PID $(cat $STATE_DIR/pid)）"; exit 0
fi
nohup ./venv/bin/python main.py --time-scale 1e9 > logs_e6s_console.out 2>&1 &
echo $! > "$STATE_DIR/pid"
echo "E6s 替换线已启动（PID $(cat "$STATE_DIR/pid")）。swap=我不走×60"
