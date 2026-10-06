#!/bin/bash
# P3 试点线：从加速线 fork 状态，以 1× 实时运行。
# 照护者 = 真实用户（inbox_p3/say_*.txt，用 talk.py 输入）。
# 注意：STOP 文件是全局共享的——停本线请用 pkill -f 'main\.py --time-scale 1$'
cd "$(dirname "$0")"

# ---- 首次启动：fork 加速线状态（冻结→复制→校验，防撕裂） ----
if [ ! -d state_p3 ]; then
  echo "首次启动：fork state_accel → state_p3 ..."
  ACCEL_PID=$(pgrep -f "main.py --time-scale 1e9")
  if [ -n "$ACCEL_PID" ]; then kill -STOP $ACCEL_PID; sleep 1; fi
  cp -R state_accel state_p3
  if [ -n "$ACCEL_PID" ]; then kill -CONT $ACCEL_PID; fi
  # 校验所有 JSON 完整（撕裂则删除重来）
  if ! ./venv/bin/python - <<'PYEOF'
import json, os, sys, re
ok = True
for fn in os.listdir("state_p3"):
    if fn.endswith(".json"):
        try:
            json.load(open(os.path.join("state_p3", fn)))
        except Exception as e:
            print("损坏:", fn, e); ok = False
if not ok: sys.exit(1)
line = open("logs_accel/main.log").readlines()[-1]
m = re.search(r"day (\d+) h([\d.]+)", line)
json.dump({"forked_from": "state_accel",
           "sim_day": int(m.group(1)) + float(m.group(2)) / 24,
           "wall_time": __import__("time").strftime("%F %T"),
           "note": "P3 试点个体：与加速线在此分岔（共享此前全部历史）。正式 P3 个体将是主线。"},
          open("state_p3/fork.json", "w"), ensure_ascii=False, indent=2)
print("fork 完整，分支点已记录")
PYEOF
  then
    echo "!! fork 文件校验失败，删除 state_p3 重试"; rm -rf state_p3; exit 1
  fi
fi

export STATE_DIR=state_p3 LOG_DIR=logs_p3 CONFIG=config_p3.json INBOX_DIR=inbox_p3
mkdir -p "$STATE_DIR" "$LOG_DIR" "$INBOX_DIR"
echo "P3 试点线启动（1× 实时）。照护者台：./talk.py"
exec caffeinate -i ./venv/bin/python main.py --time-scale 1
