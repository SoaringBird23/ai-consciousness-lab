#!/bin/bash
# S1 复现批次：3 个独立种子，从 day 0 出生，跑同一开发流程
# 停止：for s in 101 102 103; do kill $(cat state_repl_$s/pid); done
cd "$(dirname "$0")"
for s in 101 102 103; do
  export STATE_DIR=state_repl_$s LOG_DIR=logs_repl_$s CONFIG=config_repl_$s.json INBOX_DIR=inbox_repl_$s
  mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
  if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
    echo "种子 $s 已在运行"; continue
  fi
  nohup ./venv/bin/python main.py --time-scale 1e9 > logs_repl_${s}_console.out 2>&1 &
  echo $! > "$STATE_DIR/pid"
  nohup caffeinate -i -w $(cat "$STATE_DIR/pid") >/dev/null 2>&1 &
  echo "种子 $s 已启动（PID $(cat $STATE_DIR/pid)）"
done
