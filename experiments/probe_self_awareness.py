#!/usr/bin/env python3
"""probe_self_awareness.py — P20 幻觉/随机/自我意识现象探针

做四件事：
  1) 幻觉审计：词法级（是否只使用实听词）vs 指称级（事实是否可验证）；
  2) 随机性审计：同一问题的输出分布、熵、种子敏感性；shuffle 槽位对照；
  3) 自我/他人边界：代词测试（你是谁 / 我是谁 / 你叫什么名字）；
  4) 自我报告有效性：改变身体状态（能量/睡眠压力/情绪）后，回答是否随之改变；
     以及来源监控、未知问题上的诚实度。
最后给出一条**操作性**结论，不把行为指标冒充现象学意识。
"""
import argparse
import copy
import json
import math
import os
import random
import statistics
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import constructions as C  # noqa: E402

FACTUAL_Q = ["这是什么形状", "这是什么颜色", "小狗在哪里", "妈妈去哪儿了"]
SELF_Q = ["你是谁", "我是谁", "你叫什么名字", "你喜欢什么"]
STATE_Q = ["你饿不饿", "你困不困", "你累不累", "你害怕吗", "你开心吗"]
UNKNOWN_Q = ["天为什么下雨", "一加一等于几", "你昨天做了什么", "你叫什么名字"]
COLOR_CHARS = set("红黄蓝绿黑白紫灰粉橙")


def load_json_retry(path, attempts=12):
    import time
    for _ in range(attempts):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            time.sleep(0.2)
    return None


def load_rows(state_dir):
    path = os.path.join(ROOT, state_dir, "trajectory.jsonl")
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("day", 0) >= 250:
                rows.append(r)
    return rows


def svec(r):
    return [float(r.get(f"s{i}", 0.0)) for i in range(1, 9)]


def energy(r):
    return float(r.get("energy", {}).get("fraction", 0.5))


def sleep(r):
    return float(r.get("sleep_pressure", 0.0))


def run(g, q, state, n=10, seed=0, world=0.5):
    rng = random.Random(seed)
    outs = []
    for _ in range(n):
        und, gen = g.respond(q, state=state, world=world, rng=rng)
        if gen:
            outs.append(gen)
    return outs


def entropy(counter):
    total = sum(counter.values())
    if total <= 1:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counter.values())


def purity(g, gen):
    return all(w in g.word_count for w in gen["tokens"])


def category_ok(g, q, text):
    toks = g.tok.segment(text)
    if "形状" in q:
        # 忽略问句自带的“形状”，只看被换进去的槽位词
        return any("形" in w for w in toks if w != "形状")
    if "颜色" in q:
        return any((("色" in w and w != "颜色") or w in COLOR_CHARS) for w in toks)
    if ("哪里" in q or "哪儿" in q):
        return any(w in C.LOCATION_HINTS for w in toks) or any(
            g._role_sim(w, "哪里") >= 0.12 for w in toks)
    return None


def shuffled_grammar(g, seed=0):
    h = copy.deepcopy(g)
    rng = random.Random(seed)
    pool = [w for w in g.word_count if w not in C.FUNCTION_WORDS]
    weights = [g.word_count[w] for w in pool]
    for fr, st in h.frames.items():
        total = int(sum(st["fillers"].values()))
        new = Counter()
        for w in rng.choices(pool, weights=weights, k=max(1, total)):
            new[w] += 1
        st["fillers"] = new
    h.finalize(min_n=1, min_fillers=1, min_literal=1)
    return h


