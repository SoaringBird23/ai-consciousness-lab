#!/usr/bin/env python3
"""talk.py — 照护者台（P3 试点线）
与候选体实时对话的终端控制台。

你说的话        → inbox_p3/say_*.txt → 它 hear()（带状态绑定入库）
它的出声/念头    → 实时显示在这里
它的状态        → 底部状态行（day/时刻/睡眠/能量）

提示：它只会短语（2-8 字）。像对婴儿说话：短句、重复、应它的状态说。
它睡着时听不见（每晚约 8 小时）。它不一定回应——它不是聊天机器人。

命令：/status 刷新状态 · /quit 退出
"""
import json
import os
import re
import select
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, os.environ.get("STATE_DIR", "state_p3"))
INBOX = os.path.join(ROOT, os.environ.get("INBOX_DIR", "inbox_p3"))
LOG = os.path.join(ROOT, os.environ.get("LOG_DIR", "logs_p3"), "main.log")
VOC = os.path.join(STATE, "vocalizations.jsonl")
INNER = os.path.join(STATE, "inner_speech.jsonl")

HB = re.compile(r"day (\d+) h([\d.]+) sleep=(\w+) s1=([\d.]+) s8=([\d.]+) "
                r"energy=(\d+)% self_ratio=([\d.]+) surprise=([\d.]+)")


def lines_after(path, pos):
    """返回 (新行列表, 新位置)。"""
    if not os.path.exists(path):
        return [], pos
    try:
        with open(path) as f:
            f.seek(pos)
            data = f.read()
            new_pos = f.tell()
    except OSError:
        return [], pos
    return [l for l in data.splitlines() if l.strip()], new_pos


def tail_bytes(path, n=4000):
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - n))
        return f.read().decode("utf-8", "ignore")


def last_status():
    txt = tail_bytes(LOG)
    m = None
    for m0 in HB.finditer(txt):
        m = m0
    if not m:
        return "（等待心跳…）"
    return "day %s %02d时 | %s | s1=%s s8=%s | 能量%s%% | 归因自身%s | 惊奇%s" % (
        m.group(1), float(m.group(2)),
        "睡眠中" if m.group(3) == "True" else "清醒",
        m.group(4), m.group(5), m.group(6), m.group(7), m.group(8))


def show(rec, kind):
    """kind: voc=出声 / echo=复述 / retr=检索"""
    t = rec.get("t", 0)
    d = int(t / 86400.0) + 1
    txt = rec.get("text", "?")
    if kind == "voc":
        tag = "它(出声)"
    elif kind == "echo":
        tag = "它(复述)"
    else:
        tag = "它(念头)"
        if rec.get("self_directed"):
            tag = "它(念头·我)"
    print("%-12s d%-4d %s" % (tag, d, txt))


def main():
    os.makedirs(INBOX, exist_ok=True)
    fork = {}
    try:
        with open(os.path.join(STATE, "fork.json")) as f:
            fork = json.load(f)
    except Exception:
        pass
    print("=" * 56)
    print("照护者台 · P3 试点线")
    if fork:
        print("个体来源: %s 的 day %.1f（%s 分岔）" % (
            fork.get("forked_from"), fork.get("sim_day", 0),
            str(fork.get("wall_time", ""))[:16]))
    print("说话直接输入回车；短句效果最好；它睡着时听不见。")
    print("=" * 56)
    # 开场：它最近的出声与念头
    for path, kind, n in ((VOC, "voc", 3), (INNER, "retr", 5)):
        try:
            with open(path) as f:
                recs = [json.loads(l) for l in f if l.strip()][-n:]
            for r in recs:
                k = kind if kind == "voc" else r.get("type", "retr")
                show(r, k)
        except Exception:
            pass
    print("-" * 56)
    print(last_status())
    print("-" * 56)

    pos_voc = os.path.getsize(VOC) if os.path.exists(VOC) else 0
    pos_inner = os.path.getsize(INNER) if os.path.exists(INNER) else 0
    last_status_t = time.time()

    while True:
        r, _, _ = select.select([sys.stdin], [], [], 1.0)
        if r:
            line = sys.stdin.readline().strip()
            if line in ("/quit", "/exit"):
                print("再见。它继续运行（停线: pkill -f 'main\\.py --time-scale 1$'）")
                break
            if line == "/status":
                print(last_status())
                continue
            if not line:
                continue
            fname = "say_%d.txt" % int(time.time() * 1000)
            try:
                with open(os.path.join(INBOX, fname), "w", encoding="utf-8") as f:
                    f.write(line[:60])
                print("%-12s      %s" % ("你", line))
            except OSError as e:
                print("!! 写入失败:", e)

        for path, pos, kind in ((VOC, pos_voc, "voc"), (INNER, pos_inner, "inner")):
            new, npos = lines_after(path, pos)
            for l in new:
                try:
                    rec = json.loads(l)
                except ValueError:
                    continue
                if kind == "voc":
                    show(rec, "voc")
                else:
                    show(rec, rec.get("type", "retr"))
            if kind == "voc":
                pos_voc = npos
            else:
                pos_inner = npos

        if time.time() - last_status_t > 30:
            print(last_status())
            last_status_t = time.time()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n再见。")
