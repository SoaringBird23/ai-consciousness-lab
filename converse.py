#!/usr/bin/env python3
"""converse.py — P20 构造语法对话台

用法：
  ./venv/bin/python converse.py                      # 交互
  ./venv/bin/python converse.py --explain            # 每轮显示它怎么理解
  ./venv/bin/python converse.py --script "这是什么;苹果在哪里;乌龟在睡觉"
  ./venv/bin/python converse.py --model state_p20_run/constructions.json   # P20 跑起来后

它做什么：
  听 → 用听过的句式切分（construction + 槽位）→ 判断句子类型（问什么/是否问/陈述/祈使）
    → 问句：把疑问词挖掉，按槽位类别+上下文+状态填一个实听过的词
    → 陈述：接话变体 / 追问 / 句式重组
  输出里每个词都必须是它实听过的（word_count>0），句式也必须是实听过的。

它不做什么：
  没有对象世界，只有八维身体状态和一个标量场。能答对“句式”，不能保证答对“事实”。
  这不是聊天机器人，是一条仍在发育的语言线；语言输出只作现象记录，不作意识证据。
"""
import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from constructions import ConstructionGrammar, FUNCTION_WORDS  # noqa: E402

DEFAULT_MODEL = os.path.join(ROOT, "state_p20_models", "constructions_memory.json")
DEFAULT_STATE = os.path.join(ROOT, "state_P19b_full")


def load_state(state_dir):
    """读最近状态。主进程可能在写这个文件，读到半截就重试。"""
    import time
    path = os.path.join(state_dir, "linguistic_memory.json")
    if not os.path.exists(path):
        return [0.5] * 8, 0.5, None
    for _ in range(12):
        try:
            with open(path, encoding="utf-8") as f:
                mem = json.load(f)
            if mem:
                last = mem[-1]
                return (last.get("s", [0.5] * 8), last.get("world", 0.5),
                        last.get("t"))
        except (json.JSONDecodeError, OSError):
            pass
        time.sleep(0.25)
    return [0.5] * 8, 0.5, None


def load_interoception(state_dir):
    """读当前身体状态；主进程可能正在写文件，读到半截就重试。"""
    import time
    out = {}
    for f in ("energy.json", "background_state.json", "affect.json"):
        path = os.path.join(state_dir, f)
        for _ in range(6):
            try:
                with open(path, encoding="utf-8") as fh:
                    out[f] = json.load(fh)
                break
            except (json.JSONDecodeError, OSError):
                time.sleep(0.2)
    en = out.get("energy.json", {})
    bg = out.get("background_state.json", {})
    af = out.get("affect.json", {})
    return {
        "energy": float(en.get("fraction", en.get("level", 50.0) / 100.0)),
        "sleep": float(bg.get("sleep_pressure", 0.0)),
        "asleep": bool(bg.get("asleep", False)),
        "distress": float(af.get("distress", 0.0)),
        "ease": float(af.get("ease", 0.0)),
    }


def interoception_reply(text, st):
    """实验者接上的内感受探针：直接读能量/睡眠压力/情绪，再回答。

    这不是系统自己长出的能力；它用于给“自我报告是否可能随身体状态变化”
    提供一个校准参照。没有这个开关时，构造语法会给出与状态无关的立场回声。
    """
    t = text.strip()
    if any(k in t for k in ("饿不饿", "饿吗")):
        return "我饿" if st["energy"] < 0.35 else "我不饿"
    if any(k in t for k in ("困不困", "困吗")):
        return "我困" if st["sleep"] > 0.75 else "我不困"
    if any(k in t for k in ("累不累", "累吗")):
        return "我累" if (st["energy"] < 0.40 or st["sleep"] > 0.80) else "我不累"
    if "害怕" in t or "怕不怕" in t:
        return "我害怕" if st["distress"] > 0.50 else "我不害怕"
    if "开心" in t or "高兴" in t:
        return "我开心" if st["ease"] > 0.50 else "我不开心"
    return None