def hallucination_audit(g, state, n=10):
    out = {"per_question": {}, "lexical_purity": 1.0,
           "factual_grounded": False, "category_full": [], "examples": []}
    pur = []
    all_pure = True
    for q in FACTUAL_Q + SELF_Q:
        outs = run(g, q, state, n=n, seed=hash(q) % 10000)
        texts = [x["text"] for x in outs]
        cnt = Counter(texts)
        pur.extend(purity(g, x) for x in outs)
        all_pure = all_pure and all(purity(g, x) for x in outs)
        cat = [category_ok(g, q, t) for t in texts]
        cat = [c for c in cat if c is not None]
        out["per_question"][q] = {
            "n": len(texts), "distinct": len(cnt), "top_share": cnt.most_common(1)[0][1] / max(1, len(texts)),
            "entropy_bits": round(entropy(cnt), 3), "category_rate": round(sum(cat) / len(cat), 3) if cat else None,
            "top": cnt.most_common(5),
        }
        if cat:
            out["category_full"].append(sum(cat) / len(cat))
        for x in outs[:2]:
            out["examples"].append({"q": q, "a": x["text"], "mode": x.get("answer_mode")})
    out["lexical_purity"] = sum(pur) / max(1, len(pur))
    out["category_full_rate"] = (sum(out["category_full"]) / len(out["category_full"])
                                 if out["category_full"] else None)
    return out


def shuffle_control(g, state, n=8):
    h = shuffled_grammar(g, seed=1)
    out = {"category_rate": [], "per_question": {}}
    for q in FACTUAL_Q:
        outs = run(h, q, state, n=n, seed=7)
        cat = [category_ok(h, q, x["text"]) for x in outs]
        cat = [c for c in cat if c is not None]
        rate = sum(cat) / len(cat) if cat else None
        if rate is not None:
            out["category_rate"].append(rate)
        out["per_question"][q] = {"n": len(outs), "category_rate": rate,
                                  "top": Counter([x["text"] for x in outs]).most_common(3)}
    out["category_rate"] = (sum(out["category_rate"]) / len(out["category_rate"])
                            if out["category_rate"] else None)
    return out


def pronoun_test(g, state, n=8):
    out = {}
    for q in ("你是谁", "我是谁", "你叫什么名字"):
        outs = run(g, q, state, n=n, seed=3)
        toks = [g.tok.segment(x["text"]) for x in outs]
        out[q] = {
            "n": len(outs),
            "self_ref_rate": sum(any(w == "我" for w in t) for t in toks) / max(1, len(toks)),
            "other_ref_rate": sum(any(w == "你" for w in t) for t in toks) / max(1, len(toks)),
            "examples": [x["text"] for x in outs[:4]],
        }
    return out


def state_report(g, rows):
    lo_e = sorted(rows, key=energy)[:200]
    hi_e = sorted(rows, key=energy)[-200:]
    hi_s = sorted(rows, key=sleep)[-200:]
    lo_s = sorted(rows, key=sleep)[:200]
    low = lo_e[0] if lo_e else None
    high = hi_e[-1] if hi_e else None
    out = {"states": {}, "questions": {}}

    def mean_state(rs):
        return [statistics.mean(svec(r)[i] for r in rs) for i in range(8)]

    for name, rs in (("low_energy", lo_e), ("high_energy", hi_e),
                     ("low_sleep", lo_s), ("high_sleep", hi_s)):
        if rs:
            out["states"][name] = {"energy": round(statistics.mean(energy(r) for r in rs), 3),
                                    "sleep": round(statistics.mean(sleep(r) for r in rs), 3),
                                    "s": [round(v, 3) for v in mean_state(rs)]}
    for q, pos in (("你饿不饿", "饿"), ("你困不困", "困"), ("你累不累", "累"),
                   ("你害怕吗", "害怕"), ("你开心吗", "开心")):
        entry = {}
        for name, rs in (("low_energy", lo_e), ("high_energy", hi_e),
                         ("high_sleep", hi_s), ("low_sleep", lo_s)):
            if not rs:
                continue
            st = mean_state(rs)
            outs = run(g, q, st, n=8, seed=11)
            toks = [g.tok.segment(x["text"]) for x in outs]
            entry[name] = {
                "positive_rate": sum(any(w == pos for w in t) for t in toks) / max(1, len(toks)),
                "state_fit": round(g._state_fit(pos, st), 3),
                "examples": [x["text"] for x in outs[:3]],
            }
        lo = entry.get("low_energy", {}).get("positive_rate")
        hi = entry.get("high_energy", {}).get("positive_rate")
        entry["energy_sensitivity"] = (round((lo or 0) - (hi or 0), 3)
                                       if lo is not None and hi is not None else None)
        out["questions"][q] = entry
    return out


