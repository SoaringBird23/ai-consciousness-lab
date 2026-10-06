#!/bin/bash
# S2 分离批次：2x2（语料含/不含第一人称 × 门控修/未修），各自独立种子，day 0 出生
cd "$(dirname "$0")"
for k in D NC NG BO; do
  export STATE_DIR=state_s2_$k LOG_DIR=logs_s2_$k CONFIG=config_s2_$k.json INBOX_DIR=inbox_s2_$k
  mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
  [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null && { echo "S2-$k 已在运行"; continue; }
  nohup ./venv/bin/python main.py --time-scale 1e9 > logs_s2_${k}_console.out 2>&1 &
  echo $! > "$STATE_DIR/pid"
  nohup caffeinate -i -w $(cat "$STATE_DIR/pid") >/dev/null 2>&1 &
  echo "S2-$k 已启动（PID $(cat $STATE_DIR/pid)）"
done
