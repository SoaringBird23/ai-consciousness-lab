#!/bin/bash
# 结晶线 P3 实时分支：状态从结晶线 state_exp fork（state_exp_p3），以 1× 实时运行。
# 照护者 = 真实用户（inbox_exp_p3/say_*.txt，用 talk.py 输入）。
# 注意：STOP 文件全局共享——停本线请用 kill $(cat state_exp_p3/pid)
cd "$(dirname "$0")"
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export STATE_DIR=state_exp_p3 LOG_DIR=logs_exp_p3 CONFIG=config_exp_p3.json INBOX_DIR=inbox_exp_p3
mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
  echo "结晶线 P3 分支已在运行（PID $(cat $STATE_DIR/pid)）"; exit 0
fi
nohup ./venv/bin/python main.py --time-scale 1 > logs_exp_p3_console.out 2>&1 &
echo $! > "$STATE_DIR/pid"
nohup caffeinate -i -w $(cat "$STATE_DIR/pid") >/dev/null 2>&1 &
echo "结晶线 P3 分支已启动（PID $(cat $STATE_DIR/pid)）。"
echo "照护者台：STATE_DIR=state_exp_p3 LOG_DIR=logs_exp_p3 INBOX_DIR=inbox_exp_p3 ./venv/bin/python talk.py"
