#!/usr/bin/env python3
"""tools/build_constructions.py — P20 构造语法原型：构建 + 留出评估

用法：
  ./venv/bin/python tools/build_constructions.py --out state_p20_models/constructions.json --eval
  ./venv/bin/python tools/build_constructions.py --source state --state-dir state_P19b_full \
      --out state_p20_models/constructions_memory.json

结构统计默认来自 corpus/caregiver_corpus.json（环境侧的照护者语言，按频次加权）；
状态绑定默认来自 --state-dir 的 linguistic_memory.json（系统**真实听过**的轨迹）。
留出评估按「整句类型」切分：10% 的句子类型完全不参与训练，用来测它能不能
用听过的句式去解析没听过的句子。
"""
import argparse
import hashlib
import json
import math
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import constructions as C  # noqa: E402


def is_holdout(text, frac=0.10):
    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    return (int(h[:8], 16) % 1000) < int(frac * 1000)


def load_json_retry(path, attempts=15, delay=0.25):
    """主进程可能正在写 linguistic_memory.json：读到半截就重试。"""
    last = None
    for _ in range(attempts):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            last = e
            time.sleep(delay)
    raise last


def load_corpus(path):
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    return [(str(r.get("text", "")).strip(), float(r.get("count", 1)))
            for r in rows if str(r.get("text", "")).strip()]


