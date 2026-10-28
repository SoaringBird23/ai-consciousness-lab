"""analyze_P19.py — P19 多轮对话

读取 state_P19_{off,full,shuf}/dialogue_turns.jsonl（末 30 日窗口），
以「词重叠」为对话承接的可实现代理，统计：
  · 轮次承重：系统轮 ⊇ 紧邻上一轮伙伴词 的比例
  · 多轮承接：系统轮与对方近 3 轮有重叠的连续链（≥3）
  · 非退化：系统轮不同型占比
判据 H19a–H19d；落盘 experiments/results_P19.json。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 86400.0
T0_DEFAULT = 22002086.380798087
OUT = os.path.join(ROOT, "experiments", "results_P19.json")
ARMS = ["off", "full", "shuf"]
sys.path.insert(0, ROOT)
import dialogue as DL


def load_turns(arm):
    p = os.path.join(ROOT, f"state_P19_{arm}", "dialogue_turns.jsonl")
    out = []
    if not os.path.exists(p):
        return out
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
    rows = [r for r in load_turns(arm) if r.get("t") is not None]
    lo, hi = t0 + 30 * DAY, t0 + 60 * DAY
    turns = [r for r in rows if lo <= float(r["t"]) < hi]

    def words(text):
        return _seg(text, lexicon, maxlen)

    # 顺序处理：为每个 self 轮找紧邻的上一 partner 轮 & 近 3 个 partner 轮
    last_partner = None
    partner_hist = []           # 最近 3 个 partner 轮的词集
    contain_all = []            # 含所有词
    contain_multi = []          # 仅多字词
    linked = []                 # 承接（近 3 轮有重叠）
    self_texts = []
    for r in turns:
        if r.get("speaker") == "self":
            self_texts.append(r.get("text", ""))
            ws = words(r.get("text", ""))
            ws_multi = [w for w in ws if len(w) >= 2]
            # 紧邻上一 partner
            if last_partner is not None:
                pw = words(last_partner)
                shared = set(ws) & set(pw)
                contain_all.append(len(shared) / len(ws) if ws else 0.0)
                pwm = set(w for w in pw if len(w) >= 2)
                contain_multi.append(len(set(ws_multi) & pwm) / len(ws_multi) if ws_multi else 0.0)
            else:
                contain_all.append(0.0); contain_multi.append(0.0)
            # 近 3 轮伙伴并集
            union = set()
            for ph in partner_hist:
                union |= set(words(ph))
            linked.append(1 if (set(ws) & union) else 0)
        else:
            last_partner = r.get("text", "")
            partner_hist.append(r.get("text", ""))
            partner_hist = partner_hist[-3:]
    n_self = len(self_texts)
    # 连续承接链（≥3）
    best = 0; cur = 0; chains3 = 0
    for v in linked:
        cur = cur + 1 if v else 0
        if cur > best:
            best = cur
        if cur == 3:
            chains3 += 1
    return {
        "arm": arm, "n_turns": len(turns), "n_self": n_self,
        "n_partner": sum(1 for r in turns if r.get("speaker") != "self"),
        "contain_all_mean": round(sum(contain_all) / len(contain_all), 4) if contain_all else None,
        "contain_multi_mean": round(sum(contain_multi) / len(contain_multi), 4) if contain_multi else None,
        "linked_rate": round(sum(linked) / len(linked), 4) if linked else None,
        "max_chain": best, "chains_ge3": chains3,
        "distinct_self_rate": round(len(set(self_texts)) / n_self, 4) if n_self else None,
    }


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


def main():
    t0 = 22002086.380798087
    p14 = os.path.join(ROOT, "experiments", "results_P14c.json")
    if os.path.exists(p14):
        try:
            t0 = float(json.load(open(p14)).get("fork_sim_time", t0))
        except Exception:
            pass
    lexicon, maxlen = DL.load_words(os.path.join(ROOT, "corpus", "lexicon.json"))
    print(f"fork t0={t0}（day {t0/DAY:.2f}）；判据窗口=末30日；词表={len(lexicon)}")
    print("=" * 96)
    res = {"fork_sim_time": t0, "arms": {}}
    for a in ARMS:
        res["arms"][a] = analyze_arm(a, t0, lexicon, maxlen)
        m = res["arms"][a]
        print(f"  {a:5s} turns={m['n_turns']:5d} self={m['n_self']:4d} "
              f"linked={m['linked_rate']} contain(all/multi)={m['contain_all_mean']}/{m['contain_multi_mean']} "
              f"maxchain={m['max_chain']} chains>=3={m['chains_ge3']} distinct={m['distinct_self_rate']}")
    print("=" * 96)
    off, full, shuf = res["arms"]["off"], res["arms"]["full"], res["arms"]["shuf"]

    def ok(x):
        return x is not None
    v = {}
    v["H19a_轮次承重(full-linked >= shuf+0.10)"] = {
        "pass": bool(ok(full["linked_rate"]) and ok(shuf["linked_rate"])
                     and full["linked_rate"] >= shuf["linked_rate"] + 0.10),
        "detail": f"full={full['linked_rate']} shuf={shuf['linked_rate']}"}
    v["H19b_多轮承接(full 链>=3 数 > shuf)"] = {
        "pass": bool(full["chains_ge3"] > shuf["chains_ge3"]),
        "detail": f"full={full['chains_ge3']} shuf={shuf['chains_ge3']}"}
    v["H19c_非退化(full distinct>=off-0.05)"] = {
        "pass": bool(ok(full["distinct_self_rate"]) and ok(off["distinct_self_rate"])
                     and full["distinct_self_rate"] >= off["distinct_self_rate"] - 0.05),
        "detail": f"full={full['distinct_self_rate']} off={off['distinct_self_rate']}"}
    v["H19d_优于off(full-linked >= off)"] = {
        "pass": bool(ok(full["linked_rate"]) and ok(off["linked_rate"])
                     and full["linked_rate"] >= off["linked_rate"]),
        "detail": f"full={full['linked_rate']} off={off['linked_rate']}"}
    res["verdicts"] = v
    res["note"] = ("以词重叠为对话承接的可实现代理（共现层，非语义理解）；"
                   "shuffle 为内容对照（D 幅值不变、轮↔词关联打断）。")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("落盘：", OUT)
    for k, d in v.items():
        print(f"  [{'PASS' if d['pass'] else 'FAIL'}] {k} — {d['detail']}")


if __name__ == "__main__":
    main()