def fmt_frame(frame):
    return "".join("＿" if w == "_" else w for w in frame)


def show_understanding(g, und, gen):
    parts = []
    for it in und["constructions"]:
        parts.append(f"{fmt_frame(it['frame'])}（{it['filler']}）")
    print(f"  └ 听懂：{und['speech_act']}　句式：{' + '.join(parts) if parts else '未匹配'}"
          f"　话题：{'/'.join(und['topics'][:4]) or '—'}　结构覆盖：{und['coverage']:.0%}")
    if gen:
        mode = {"wh_template": "问句模板+槽位替换", "why_because": "因为句式",
                "yesno_echo": "是非问：换人称+应答词", "paraphrase": "接话变体",
                "followup": "追问", "frame": "句式重组", "greeting": "问候",
                "imperative": "应承", "backchannel": "应答", "stitch": "句式拼接"}
        pure = all(w in g.word_count for w in gen.get("tokens", []))
        print(f"  └ 说法：{mode.get(gen.get('answer_mode'), gen.get('answer_mode'))}"
              f"　每个词都听过：{'是' if pure else '否'}")


def punctuate(text, mode):
    if not text:
        return text
    if mode in ("followup",):
        return text + "？"
    if mode in ("wh_template", "why_because", "yesno_echo"):
        return text + "。"
    return text + "。"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--state-dir", default=DEFAULT_STATE)
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--script", default=None)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--interoception", action="store_true",
                    help="启用实验者内感受探针：自我报告直接读 energy/sleep/affect")
    args = ap.parse_args()

    if not os.path.exists(args.model):
        print(f"找不到模型：{args.model}\n先运行：\n"
              f"  ./venv/bin/python tools/build_constructions.py --no-holdout "
              f"--out {args.model}")
        return 1
    g = ConstructionGrammar.load(args.model)
    state, world, last_t = load_state(args.state_dir)
    rng = random.Random(args.seed)
    recent, avoid = [], []

    print(f"构造语法模型：{len(g.frames)} 个句式 / {len(g.word_count)} 个听过词　"
          f"（状态来自 {os.path.basename(args.state_dir)}）")
    print("输入 /quit 退出；/explain 切换解释；/state 看状态。\n")

    def turn(text):
        if args.interoception:
            st = load_interoception(args.state_dir)
            msg = interoception_reply(text, st)
            if msg is not None:
                print(f"你> {text}")
                if args.explain:
                    print(f"  └ 内感受探针：energy={st['energy']:.2f} "
                          f"sleep={st['sleep']:.2f} distress={st['distress']:.2f} "
                          f"ease={st['ease']:.2f}")
                    print("  └ 说法：自我报告（实验者内感受探针，不是涌现能力）")
                print(f"它> {msg}。\n")
                return
        und, gen = g.respond(text, state=state, world=world,
                             recent_topics=recent[-6:], rng=rng, avoid=avoid)
        print(f"你> {text}")
        if args.explain:
            show_understanding(g, und, gen)
        if gen is None:
            print("它> （没有回应）\n")
            return
        out = punctuate(gen["text"], gen.get("answer_mode"))
        print(f"它> {out}\n")
        # 对话状态：话题衰减 + 避免连续复读
        for w in und.get("topics", []):
            if w not in FUNCTION_WORDS and w not in recent:
                recent.append(w)
        del recent[:-12]
        avoid.append(gen["text"])
        del avoid[:-6]

    if args.script:
        for line in args.script.split(";"):
            line = line.strip()
            if line:
                turn(line)
        return 0

    while True:
        try:
            text = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text in ("/quit", "/exit", "quit", "exit"):
            break
        if text == "/explain":
            args.explain = not args.explain
            print(f"解释：{'开' if args.explain else '关'}\n")
            continue
        if text == "/state":
            print(f"s1..s8={state}\nworld={world}\n最近话题={recent[-6:]}\n")
            continue
        turn(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
