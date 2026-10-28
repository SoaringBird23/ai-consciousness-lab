"""test_p18.py — P18 词级组合 单测

覆盖：
  ① 切词（最长匹配）
  ② 在线学词二元 + 实听词表
  ③ 组合：整体新、局部有据（相邻词对听过）、词法纯净（零幻觉硬约束）
  ④ shuffle 对照：词汇不变但结构关联被破坏（结构指标回落）
  ⑤ off：未启用 → composer=None，语言层行为逐位不变
  ⑥ 持久化往返
"""
import json
import os
import random
import sys
import tempfile

os.environ["STATE_DIR"] = "/tmp/p18_test_state"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import compose as C
import language as L

PASS = 0
FAIL = 0


def check(d, c, e=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ✓ {d}")
    else:
        FAIL += 1; print(f"  ✗ {d} {e}")


LEX = ["看", "球", "妈妈", "抱", "宝宝", "好", "亮亮", "灯", "走来", "过来",
       "去", "拿", "给"]
HEARD = ["看妈妈", "妈妈抱宝宝", "妈妈拿球", "抱宝宝过来", "亮亮好", "看球",
         "球好", "妈妈走来", "给宝宝", "拿球过来"]


def make_lex():
    fd, p = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"words": LEX, "params": {"MAXLEN": 3}}, f, ensure_ascii=False)
    return p


def mk(path, **kw):
    cfg = {"word_compose": {"enabled": True, "lexicon_file": path, "chain_len": 2}}
    cfg["word_compose"].update(kw)
    wc = C.WordComposer(cfg)
    for s in HEARD:
        wc.learn(s)
    return wc


def case1_segment():
    print("\n[①] 切词（最长匹配）")
    wc = mk(make_lex())
    check("'妈妈抱宝宝' → 妈妈/抱/宝宝", wc.segment("妈妈抱宝宝") == ["妈妈", "抱", "宝宝"],
          f"{wc.segment('妈妈抱宝宝')}")
    check("未命中单字保留", wc.segment("妈妈爱宝宝") == ["妈妈", "爱", "宝宝"],
          f"{wc.segment('妈妈爱宝宝')}")


def case2_learn():
    print("\n[②] 在线学词二元 + 实听词表")
    wc = mk(make_lex())
    check("实听词表覆盖", {"妈妈", "抱", "宝宝", "球"} <= wc.heard_words, f"{sorted(wc.heard_words)}")
    check("词二元 妈妈→{抱,拿,走来}",
          set(wc.bigram.get("妈妈", {})) == {"抱", "拿", "走来"}, f"{wc.bigram.get('妈妈')}")


def case3_compose():
    print("\n[③] 组合：整体新 / 局部有据 / 词法纯净")
    random.seed(3)
    wc = mk(make_lex())
    out = [wc.compose("看妈妈") for _ in range(40)]
    out = [o for o in out if o]
    check("组合发生（锚末词有后继时）", len(out) > 0)
    check("锚前缀保留", all(o["words"][:2] == ["看", "妈妈"] for o in out))
    check("整体新：整串未逐字听过", all(o["novel"] for o in out))
    check("局部有据：相邻词对全部听过",
          all(o["n_pairs_real"] == o["n_pairs"] for o in out))
    check("词法纯净=1.0（零幻觉硬约束）", all(o["purity"] == 1.0 for o in out))
    check("无后继锚 → 回退 None", wc.compose("抱宝宝过来") is None)


def case4_shuffle():
    print("\n[④] shuffle 对照：结构关联被破坏")
    random.seed(3)
    wf = mk(make_lex())
    ws = mk(make_lex(), shuffle=True)
    of = [o for o in (wf.compose("看妈妈") for _ in range(60)) if o]
    os_ = [o for o in (ws.compose("看妈妈") for _ in range(60)) if o]
    rf = sum(o["n_pairs_real"] / o["n_pairs"] for o in of) / len(of)
    rs = sum(o["n_pairs_real"] / o["n_pairs"] for o in os_) / len(os_)
    check("full 结构指标显著高于 shuffle", rf > rs + 0.3, f"full={rf:.2f} shuf={rs:.2f}")
    check("shuffle 仍词法纯净（词汇未变）", all(o["purity"] == 1.0 for o in os_))


def case5_off():
    print("\n[⑤] off：未启用则 composer=None")
    lg = L.Language({"language": {"enabled": True}, "caregiver": {"mode": "random"}})
    check("默认关 → composer 为 None", lg.composer is None)
    lg2 = L.Language({"language": {"enabled": True}, "caregiver": {"mode": "random"},
                      "word_compose": {"enabled": True, "lexicon_file": make_lex()}})
    check("启用 → composer 非空", lg2.composer is not None)


def case6_persist():
    print("\n[⑥] 持久化往返")
    p = make_lex()
    wc = mk(p)
    fd, sp = tempfile.mkstemp(suffix=".json"); os.close(fd)
    wc.save(sp)
    wc2 = C.WordComposer({"word_compose": {"enabled": True, "lexicon_file": p}})
    wc2.load(sp)
    check("词二元往返一致", wc2.bigram == wc.bigram)
    check("实听词表往返一致", wc2.heard_words == wc.heard_words)


if __name__ == "__main__":
    print("=" * 64); print("P18 词级组合 单测"); print("=" * 64)
    case1_segment(); case2_learn(); case3_compose()
    case4_shuffle(); case5_off(); case6_persist()
    print("\n" + "=" * 64)
    print(f"结果：{PASS} passed, {FAIL} failed")
    print("=" * 64)
    sys.exit(1 if FAIL else 0)
