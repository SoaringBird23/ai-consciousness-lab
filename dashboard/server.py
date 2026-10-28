#!/usr/bin/env python3
"""ACL Console — 只读实验监控面板（纯 Python 标准库，零第三方依赖）

把 ai-consciousness-lab 的实验进度与候选体实时状态可视化。

特性
----
- 只读：全部为 GET 接口，不含任何写操作，绝不会影响正在运行的实验。
- 零依赖：仅用 http.server / json / subprocess / shutil 等标准库。
- 自动发现：扫描 state* 目录、experiments/ 产物与 chain_*.log，无需配置。
- 健壮：任一数据源读取失败只让对应字段为空，不使整个面板报错。

启动
----
    python3 dashboard/server.py                 # http://127.0.0.1:8787
    python3 dashboard/server.py --port 9000     # 改端口
    python3 dashboard/server.py --host 0.0.0.0  # 供局域网访问（默认仅本机）

安全
----
默认绑定 127.0.0.1；所有文件参数走白名单并拒绝路径穿越。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

DASH_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DASH_DIR)
STATIC = os.path.join(DASH_DIR, "static")

TICK_WINDOW = 240          # 实时 series 采样点上限
DEFAULT_LOG_LINES = 200

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

LOG_RE = re.compile(r"^[A-Za-z0-9_.-]+\.log$")     # 日志文件名白名单
CONSOLE_RE = re.compile(r"^[A-Za-z0-9_.-]+\.out$")


# ----------------------------------------------------------------------------- 基础工具
def tail_lines(path, n=200, block=8192):
    """从文件尾部倒读最后 n 行（不整读大文件）。"""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        data = b""
        while size > 0 and data.count(b"\n") <= n:
            step = min(block, size)
            size -= step
            f.seek(size)
            data = f.read(step) + data
        lines = data.decode("utf-8", "replace").splitlines()
        return lines[-n:]


def head_lines(path, n=1):
    """读文件开头 n 行（用于取 fork 起点）。"""
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as f:
        for _ in range(n):
            line = f.readline()
            if not line:
                break
            out.append(line.rstrip("\n"))
    return out


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def parse_jsonl(lines):
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


# ----------------------------------------------------------------------------- 主机 / 进程
def host_info():
    try:
        load = list(os.getloadavg())
    except Exception:
        load = [0.0, 0.0, 0.0]
    try:
        free = shutil.disk_usage(ROOT).free / (1024 ** 3)
    except Exception:
        free = None
    return {"load": [round(x, 2) for x in load],
            "disk_free_gb": None if free is None else round(free, 1),
            "thermal": thermal_info()}


def thermal_info():
    try:
        out = subprocess.run(["pmset", "-g", "therm"], capture_output=True,
                             text=True, timeout=3).stdout
    except Exception:
        return {"status": "unknown", "detail": ""}
    sp = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", out)
    sc = re.search(r"CPU_Scheduler_Limit\s*=\s*(\d+)", out)
    hot = False
    det = []
    if sp:
        det.append("speed %s" % sp.group(1))
        hot = hot or int(sp.group(1)) < 95
    if sc:
        det.append("sched %s" % sc.group(1))
        hot = hot or int(sc.group(1)) < 100
    return {"status": "throttled" if hot else "ok",
            "detail": ", ".join(det) if det else "cool"}


def is_running(state_dir):
    p = os.path.join(ROOT, state_dir, "pid")
    if not os.path.exists(p):
        return False
    try:
        pid = int(open(p).read().strip())
    except Exception:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------------- 实验发现
def list_state_dirs():
    out = []
    for name in os.listdir(ROOT):
        full = os.path.join(ROOT, name)
        if not os.path.isdir(full):
            continue
        if name == "state" or name.startswith("state_"):
            out.append(name)
    return sorted(out)


def split_state_dir(name):
    """state_P14b_full -> ('P14b','full')；state -> ('main',''); state_exp -> ('exp','')。"""
    if name == "state":
        return "main", ""
    if name == "state_exp":
        return "exp", ""
    core = name[len("state_"):]
    parts = core.split("_", 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def list_logs():
    out = []
    for name in os.listdir(ROOT):
        if LOG_RE.match(name) or CONSOLE_RE.match(name):
            out.append(name)
    return sorted(out)


def find_log(exp):
    """为该实验找最合适的 chain 日志。"""
    cands = [n for n in list_logs()
             if n.startswith("chain_") and exp.lower() in n.lower()]
    if not cands:
        return None
    cands.sort(key=lambda n: (n.lower() != ("chain_%s.log" % exp).lower(), len(n)))
    return cands[0]


def log_target(logname):
    if not logname:
        return None
    p = os.path.join(ROOT, logname)
    txt = "\n".join(tail_lines(p, 400))
    m = re.search(r"TGT\s*=\s*(\d+)", txt)
    return int(m.group(1)) if m else None


def log_done(logname):
    if not logname:
        return False
    p = os.path.join(ROOT, logname)
    return "全部完成" in "\n".join(tail_lines(p, 60))


def traj_path(state_dir):
    return os.path.join(ROOT, state_dir, "trajectory.jsonl")


def arm_progress(state_dir, target):
    """读末行 day + 首行 day（fork 起点），算进度。"""
    last = parse_jsonl(tail_lines(traj_path(state_dir), 1))
    first = parse_jsonl(head_lines(traj_path(state_dir), 1))
    day = last[-1].get("day") if last else None
    start = first[0].get("day") if first else None
    pct = None
    if day is not None and target and start is not None and target > start:
        pct = max(0.0, min(1.0, (day - start) / (target - start)))
    return {"day": day, "start_day": start, "pct": None if pct is None else round(pct, 4),
            "sim_hour": (last[-1].get("sim_hour") if last else None)}


def expr_glob(exp, kind):
    """在 experiments/ 下找该实验的产物（results_*.json / prereg_*.json）。"""
    d = os.path.join(ROOT, "experiments")
    if not os.path.isdir(d):
        return None
    hits = [n for n in os.listdir(d)
            if n.startswith(kind) and n.endswith(".json") and exp.lower() in n.lower()
            and "tmp" not in n and "smoke" not in n]
    hits.sort(key=len)
    return os.path.join(d, hits[0]) if hits else None


def build_overview():
    groups = {}
    for d in list_state_dirs():
        exp, arm = split_state_dir(d)
        groups.setdefault(exp, []).append({"dir": d, "arm": arm})

    experiments = []
    for exp, arms in groups.items():
        log = find_log(exp)
        target = log_target(log)
        done = log_done(log)
        arm_rows = []
        for a in sorted(arms, key=lambda x: x["arm"]):
            prog = arm_progress(a["dir"], target)
            running = is_running(a["dir"])
            # 单臂进度：无 target 时用 1.0（不显示进度条）
            arm_rows.append({
                "dir": a["dir"], "arm": a["arm"] or "—",
                "day": prog["day"], "start_day": prog["start_day"],
                "pct": prog["pct"], "sim_hour": prog["sim_hour"],
                "running": running,
            })
        running_any = any(r["running"] for r in arm_rows)
        results = read_json(expr_glob(exp, "results_")) if expr_glob(exp, "results_") else None
        prereg = read_json(expr_glob(exp, "prereg_")) if expr_glob(exp, "prereg_") else None
        mtimes = [os.path.getmtime(traj_path(a["dir"]))
                  for a in arms if os.path.exists(traj_path(a["dir"]))]
        experiments.append({
            "id": exp, "target": target, "log": log,
            "status": "running" if running_any else ("done" if done else "idle"),
            "arms": arm_rows,
            "verdicts": (results or {}).get("verdicts") if isinstance(results, dict) else None,
            "results": results if isinstance(results, dict) else None,
            "has_results": bool(results),
            "has_prereg": bool(prereg),
            "prereg_title": (prereg or {}).get("experiment") if isinstance(prereg, dict) else None,
            "updated": max(mtimes) if mtimes else None,
        })

    # 推荐排序：正在运行 > 有结果 > 其余；组内按目标大小
    def sort_key(e):
        return (0 if e["status"] == "running" else 1 if e["results"] else 2, e["id"])
    experiments.sort(key=sort_key)

    live_states = list_state_dirs()
    return {"now": time.time(), "host": host_info(),
            "experiments": experiments, "live_states": live_states}


def build_live(state_dir):
    if state_dir not in list_state_dirs():
        return {"error": "unknown state"}
    traj = tail_lines(traj_path(state_dir), TICK_WINDOW)
    pts = parse_jsonl(traj)
    series = []
    for p in pts:
        series.append({
            "t": p.get("sim_time"), "day": p.get("day"),
            "s": [p.get("s%d" % i) for i in range(1, 9)],
        })
    last = pts[-1] if pts else {}
    return {
        "state": state_dir,
        "last": last,
        "series": series,
        "background": read_json(os.path.join(ROOT, state_dir, "background_state.json")),
        "energy": read_json(os.path.join(ROOT, state_dir, "energy.json")),
        "stage": read_json(os.path.join(ROOT, state_dir, "stage.json")),
        "self_model": read_json(os.path.join(ROOT, state_dir, "self_model.json")),
    }


def build_streams(state_dir, n=60):
    if state_dir not in list_state_dirs():
        return {"error": "unknown state"}
    d = os.path.join(ROOT, state_dir)
    inner = parse_jsonl(tail_lines(os.path.join(d, "inner_speech.jsonl"), n))
    voc = parse_jsonl(tail_lines(os.path.join(d, "vocalizations.jsonl"), n))
    return {"state": state_dir, "inner_speech": inner[-n:], "vocalizations": voc[-n:]}


def build_log(logname, n=DEFAULT_LOG_LINES):
    if not logname or "/" in logname or ".." in logname:
        return {"error": "bad file"}
    if not (LOG_RE.match(logname) or CONSOLE_RE.match(logname)):
        return {"error": "not allowed"}
    lines = tail_lines(os.path.join(ROOT, logname), n)
    return {"file": logname, "lines": lines}


# ----------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "ACLConsole/1.0"

    def log_message(self, *args):
        pass  # 静音访问日志

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj):
        self._send(200, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        try:
            u = urlparse(self.path)
            path, q = u.path, parse_qs(u.query)
            if path.startswith("/api/"):
                return self._api(path, q)
            return self._static(path)
        except Exception as e:                      # 任何异常都不让面板挂
            self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False))

    def _api(self, path, q):
        def one(k, d=None):
            v = q.get(k)
            return v[0] if v else d
        if path == "/api/health":
            return self._json({"ok": True, "root": ROOT})
        if path == "/api/overview":
            return self._json(build_overview())
        if path == "/api/live":
            return self._json(build_live(one("state", "state")))
        if path == "/api/streams":
            return self._json(build_streams(one("state", "state"), int(one("n", 60))))
        if path == "/api/logs":
            if one("file"):
                return self._json(build_log(one("file"), int(one("n", DEFAULT_LOG_LINES))))
            return self._json({"files": list_logs()})
        return self._send(404, json.dumps({"error": "not found"}))

    def _static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        rel = path.lstrip("/")
        if ".." in rel:
            return self._send(403, "forbidden")
        full = os.path.join(STATIC, rel)
        if not os.path.isfile(full):
            return self._send(404, "not found")
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))


def main():
    ap = argparse.ArgumentParser(description="ACL Console（只读监控面板）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("ACL Console  ->  http://%s:%d" % (args.host, args.port))
    print("项目根目录   ->  %s" % ROOT)
    print("只读模式；Ctrl+C 退出。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
