"""analyze_R5.py —— R5 离线分析（不改系统）

读 state_R5_{off,full,shuf,nodep,nodecay,bigk}，按 experiments/prereg_R5.json 出表：

  MC_开口 : workspace.json 的 n_deposit；检索条数 n_retr
  M_回响  : 相邻念头『真实 top3 联想』命中率（H5b：full 应显著高于 shuf）
  M_持续  : 5 步内类型复现率、类型覆盖度（H5c）
  M_行为  : vs off 的逐 tick 检索重合（jaccard / phrase_agreement / first_divergence）
  M_自指  : self_directed 检索占比

真实联想图从 <真值态>/linguistic_memory.json 的听到顺序重建（所有臂共用同一张图）。

参数化（环境变量，默认即 R5 原行为，零回归）：
  WSP_STATE_PREFIX  臂目录前缀，默认 state_R5_
  WSP_TRUTH_STATE   真值态目录名，默认 state_exp
  WSP_RESULTS_ID    结果文件名后缀，默认 R5（→ experiments/results_<id>.json）
  WSP_LABEL         打印标签，默认 R5
  WSP_HYP           判据标签，默认 H5b

Step B（P6-B）用法：
  WSP_STATE_PREFIX=state_P6B_ WSP_TRUTH_STATE=state_P6_childes \
  WSP_RESULTS_ID=P6B WSP_LABEL=P6-B WSP_HYP=H6b \
  ./venv/bin/python experiments/analyze_R5.py [--json]

用法：./venv/bin/python experiments/analyze_R5.py [--json]
"""
import json
import os
import random
import sys
from collections import Counter

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 臂名列表与对照臂均可经环境变量覆盖（默认即 R5 原行为，零回归）。
# WSP_ARMS：逗号分隔的臂名（目录为 <STATE_PREFIX><臂名>）
# WSP_BASE：对照臂名；若其目录不存在，Jaccard 自动显示 n/a
ARMS = [a.strip() for a in os.environ.get(
    "WSP_ARMS", "off,full,shuf,nodep,nodecay,bigk").split(",") if a.strip()]
BASE = os.environ.get("WSP_BASE", "off")
N_PERM = 2000
SEC_PER_DAY = 86400.0

STATE_PREFIX = os.environ.get("WSP_STATE_PREFIX", "state_R5_")
TRUTH_STATE = os.environ.get("WSP_TRUTH_STATE", "state_exp")
# 真值序列来源：memory=听到顺序（听—听，默认，零回归）；thought=念头流顺序（念—念，P13）
TRUTH_SOURCE = os.environ.get("WSP_TRUTH_SOURCE", "memory")
RESULTS_ID = os.environ.get("WSP_RESULTS_ID", "R5")
LABEL = os.environ.get("WSP_LABEL", "R5")
HYP_TAG = os.environ.get("WSP_HYP", "H5b")


def _jsonl(path):
    """逐行读 jsonl；容忍末行被实时写坏（跳过无法解析的行）。"""
    if not os.path.exists(path):
        return None
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _load_json_array(path, retries=6, delay=0.5):
    """读一个 JSON 数组；容忍实时写入导致的截断。

    先尝试整体 json.load；失败则用 raw_decode 逐对象抽取已完整写出的前缀，
    中途休眠重试。故即便目标文件正被在跑进程改写，也能取到稳定前缀。
    """
    import time
    last = None
    for _ in range(retries):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            last = e
        try:
            with open(path) as f:
                txt = f.read()
            dec = json.JSONDecoder()
            i = txt.find("[")
            if i >= 0:
                i += 1
                out = []
                n = len(txt)
                while i < n:
                    while i < n and txt[i] in " \t\r\n,":
                        i += 1
                    if i >= n or txt[i] == "]":
                        break
                    obj, j = dec.raw_decode(txt, i)
                    out.append(obj)
                    i = j
                if out:
                    return out
        except Exception:
            pass
        time.sleep(delay)
    raise last


def _state(arm):
    return os.path.join(LAB, STATE_PREFIX + arm)


def _load_memory():
    p = os.path.join(LAB, TRUTH_STATE, "linguistic_memory.json")
    if not os.path.exists(p):
        return []
    return _load_json_array(p)


def _load_truth_texts():
    """真值序列。
    memory（默认）：<真值态>/linguistic_memory.json 的**听到顺序**（听—听图，零回归）；
    thought（P13）：<真值态>/inner_speech.jsonl 的**念头流顺序**（retrieval 记录，念—念图）。
    两者都用同一文件作为臂内继承前缀的判据（_inherit_prefix），与来源无关。"""
    if TRUTH_SOURCE == "thought":
        recs = _jsonl(os.path.join(LAB, TRUTH_STATE, "inner_speech.jsonl"))
        if not recs:
            return []
        return [r.get("text") for r in recs
                if r.get("type") == "retrieval" and r.get("text")]
    return [m["text"] for m in _load_memory()]


