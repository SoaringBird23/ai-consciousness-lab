"""build_p14b_content_map.py — 生成并冻结 P14b 的『型→应答倾向』映射

见 experiments/prereg_P14b_content_sensitive_caregiver.json → design.content_map。

规则（事前冻结，不得事后修改）：
  取照护者内置语料的全部唯一型，按 UTF-8 字节序升序排序；
  用 random.Random(1401) 打乱；前 ceil(n/2) 个为 HIGH(r=0.9)，其余为 LOW(r=0.1)。
  产出 experiments/p14b_content_map.json（含 sha256，供实现前校验冻结）。

用法：./venv/bin/python tools/build_p14b_content_map.py
"""
import hashlib
import importlib.util
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = 1401
R_HIGH = 0.9
R_LOW = 0.1
OUT = os.path.join(ROOT, "experiments", "p14b_content_map.json")


def load_language_module():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    spec = importlib.util.spec_from_file_location(
        "language", os.path.join(ROOT, "language.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    lang = load_language_module()
    pools = (lang.CORPUS_EVENT + lang.CORPUS_NIGHT + lang.CORPUS_DAY
             + lang.CORPUS_SELF + lang.FP_SOOTHE)
    types = sorted(set(pools))
    n = len(types)
    shuffled = list(types)
    random.Random(SEED).shuffle(shuffled)
    k = (n + 1) // 2
    classes = {t: ("HIGH" if i < k else "LOW") for i, t in enumerate(shuffled)}
    r_map = {t: (R_HIGH if c == "HIGH" else R_LOW) for t, c in classes.items()}

    payload = {
        "experiment": "P14b",
        "rule": "sorted unique corpus types, random.Random(seed).shuffle, first ceil(n/2)=HIGH",
        "seed": SEED, "r_high": R_HIGH, "r_low": R_LOW,
        "n_types": n,
        "n_high": sum(1 for c in classes.values() if c == "HIGH"),
        "n_low": sum(1 for c in classes.values() if c == "LOW"),
        "classes": classes,
        "r": r_map,
    }
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    payload["sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"写入 {OUT}")
    print(f"  n_types={n} HIGH={payload['n_high']} LOW={payload['n_low']} sha256={payload['sha256'][:16]}…")
    print(f"  HIGH 样例: {[t for t in types if classes[t]=='HIGH'][:6]}")
    print(f"  LOW  样例: {[t for t in types if classes[t]=='LOW'][:6]}")


if __name__ == "__main__":
    main()
