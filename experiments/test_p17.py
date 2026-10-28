"""test_p17.py — P17 词汇爆发单测（预注册 audits.unit_test_required）

覆盖两件事：
  A. force_pool 修复——状态针对性 / 指称通道**永不被语料覆盖**
     （这是 P17 首跑 H17b n_world=0 的根因：_say 加载语料后覆盖了世界命名通道）
  B. 词汇发育机制——top-cap 采样 / adaptive 与 fixed_fast 扩词 / 上限饱和 / 持久化
"""
import json
import os
import random
import sys
import tempfile

os.environ["STATE_DIR"] = "/tmp/p17_test_state"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import language as L

PASS = 0
FAIL = 0


def check(d, c, e=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ✓ {d}")
    else:
        FAIL += 1; print(f"  ✗ {d} {e}")


def make_corpus(n=10):
    """n 型语料，count 递减（index 越大 count 越低），便于验证 top-cap 截取。"""
    rows = [{"text": f"kw{i}", "count": float(n - i)} for i in range(n)]
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    return path, [f"kw{i}" for i in range(n)]


def make_lang(corpus_path, **cg):
    cfg = {
        "language": {"enabled": True},
        "caregiver": {"mode": "contingent", "corpus_file": corpus_path},
    }
    cfg["caregiver"].update(cg)
    return L.Language(cfg)


# ============ A. force_pool 修复 ============

def case1_force_pool():
    print("\n[①] _say(force_pool)：指定池永不被语料覆盖")
    path, types = make_corpus(10)
    lg = make_lang(path)
    random.seed(1)
    forced = {lg._say(["X"], force_pool=True) for _ in range(300)}
    check("force_pool=True → 恒为指定池 'X'", forced == {"X"}, f"{forced}")
    plain = {lg._say(["X"], force_pool=False) for _ in range(300)}
    check("force_pool=False → 走语料（出现语料型）", plain & set(types), f"{plain}")
    check("force_pool=False → 不再是纯 'X'", "X" not in plain, f"{plain}")


def case2_world_naming_not_overridden():
    print("\n[②] 世界命名通道不被语料覆盖（H17b 根因修复）")
    path, _ = make_corpus(10)
    lg = make_lang(path, world_contingent=True, wc_rate_per_hour=1000.0)
    random.seed(2)
    hi = {lg.caregiver_speaks(1.0, 12.0, False, state_vec=[0.5] * 8,
                              asleep=False, world_field=0.9)
          for _ in range(300)}
    lo = {lg.caregiver_speaks(1.0, 12.0, False, state_vec=[0.5] * 8,
                              asleep=False, world_field=0.1)
          for _ in range(300)}
    check("世界场 HIGH → 恒说 HIGH 词表", hi and hi <= set(L.CORPUS_WORLD_HI), f"{hi}")
    check("世界场 LOW → 恒说 LOW 词表", lo and lo <= set(L.CORPUS_WORLD_LO), f"{lo}")
    check("HIGH/LOW 词表不相交", not (hi & lo))


def case3_state_channels_not_overridden():
    print("\n[③] 状态针对性通道（安抚/无聊召唤/被注视）不被语料覆盖")
    path, _ = make_corpus(10)
    random.seed(3)
    # 安抚：#3（s4 高）
    lg = make_lang(path)
    s = [0.5] * 8; s[3] = 0.9
    sooth = {lg.caregiver_speaks(1.0, 12.0, False, state_vec=s, asleep=False)
             for _ in range(200)}
    ok_pool = set(L.CORPUS_NIGHT) | set(L.FP_SOOTHE)
    check("s4 高 → 恒说安抚池", sooth and sooth <= ok_pool, f"{sooth}")
    # 无聊召唤：#4（s8 高）
    lg = make_lang(path)
    s = [0.5] * 8; s[7] = 0.9
    bore = {lg.caregiver_speaks(1.0, 12.0, False, state_vec=s, asleep=False)
            for _ in range(200)}
    bore_pool = {"看", "看这个", "又动了", "又动啦", "摸摸", "来了来了"}
    check("s8 高 → 恒说召唤池", bore and bore <= bore_pool, f"{bore}")
    # 被注视：#5（salience 高）——须把 s4/s8 压到阈值下，否则先被 #3/#4 拦截
    lg = make_lang(path)
    s = [0.3] * 8
    attn = {lg.caregiver_speaks(1.0, 12.0, False, state_vec=s,
                                asleep=False, salience=0.9)
            for _ in range(200)}
    check("salience 高 → 恒说自我指向池", attn and attn <= set(L.CORPUS_SELF), f"{attn}")


# ============ B. 词汇发育机制 ============

def case4_vocab_cap():
    print("\n[④] top-cap 采样池截取")
    path, types = make_corpus(10)
    lg = make_lang(path, corpus_vocab_cap=3)
    check("cap=3 → 池只有 3 型", len(lg.corpus_texts) == 3, f"{lg.corpus_texts}")
    check("cap=3 → 取 top-3（高频优先）", set(lg.corpus_texts) == set(types[:3]),
          f"{lg.corpus_texts}")
    check("cap=0 → 不设限（全池）", len(make_lang(path, corpus_vocab_cap=0).corpus_texts) == 10)


def case5_adaptive_growth():
    print("\n[⑤] adaptive 扩词：巩固了再扩")
    path, types = make_corpus(10)
    lg = make_lang(path, corpus_vocab_cap=2, vocab_growth="adaptive",
                   vocab_median_threshold=5.0, vocab_cap_max=8)
    # 未巩固（中位 0）→ 不扩
    lg.maybe_grow_vocab(10)
    check("未巩固 → cap 不变", lg.corpus_vocab_cap == 2, f"{lg.corpus_vocab_cap}")
    # 巩固（每型样本 ≥ 阈值）→ 翻倍（须同步 _type_n_sum，保持优化后的不变式）
    lg._type_n = {t: 6 for t in lg.corpus_texts}
    lg._type_n_sum = sum(lg._type_n.values())
    lg.maybe_grow_vocab(11)
    check("已巩固 → cap 翻倍 2→4", lg.corpus_vocab_cap == 4, f"{lg.corpus_vocab_cap}")
    check("扩词后池同步重建", len(lg.corpus_texts) == 4, f"{lg.corpus_texts}")
    check("扩词后型计数清零", lg._type_n == {}, f"{lg._type_n}")


def case6_fixed_fast_and_saturation():
    print("\n[⑥] fixed_fast 定时扩词 + 上限饱和")
    path, types = make_corpus(10)
    lg = make_lang(path, corpus_vocab_cap=2, vocab_growth="fixed_fast",
                   vocab_cap_max=6)
    lg._cap_last_grow_day = 0
    lg.maybe_grow_vocab(5)
    check("未满 15 日 → 不扩", lg.corpus_vocab_cap == 2, f"{lg.corpus_vocab_cap}")
    lg.maybe_grow_vocab(20)
    check("满 15 日 → 翻倍 2→4", lg.corpus_vocab_cap == 4, f"{lg.corpus_vocab_cap}")
    lg._cap_last_grow_day = 40
    lg.maybe_grow_vocab(60)
    check("触上限 → 封顶 6", lg.corpus_vocab_cap == 6, f"{lg.corpus_vocab_cap}")
    lg._cap_last_grow_day = 80
    lg.maybe_grow_vocab(100)
    check("已在上限 → 不再扩", lg.corpus_vocab_cap == 6, f"{lg.corpus_vocab_cap}")


def case7_persistence():
    print("\n[⑦] 发育状态持久化往返")
    path, _ = make_corpus(10)
    lg = make_lang(path, corpus_vocab_cap=2, vocab_growth="adaptive",
                   vocab_cap_max=8)
    lg.corpus_vocab_cap = 4
    lg._cap_last_grow_day = 33
    lg._type_n = {"kw0": 7, "kw1": 9}
    snap = lg.snapshot()
    check("snapshot 含 cap", snap["corpus_vocab_cap"] == 4)
    check("snapshot 含 last_grow_day", snap["cap_last_grow_day"] == 33)
    check("snapshot 含 type_n", snap["type_n"] == {"kw0": 7, "kw1": 9})


if __name__ == "__main__":
    print("=" * 64); print("P17 词汇爆发 单测"); print("=" * 64)
    case1_force_pool()
    case2_world_naming_not_overridden()
    case3_state_channels_not_overridden()
    case4_vocab_cap()
    case5_adaptive_growth()
    case6_fixed_fast_and_saturation()
    case7_persistence()
    print("\n" + "=" * 64)
    print(f"结果：{PASS} passed, {FAIL} failed")
    print("=" * 64)
    sys.exit(1 if FAIL else 0)
