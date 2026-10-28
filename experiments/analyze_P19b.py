"""analyze_P19b.py — P19b 习惯化 + 去回声

读取 state_P19b_{off,full,shuf}/dialogue_turns.jsonl（末 30 日窗口），统计：
  · 多样性：系统轮不同型占比、最高频句占比
  · 回声：系统轮 == 伙伴紧邻上一轮 的比例
  · 承接（仅非回声轮）：与伙伴紧邻上一轮共享 ≥1 词的比例
判据 H19b1–H19b4；落盘 experiments/results_P19b.json。
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 86400.0
OUT = os.path.join(ROOT, "experiments", "results_P19b.json")
ARMS = ["off", "full", "shuf"]
sys.path.insert(0, ROOT)
import dialogue as DL


def _seg(text, lexicon, maxlen):
    out, i, L = [], 0, len(text)
    while i < L:
        hit = None
        for ln in range(min(maxlen, L - i), 1, -1):
            if text[i:i + ln] in lexicon:
                hit = text[i:i + ln]; break
        if hit:
            out.append(hit); i += len(hit)
        else:
            out.append(text[i]); i += 1
    return out


def load_turns(arm):
    p = os.path.join(ROOT, f"state_P19b_{arm}", "dialogue_turns.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def analyze_arm(arm, t0, lexicon, maxlen):
    lo, hi = t0 + 30 * DAY, t0 + 60 * DAY
    turns = [r for r in load_turns(arm)
             if r.get("t") is not None and lo <= float(r["t"]) < hi]
    words = lambda s: _seg(s, lexicon, maxlen)

    last_partner = None
    self_texts, echo_flags, link_flags = [], [], []
    for r in turns:
        if r.get("speaker") == "self":
            t = r.get("text", "")
            self_texts.append(t)
            if last_partner is not None:
                is_echo = (t == last_partner)
                echo_flags.append(1 if is_echo else 0)
                ws, pw = set(words(t)), set(words(last_partner))
                link_flags.append((1 if (ws & pw) else 0, 1 if is_echo else 0))
        else:
            last_partner = r.get("text", "")
    n_self = len(self_texts)
    cnt = collections.Counter(self_texts)
    distinct = len(cnt) / n_self if n_self else None
    top_share = (max(cnt.values()) / n_self) if n_self else None
    echo_rate = (sum(echo_flags) / len(echo_flags)) if echo_flags else None
    non_echo = [lk for lk, ez in link_flags if ez == 0]
    linked_non_echo = (sum(non_echo) / len(non_echo)) if non_echo else None
    linked_all = (sum(lk for lk, _ in link_flags) / len(link_flags)) if link_flags else None
    return {
        "arm": arm, "n_turns": len(turns), "n_self": n_self,
        "n_partner": sum(1 for r in turns if r.get("speaker") != "self"),
        "distinct_rate": round(distinct, 4) if distinct is not None else None,
        "top_share": round(top_share, 4) if top_share is not None else None,
        "exact_echo_rate": round(echo_rate, 4) if echo_rate is not None else None,
        "linked_non_echo": round(linked_non_echo, 4) if linked_non_echo is not None else None,
        "linked_all": round(linked_all, 4) if linked_all is not None else None,
        "top5": cnt.most_common(5),
    }


def main():
    t0 = 22002086.380798087
    p14 = os.path.join(ROOT, "experiments", "results_P14c.json")
    if os.path.exists(p14):
        try:
            t0 = float(json.load(open(p14)).get("fork_sim_time", t0))
        except Exception:
            pass
    lexicon, maxlen = DL.load_words(os.path.join(ROOT, "corpus", "lexicon.json"))
    print(f"fork t0={t0}（day {t0/DAY:.2f}）；窗口=末30日；词表={len(lexicon)}")
    print("=" * 104)
    res = {"fork_sim_time": t0, "arms": {}}
    for a in ARMS:
        m = analyze_arm(a, t0, lexicon, maxlen)
        res["arms"][a] = m
        print(f"  {a:5s} self={m['n_self']:4d} distinct={m['distinct_rate']} "
              f"top_share={m['top_share']} echo={m['exact_echo_rate']} "
              f"linked(non-echo/all)={m['linked_non_echo']}/{m['linked_all']}")
        print(f"        最高频: {m['top5']}")
    print("=" * 104)
    off, full, shuf = res["arms"]["off"], res["arms"]["full"], res["arms"]["shuf"]

    def ok(x):
        return x is not None

    v = {}
    v["H19b1_多样性(full distinct >= off+0.10)"] = {
        "pass": bool(ok(full["distinct_rate"]) and ok(off["distinct_rate"])
                     and full["distinct_rate"] >= off["distinct_rate"] + 0.10),
        "detail": f"full={full['distinct_rate']} off={off['distinct_rate']}"}
    v["H19b2_去回声(full echo <= off-0.05)"] = {
        "pass": bool(ok(full["exact_echo_rate"]) and ok(off["exact_echo_rate"])
                     and full["exact_echo_rate"] <= off["exact_echo_rate"] - 0.05),
        "detail": f"full={full['exact_echo_rate']} off={off['exact_echo_rate']}"}
    v["H19b3_承接保持(非回声轮 full >= off-0.05)"] = {
        "pass": bool(ok(full["linked_non_echo"]) and ok(off["linked_non_echo"])
                     and full["linked_non_echo"] >= off["linked_non_echo"] - 0.05),
        "detail": f"full={full['linked_non_echo']} off={off['linked_non_echo']}"}
    v["H19b4_对照分层(full distinct > shuf)"] = {
        "pass": bool(ok(full["distinct_rate"]) and ok(shuf["distinct_rate"])
                     and full["distinct_rate"] > shuf["distinct_rate"]),
        "detail": f"full={full['distinct_rate']} shuf={shuf['distinct_rate']}"}
    res["verdicts"] = v
    res["note"] = ("承接按词重叠（共现层代理）；H19b3 只看**非回声**轮，"
                   "用于确认多样性不是靠破坏承接换来的。")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("落盘：", OUT)
    for k, d in v.items():
        print(f"  [{'PASS' if d['pass'] else 'FAIL'}] {k} — {d['detail']}")


if __name__ == "__main__":
    main()