def load_sessions(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("sessions", d if isinstance(d, list) else [])


def build(rows, sessions, holdout_frac=0.10, do_holdout=True, min_count=1):
    g = C.ConstructionGrammar(os.path.join(ROOT, "corpus", "lexicon.json"))
    train_types, test_types = [], []
    for text, count in rows:
        if count < min_count:
            continue
        if do_holdout and is_holdout(text, holdout_frac):
            test_types.append((text, count))
            continue
        train_types.append((text, count))
    t0 = time.time()
    for text, count in train_types:
        g.learn(text, weight=count)
    # 话语相继：同一会话里的相邻句（照护者单侧，近似“什么话后面常接什么话”）
    for sess in sessions:
        prev = None
        for item in sess:
            text = item[0] if isinstance(item, (list, tuple)) else str(item)
            toks = g.tok.segment(text)
            if not toks:
                continue
            sig = g.signature(toks)
            if prev is not None:
                g.add_transition(prev, sig, 1.0)
            prev = sig
    g.finalize()
    print(f"[build] train_types={len(train_types)} test_types={len(test_types)} "
          f"frames={len(g.frames)} words={len(g.word_count)} "
          f"({time.time()-t0:.1f}s)")
    return g, train_types, test_types


def bind_state(g, state_dir):
    path = os.path.join(ROOT, state_dir, "linguistic_memory.json")
    if not os.path.exists(path):
        print(f"[bind] 无 {path}，跳过状态绑定")
        return 0
    mem = load_json_retry(path)
    n = 0
    for r in mem:
        text = str(r.get("text", "")).strip()
        if not text:
            continue
        g.observe_state(text, state=r.get("s"), world=r.get("world"), weight=1.0)
        n += 1
    print(f"[bind] 状态绑定 {n} 条（来自 {state_dir}）")
    return n


def masked_eval(g, test_types, n_utt=300, seed=0):
    rng = random.Random(seed)
    rows = [(t, c) for t, c in test_types if 3 <= len(g.tok.segment(t)) <= 8]
    rng.shuffle(rows)
    rows = rows[:n_utt]
    hits1 = hits5 = base1 = base5 = prior1 = total = 0
    examples = []
    # 全局 unigram 基线
    uni = [w for w, _ in g.word_count.most_common(50) if w not in C.FUNCTION_WORDS]
    for text, count in rows:
        toks = g.tok.segment(text)
        for pos, true_w in enumerate(toks):
            if true_w in C.FUNCTION_WORDS:
                continue
            masked = toks[:pos] + ["_"] + toks[pos + 1:]
            # 用解析器在挖空句上找句式：把 '_' 当成未知，解析其余跨度
            inst = g.parse([w for w in masked if w != "_"])
            # 更直接：找所有覆盖 pos 的单空句式
            cand_frames = []
            for i in range(max(0, pos - 3), pos + 1):
                for j in range(pos + 1, min(len(toks), pos + 4)):
                    span = tuple(toks[i:j])
                    if pos - i >= len(span):
                        continue
                    lit = span[:pos - i] + span[pos - i + 1:]
                    fr = span[:pos - i] + ("_",) + span[pos - i + 1:]
                    if fr in g.frames:
                        cand_frames.append((fr, i, j))
            if not cand_frames:
                continue
            # 取覆盖最长上下文的句式
            fr, i, j = max(cand_frames, key=lambda x: (x[2] - x[1]) * 10
                           + g.frames[x[0]]["n"])
            topics = [w for k, w in enumerate(toks) if k != pos and w not in C.FUNCTION_WORDS]
            cands = g._candidate_words(fr, topics, None, None, limit=200)
            scored = sorted(((g._score_filler(w, fr, topics, None, None, set()),
                              w) for w in cands), reverse=True)
            preds = [w for _, w in scored[:5]]
            most = g.frames[fr]["fillers"].most_common(1)[0][0] if g.frames[fr]["fillers"] else None
            total += 1
            hits1 += int(bool(preds) and preds[0] == true_w)
            hits5 += int(true_w in preds)
            prior1 += int(most == true_w)
            base1 += int(uni[0] == true_w)
            base5 += int(true_w in uni[:5])
            if len(examples) < 12:
                examples.append({"text": text, "mask": "".join(masked),
                                 "truth": true_w, "pred": preds[:3],
                                 "frame": "".join(fr)})
    return {"n": total,
            "top1": hits1 / max(1, total), "top5": hits5 / max(1, total),
            "frame_prior_top1": prior1 / max(1, total),
            "unigram_top1": base1 / max(1, total),
            "unigram_top5": base5 / max(1, total),
            "examples": examples}


def _is_pure(g, toks):
    return all(w in g.word_count for w in toks)


def _novel(g, toks, partner):
    return "".join(toks) not in g.seen and "".join(toks) != partner


def generation_eval(g, test_types, state, world, n_utt=200, seed=1):
    rng = random.Random(seed)
    rows = [(t, c) for t, c in test_types if 2 <= len(g.tok.segment(t)) <= 8]
    rng.shuffle(rows)
    rows = rows[:n_utt]
    stats = {"n": 0, "pure": 0, "novel": 0, "topic": 0, "frame": 0, "len": 0}
    modes = {}
    examples = []
    for text, _ in rows:
        und, gen = g.respond(text, state=state, world=world, rng=rng)
        if not gen:
            continue
        toks = gen["tokens"]
        topics = set(und.get("topics", []))
        stats["n"] += 1
        stats["pure"] += int(_is_pure(g, toks))
        stats["novel"] += int(_novel(g, toks, text))
        stats["topic"] += int(bool(topics & set(toks)))
        stats["frame"] += int(gen.get("frame") is not None or
                              gen.get("answer_mode") in ("yesno_echo", "greeting"))
        stats["len"] += len(toks)
        m = gen.get("answer_mode", "frame")
        modes[m] = modes.get(m, 0) + 1
        if len(examples) < 15:
            examples.append({"in": text, "out": gen["text"],
                             "act": und["speech_act"],
                             "mode": gen.get("answer_mode", "frame"),
                             "frame": "".join(gen["frame"]) if gen.get("frame") else None})
    n = max(1, stats["n"])
    return {"n": stats["n"],
            "purity": stats["pure"] / n, "novel": stats["novel"] / n,
            "topic_overlap": stats["topic"] / n, "frame_valid": stats["frame"] / n,
            "avg_len": stats["len"] / n, "modes": modes, "examples": examples}


def _choose_wh(g, filler):
    if filler in C.LOCATION_HINTS or g._role_sim(filler, "哪里") > 0.2:
        return "哪里"
    if filler in ("妈妈", "爸爸", "宝宝", "哥哥", "姐姐", "弟弟", "妹妹",
                  "老师", "医生", "阿姨", "爷爷", "奶奶"):
        return "谁"
    if g._pmi(filler, "很") > 0.5:
        return "怎么样"
    return "什么"


def pseudo_question_eval(g, test_types, state, world, n_utt=120, seed=3):
    """留出句 → 把一个实词换成疑问词 → 看它能否把这个词补回来。

    这是“理解+重组”的最直接检验：问句的句法来自对方，槽位内容必须由
    语境/槽位类别/状态共同决定。exact=原词被补回；category=补回同类词。
    """
    rng = random.Random(seed)
    rows = [(t, c) for t, c in test_types if 3 <= len(g.tok.segment(t)) <= 8]
    rng.shuffle(rows)
    rows = rows[:n_utt]
    n = exact_any = exact_first = cat_any = 0
    modes = {}
    examples = []
    for text, _ in rows:
        toks = g.tok.segment(text)
        cand_pos = [i for i, w in enumerate(toks)
                    if w not in C.FUNCTION_WORDS and w in g.word_count]
        if not cand_pos:
            continue
        pos = rng.choice(cand_pos)
        truth = toks[pos]
        frame = tuple(toks[:pos] + ["_"] + toks[pos + 1:])
        if frame not in g.frames:
            continue
        wh = _choose_wh(g, truth)
        q = list(toks)
        q[pos] = wh
        qtext = "".join(q)
        n += 1
        outs = []
        for k in range(3):
            und, gen = g.respond(qtext, state=state, world=world, rng=rng)
            if gen:
                outs.append(gen)
                modes[gen.get("answer_mode")] = modes.get(gen.get("answer_mode"), 0) + 1
                if k == 0 and truth in gen["tokens"]:
                    exact_first += 1
        if any(truth in x["tokens"] for x in outs):
            exact_any += 1
        classy = set(g.frames[frame]["fillers"]) | {
            w for w in g.word_count if g._role_sim(w, truth) >= 0.5}
        if any(set(x["tokens"]) & classy for x in outs):
            cat_any += 1
        if len(examples) < 12:
            examples.append({"heldout": text, "question": qtext, "truth": truth,
                             "answers": [x["text"] for x in outs]})
    return {"n": n, "exact_any": exact_any / max(1, n),
            "exact_first": exact_first / max(1, n),
            "category_any": cat_any / max(1, n), "modes": modes,
            "examples": examples}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="corpus", choices=("corpus", "state"))
    ap.add_argument("--corpus", default=os.path.join(ROOT, "corpus", "caregiver_corpus.json"))
    ap.add_argument("--sessions", default=os.path.join(ROOT, "corpus", "caregiver_sessions.json"))
    ap.add_argument("--state-dir", default="state_P19b_full")
    ap.add_argument("--out", default=os.path.join(ROOT, "state_p20_models", "constructions.json"))
    ap.add_argument("--no-holdout", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--min-count", type=float, default=1)
    args = ap.parse_args()

    if args.source == "corpus":
        rows = load_corpus(args.corpus)
        sessions = load_sessions(args.sessions)
    else:
        mem_path = os.path.join(ROOT, args.state_dir, "linguistic_memory.json")
        mem = load_json_retry(mem_path)
        rows = [(r["text"], 1.0) for r in mem]
        sessions = []

    g, train_types, test_types = build(
        rows, sessions, do_holdout=not args.no_holdout, min_count=args.min_count)
    bind_state(g, args.state_dir)
    # 状态绑定后再剪一次（保证索引与 frames 一致）
    g.finalize()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    g.save(args.out)
    print(f"[save] {args.out} ({os.path.getsize(args.out)/1e6:.1f} MB)")

    if args.eval and test_types:
        state = [0.5] * 8
        # 用系统最近一次真实状态作为评估状态
        mem_path = os.path.join(ROOT, args.state_dir, "linguistic_memory.json")
        if os.path.exists(mem_path):
            mem = load_json_retry(mem_path)
            if mem and mem[-1].get("s"):
                state = mem[-1]["s"]
        print("[eval] masked-word prediction ...")
        me = masked_eval(g, test_types, n_utt=250)
        print("[eval] generation ...")
        ge = generation_eval(g, test_types, state, 0.5, n_utt=200)
        print("[eval] pseudo-question answering ...")
        pe = pseudo_question_eval(g, test_types, state, 0.5, n_utt=120)
        out = {"masked": {k: v for k, v in me.items() if k != "examples"},
               "generation": {k: v for k, v in ge.items() if k != "examples"},
               "pseudo_question": {k: v for k, v in pe.items() if k != "examples"},
               "masked_examples": me["examples"],
               "generation_examples": ge["examples"],
               "pseudo_examples": pe["examples"]}
        out_path = os.path.join(ROOT, "experiments", "results_P20_proto.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(json.dumps({k: v for k, v in out.items() if not k.endswith("examples")},
                         ensure_ascii=False, indent=2))
        print(f"[eval] -> {out_path}")


if __name__ == "__main__":
    main()
