#!/bin/bash
# 加速副线（方案 B）：time-scale 1e9，状态/日志隔离，不碰主线
# 用途：快速预演 P0/P1 时长的仿真动力学，验证代码与涌现路径
# 注意：此线昼夜与现实脱钩、inbox 失效，数据仅作动力学验证，不进正式报告
cd "$(dirname "$0")"
export STATE_DIR=state_accel
export LOG_DIR=logs_accel
export CONFIG=config_accel.json
mkdir -p "$STATE_DIR" "$LOG_DIR"
exec ./venv/bin/python main.py --time-scale 1e9
