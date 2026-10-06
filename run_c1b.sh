#!/bin/bash
# C1b 修正对照线：inverted 语境 + 暴露率校准（主判据实例）
# 停止：kill $(cat state_c1b/pid)
cd "$(dirname "$0")"
export STATE_DIR=state_c1b LOG_DIR=logs_c1b CONFIG=config_c1b.json INBOX_DIR=inbox_c1b
mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
  echo "C1b 已在运行（PID $(cat $STATE_DIR/pid)）"; exit 0
fi
nohup ./venv/bin/python main.py --time-scale 1e9 > logs_c1b_console.out 2>&1 &
echo $! > "$STATE_DIR/pid"
echo "C1b 已启动（PID $(cat "$STATE_DIR/pid")）。预注册：experiments/prereg_C1.json + deviation_1"
