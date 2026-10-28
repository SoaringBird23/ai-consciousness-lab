#!/usr/bin/env python3
"""experiments/analyze_P20.py — P20 live 统计

读 state_p20_run（或 --state-dir）的 inner_speech.jsonl，统计：
  - 念头类型分布（retrieval / echo / construction）
  - construction 的模式分布（question_template / followup / paraphrase / ...）
  - construction 的“话题接住率”：回答与 reply_to 的实词重叠
  - 词法纯净率：回答每个词是否在构造语法的实听词表里
  - 每日 construction 占 retrieval 的比例
输出 experiments/results_P20_live.json。
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import constructions as C  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default=os.path.join(ROOT, "state_p20_run"))
    ap.add_argument("--out", default=os.path.join(ROOT, "experiments",
                                                  "results_P20_live.json"))
    args = ap.parse_args()
    st = args.state_dir
    inner = os.path.join(st, "inner_speech.jsonl")
    if not os.path.exists(inner):
        print(f"没有 {inner}")
        return 1
    g = None
    gp = os.path.join(st, "constructions.json")
    if os.path.exists(gp):
        g = C.ConstructionGrammar.load(gp)
    types, modes = Counter(), Counter()
    day_ret, day_con = defaultdict(int), defaultdict(int)
    con_n = con_topic = con_pure = 0
    examples = []
    with open(inner, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = str(r.get("type", ""))
            types[t] += 1
            day = int(float(r.get("t", 0)) // 86400)
            if t == "retrieval":
                day_ret[day] += 1
            if t != "construction":
                continue
            day_con[day] += 1
            con_n += 1
            mode = r.get("construction_mode", "?")
            modes[mode] += 1
            # 话题接住率（用切词后的实词集合）
            src = r.get("reply_to", "")
            # 用朴素字符集合近似；有 grammar 时用其切词
            if g is not None:
                a = {w for w in g.tok.segment(r.get("text", ""))
                     if w not in C.FUNCTION_WORDS}
                b = {w for w in g.tok.segment(src) if w not in C.FUNCTION_WORDS}
                pure = all(w in g.word_count for w in g.tok.segment(r.get("text", "")))
            else:
                a = set(r.get("text", ""))
                b = set(src)
                pure = None
            if a & b:
                con_topic += 1
            if pure is not None:
                con_pure += int(pure)
            if len(examples) < 20:
                examples.append({"t": r.get("t"), "reply_to": src,
                                 "text": r.get("text"), "mode": mode})
    days = sorted(set(day_ret) | set(day_con))
    series = [{"day": d, "retrieval": day_ret[d], "construction": day_con[d],
               "construction_share": (day_con[d] / max(1, day_ret[d] + day_con[d]))}
              for d in days]
    out = {
        "state_dir": st,
        "types": dict(types),
        "construction": {
            "n": con_n,
            "topic_overlap": con_topic / max(1, con_n),
            "purity": (con_pure / con_n) if g is not None else None,
            "modes": dict(modes),
        },
        "per_day": series,
        "examples": examples,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("per_day", "examples")}, ensure_ascii=False, indent=2))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
