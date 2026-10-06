#!/bin/bash
# P0 启动脚本
cd "$(dirname "$0")"
mkdir -p state logs evolution_history inbox
exec ./venv/bin/python main.py
