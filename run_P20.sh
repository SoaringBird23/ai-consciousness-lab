#!/bin/bash
# run_P20.sh — P20 构造语法会话（发育版）
#
# 与 P19b 的唯一差别：
#   1) caregiver.corpus_vocab_cap=1200（解除 250 型输入瓶颈，接近完整照护者语料）
#   2) construction.enabled=true（听到即学句式；发声时对最近一轮“听懂→重组回答”）
# 其余参数沿用 config_P19b_full。
#
# 默认等 P19b 三臂跑到 P20_SRC_TGT（默认 315）且主进程退出后再 fork；
# 想立刻从当前状态分叉：P20_NOW=1 ./run_P20.sh
cd "$(dirname "$0")"
SRC=${P20_SRC:-state_P19b_full}
DST=${P20_STATE:-state_p20_run}
TGT=${P20_SRC_TGT:-315}
day_of(){ tail -n1 "$1/trajectory.jsonl" 2>/dev/null | sed -n 's/.*"day": *\([0-9][0-9]*\).*/\1/p'; }

if [ "${P20_NOW:-0}" = "1" ] && pgrep -f "[m]ain.py --time-scale 1e9" >/dev/null 2>&1; then
  echo "P20_NOW=1 但仍有主进程在跑：先停止 P19b，或从稳定快照 fork（P20_SRC=state_exp）。"
  exit 1
fi

if [ "${P20_NOW:-0}" != "1" ]; then
  while :; do
    d=$(day_of "$SRC"); [ -z "$d" ] && d=0
    if [ "$d" -ge "$TGT" ] && ! pgrep -f "[m]ain.py --time-scale 1e9" >/dev/null 2>&1; then
      break
    fi
    echo "[$(date '+%F %T')] 等待 P19b 到 day ${TGT}（当前 ${d}）…"
    sleep 120
  done
fi

NEW=0
if [ ! -d "$DST" ]; then
  echo "[$(date '+%F %T')] fork $SRC -> $DST（day $(day_of "$SRC")）"
  cp -R "$SRC" "$DST"
  NEW=1
fi
./venv/bin/python - "$DST" "$NEW" <<'PY'
import json, os, sys
d, new = sys.argv[1], sys.argv[2] == "1"
files = ["pid"] + (["constructions.json"] if new else [])
for f in files:
    p = os.path.join(d, f)
    if os.path.exists(p):
        os.remove(p)
# 解除 P19b 的 200 型输入上限：P20 用 5000 型（vocab_growth=none）
lp = os.path.join(d, "language_state.json")
if os.path.exists(lp):
    with open(lp, encoding="utf-8") as f:
        st = json.load(f)
    st["corpus_vocab_cap"] = 5000
    st["cap_last_grow_day"] = -999
    st["type_n"] = {}
    with open(lp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
PY
mkdir -p logs_P20
if screen -ls 2>/dev/null | grep -q "p20_run"; then
  echo "P20 已在 screen 会话 p20_run 中运行"
  exit 0
fi
screen -dmS p20_run bash -c "cd '$PWD' && STATE_DIR='$DST' LOG_DIR=logs_P20 CONFIG=config_P20.json caffeinate -i ./venv/bin/python main.py --time-scale 1e9 >> logs_P20/console.out 2>&1"
sleep 2
echo "[$(date '+%F %T')] P20 启动：STATE_DIR=$DST CONFIG=config_P20.json"
screen -ls | grep p20_run || true