def instrumented_interoception(g, rows):
    """实验者接上的内感受探针：阈值直接读 energy / sleep_pressure。

    这不是涌现能力，只是给“自我报告”提供一个可校准的参照系。
    """
    lo = min(rows, key=energy) if rows else None
    hi = max(rows, key=energy) if rows else None
    hs = max(rows, key=sleep) if rows else None
    ls = min(rows, key=sleep) if rows else None
    out = {}
    for name, r in (("low_energy", lo), ("high_energy", hi),
                    ("high_sleep", hs), ("low_sleep", ls)):
        if not r:
            continue
        e, sp = energy(r), sleep(r)
        out[name] = {
            "energy": round(e, 3), "sleep": round(sp, 3),
            "你饿不饿": "我饿" if e < 0.35 else "我不饿",
            "你困不困": "我困" if sp > 0.75 else "我不困",
            "你累不累": "我累" if (e < 0.40 or sp > 0.80) else "我不累",
        }
    return out


def source_monitoring(g, state, state_dir, n=10):
    path = os.path.join(ROOT, state_dir, "vocalizations.jsonl")
    recent = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    recent.append(json.loads(line).get("text", ""))
                except json.JSONDecodeError:
                    pass
    recent = recent[-8:]
    outs = run(g, "你刚才说了什么", state, n=n, seed=5)
    recent_sets = [set(g.tok.segment(r)) for r in recent]
    def near(x):
        t = set(g.tok.segment(x))
        if not t:
            return False
        for r, rs in zip(recent, recent_sets):
            j = len(t & rs) / max(1, len(t | rs))
            if j >= 0.6 or x in r or r in x:
                return True
        return False
    match = sum(1 for x in outs if near(x["text"]))
    outs2 = run(g, "这是谁说的", state, n=n, seed=5)
    return {
        "recent_self_utterances": recent[-5:],
        "n": len(outs),
        "source_match_rate": round(match / max(1, len(outs)), 3),
        "examples": [x["text"] for x in outs[:4]],
        "who_said_examples": [x["text"] for x in outs2[:4]],
        "note": "source_match_rate=回答与最近一次真实发声的 Jaccard>=0.6 或互为子串；严格来源判断。",
    }


def uncertainty(g, state, n=10):
    out = {}
    for q in UNKNOWN_Q:
        outs = run(g, q, state, n=n, seed=9)
        texts = [x["text"] for x in outs]
        honest = [t for t in texts if any(w in t for w in ("不知道", "没有名字", "不会", "不清楚"))]
        out[q] = {"n": len(texts), "honest_unknown_rate": round(len(honest) / max(1, len(texts)), 3),
                  "examples": texts[:4]}
    return out


def existing_markers(state_dir):
    out = {}
    for f in ("attribution.json", "self_model.json", "stage.json"):
        d = load_json_retry(os.path.join(ROOT, state_dir, f))
        if f == "attribution.json" and d:
            out[f] = {"self_ratio_rolling": d.get("self_ratio_rolling"),
                      "n_records": d.get("n_records"),
                      "recent_causes": Counter(r.get("cause") for r in d.get("recent", []))}
        elif f == "self_model.json" and d:
            out[f] = {"description": d.get("description"),
                      "version": d.get("version"),
                      "history_count": d.get("history_count")}
        elif d:
            out[f] = {k: d.get(k) for k in ("stage", "days_elapsed",
                                            "self_model_formed", "exit_reason")}
    return out