def _inherit_prefix():
    """继承前缀 = 真值态 inner_speech.jsonl 的记录数。

    各臂由 `cp -R <真值态>` 全量继承该文件，故臂内 inner_speech.jsonl 的前
    N 条为继承前缀、须剔除。注意：不能用 linguistic_memory.json 的长度（那是
    听到事件数，与念头数不同量纲）。
    """
    p = os.path.join(LAB, TRUTH_STATE, "inner_speech.jsonl")
    if not os.path.exists(p):
        return 0
    n = 0
    with open(p) as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def build_real_graph(texts):
    """从给定文本序列重建真实一阶共现 → 每个型的 top3 后继集合。"""
    uniq = sorted(set(texts))
    ix = {t: i for i, t in enumerate(uniq)}
    K = len(uniq)
    A = [[0.0] * K for _ in range(K)]
    for a, b in zip(texts[:-1], texts[1:]):
        if a != b:
            A[ix[a]][ix[b]] += 1.0
    top3 = {}
    for t in uniq:
        row = A[ix[t]]
        order = sorted(range(K), key=lambda j: -row[j])[:3]
        top3[t] = set(uniq[j] for j in order if row[j] > 0)
    return top3, K


def seq_stats(arm, n_inherit, top3, K):
    recs = _jsonl(os.path.join(_state(arm), "inner_speech.jsonl"))
    if recs is None:
        return None
    win = recs[n_inherit:]
    retr = [r for r in win if r.get("type") == "retrieval"]
    seq = [r.get("text") for r in retr if r.get("text")]
    if not seq:
        return {"n_retr": 0, "n_uniq": 0, "diversity": 0.0,
                "adj_top3_hit": None, "recur5": None, "self_ratio": None}
    adj = sum(1 for a, b in zip(seq[:-1], seq[1:]) if b in top3.get(a, set()))
    recur = sum(1 for i in range(5, len(seq)) if seq[i] in set(seq[i - 5:i]))
    sd = sum(1 for r in retr if r.get("self_directed"))
    return {
        "n_retr": len(seq),
        "n_uniq": len(set(seq)),
        "diversity": len(set(seq)) / K,
        "adj_top3_hit": (adj / (len(seq) - 1)) if len(seq) > 1 else None,
        "recur5": (recur / (len(seq) - 5)) if len(seq) > 5 else None,
        "self_ratio": sd / len(seq),
    }


def ws_stats(arm):
    p = os.path.join(_state(arm), "workspace.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        d = json.load(f)
    return {"enabled": d.get("enabled"), "n_deposit": d.get("n_deposit", 0),
            "n_types_act": len(d.get("act", {})),
            "n_assoc": len(d.get("assoc", {})),
            "k": d.get("k"), "kappa": d.get("kappa"),
            "shuffle_assoc": d.get("shuffle_assoc"),
            "no_deposit": d.get("no_deposit")}


def retrieval_map(arm, n_inherit):
    recs = _jsonl(os.path.join(_state(arm), "inner_speech.jsonl"))
    if recs is None:
        return None
    return {r["t"]: r.get("text") for r in recs[n_inherit:]
            if r.get("type") == "retrieval"}


def overlap(ctl, m, rng):
    common = sorted(set(ctl) & set(m))
    if not common:
        return {"n_common": 0}
    same = sum(1 for t in common if ctl[t] == m[t])
    return {"n_common": len(common), "phrase_agreement": same / len(common),
            "jaccard": len(common) / len(set(ctl) | set(m))}


def main():
    n_inherit = _inherit_prefix()
    top3, K = build_real_graph(_load_truth_texts())
    rng = random.Random(0)
    print("%s 离线分析（对照=%s；真值态=%s；真值来源=%s；继承前缀 %d 条已剔除；真实联想图 K=%d）"
          % (LABEL, BASE, TRUTH_STATE, TRUTH_SOURCE, n_inherit, K))

    base_map = retrieval_map(BASE, n_inherit)
    res = {"n_inherit": n_inherit, "K": K, "arms": {}}

    print()
    hdr = ("%-8s %7s %6s %7s | %9s %8s %7s | %7s %8s | %8s"
           % ("arm", "n_retr", "uniq", "divers", "adj_top3", "recur5",
              "self%", "n_dep", "n_asso", "jac"))
    print(hdr)
    print("-" * len(hdr))
    for arm in ARMS:
        st = seq_stats(arm, n_inherit, top3, K)
        ws = ws_stats(arm)
        m = retrieval_map(arm, n_inherit)
        ov = overlap(base_map, m, rng) if (base_map and m and arm != BASE) else None
        res["arms"][arm] = {"seq": st, "ws": ws, "overlap": ov}

        def f(v, fmt="%s", na="n/a"):
            return na if v is None else (fmt % v)
        print("%-8s %7s %6s %7s | %9s %8s %7s | %7s %8s | %8s"
              % (arm,
                 f(st and st["n_retr"], "%d"), f(st and st["n_uniq"], "%d"),
                 f(st and st["diversity"], "%.2f"),
                 f(st and st["adj_top3_hit"], "%.3f"),
                 f(st and st["recur5"], "%.3f"),
                 f(st and st["self_ratio"] and st["self_ratio"] * 100, "%.1f"),
                 f(ws and ws["n_deposit"], "%d"),
                 f(ws and ws["n_assoc"], "%d"),
                 f(ov and ov.get("jaccard"), "%.3f")))

    print()
    print("【%s】相邻念头『真实 top3 联想』命中率（full 应显著高于 shuf）" % HYP_TAG)
    for arm in ARMS:
        st = res["arms"][arm]["seq"]
        if st and st.get("adj_top3_hit") is not None:
            print("  %-8s adj_top3=%.3f" % (arm, st["adj_top3_hit"]))
    print("  随机基线≈3/K=%.3f" % (3.0 / max(1, K)))

    if "--json" in sys.argv:
        out = os.path.join(LAB, "experiments", "results_%s.json" % RESULTS_ID)
        with open(out, "w") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        print("\n已写", out)


if __name__ == "__main__":
    main()
