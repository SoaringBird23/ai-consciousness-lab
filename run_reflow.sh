#!/bin/bash
# R 回流量级阶梯：3 档 × 消融/对照 = 6 条，fork 自成熟线 state_exp（SIGSTOP 安全复制）
cd "$(dirname "$0")"
for lv in lo mid hi; do
 for arm in abl ctl; do
  export STATE_DIR=state_R_${lv}_${arm} LOG_DIR=logs_R_${lv}_${arm} \
         CONFIG=config_R_${lv}_${arm}.json INBOX_DIR=inbox_R_${lv}_${arm}
  if [ -f "$STATE_DIR/pid" ] && kill -0 $(cat "$STATE_DIR/pid") 2>/dev/null; then
    echo "R-$lv-$arm 已在运行"; continue
  fi
  if [ ! -f "$STATE_DIR/stage.json" ]; then
    rm -rf "$STATE_DIR"; cp -R state_exp "$STATE_DIR"
    rm -f "$STATE_DIR/pid" "$STATE_DIR/e6_state.json"
    echo "R-$lv-$arm 已从 state_exp fork"
  fi
  mkdir -p "$LOG_DIR" "$INBOX_DIR"
  nohup ./venv/bin/python main.py --time-scale 1e9 > logs_R_${lv}_${arm}_console.out 2>&1 &
  echo $! > "$STATE_DIR/pid"
  nohup caffeinate -i -w $(cat "$STATE_DIR/pid") >/dev/null 2>&1 &
  echo "R-$lv-$arm 已启动（PID $(cat $STATE_DIR/pid)）"
 done
done