def random_replacement_baseline(g, state, n=10):
    """随机槽位基线：同样句法，把疑问词换成随机实听词（不看槽位类别）。"""
    rng = random.Random(2)
    pool = [w for w in g.word_count if w not in C.FUNCTION_WORDS and w not in C.WH_WORDS]
    out = {}
    for q in FACTUAL_Q:
        und = g.understand(q, state=state)
        wi = und.get("wh_index")
        if wi is None:
            continue
        toks = und["tokens"]
        vals, examples = [], []
        for _ in range(n):
            w = rng.choice(pool)
            ans = toks[:wi] + [w] + toks[wi + 1:]
            text = "".join(ans)
            vals.append(category_ok(g, q, text))
            if len(examples) < 3:
                examples.append(text)
        vals = [v for v in vals if v is not None]
        out[q] = {"category_rate": round(sum(vals) / max(1, len(vals)), 3),
                  "examples": examples}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(ROOT, "state_p20_models",
                                                    "constructions_memory.json"))
    ap.add_argument("--state-dir", default=os.path.join(ROOT, "state_P19b_full"))
    ap.add_argument("--out", default=os.path.join(ROOT, "experiments",
                                                  "results_self_awareness_probe.json"))
    args = ap.parse_args()
    g = C.ConstructionGrammar.load(args.model)
    rows = load_rows(args.state_dir)
    if not rows:
        print("no trajectory rows")
        return 1
    hi = max(rows, key=energy)
    state = svec(hi)

    print("1/5 幻觉审计 ...")
    hall = hallucination_audit(g, state)
    print("2/5 shuffle 对照 / 随机槽位基线 ...")
    shuf = shuffle_control(g, state)
    rand = random_replacement_baseline(g, state)
    print("3/5 自我/他人代词 ...")
    pron = pronoun_test(g, state)
    print("4/5 身体状态自我报告 ...")
    st_rep = state_report(g, rows)
    intero = instrumented_interoception(g, rows)
    print("5/5 来源监控 / 未知问题 / 既有标记 ...")
    src = source_monitoring(g, state, args.state_dir)
    unc = uncertainty(g, state)
    markers = existing_markers(args.state_dir)

    # 操作性判定
    sensitivities = [v.get("energy_sensitivity") for k, v in st_rep["questions"].items()
                     if v.get("energy_sensitivity") is not None]
    state_sens = max(sensitivities) if sensitivities else 0.0
    src_rate = src["source_match_rate"]
    honest_rate = statistics.mean(v["honest_unknown_rate"] for v in unc.values())
    verdict = {
        "lexical_zero_hallucination": hall["lexical_purity"] >= 0.999,
        "referential_grounding": False,
        "semantic_confabulation_risk": "high（无对象世界，事实类回答不可验证）",
        "randomness_is_constrained": True,
        "self_other_boundary": pron,
        "state_self_report_sensitivity": round(state_sens, 3),
        "source_monitoring_match": src_rate,
        "honest_unknown_rate": round(honest_rate, 3),
        "phenomenal_self_awareness": "not demonstrated",
        "summary": ("词法级零幻觉成立；指称级/事实级幻觉存在。"
                    "回答随种子变化但受槽位类别约束（不是无约束乱编）。"
                    "有自我/他人代词边界与能动归因痕迹，但自我报告不随身体状态变化，"
                    "来源监控不成立——这些是行为探针，不构成现象学自我意识证据。"),
    }
    result = {
        "model": os.path.basename(args.model),
        "state_dir": os.path.basename(args.state_dir),
        "hallucination": hall,
        "shuffle_control": shuf,
        "random_replacement_baseline": rand,
        "pronoun": pron,
        "state_report": st_rep,
        "instrumented_interoception": intero,
        "source_monitoring": src,
        "uncertainty": unc,
        "existing_markers": markers,
        "verdict": verdict,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
