"""test_response_model.py — P14 预注册审计用例（4 条）

对应 prereg_P14_reflex_to_intent.json → audits.unit_test_required：
  ① 关闭时选择 == 检索胜者（逐位）
  ② E 全等时选择退化为 top-1
  ③ shuf 臂打乱键不改变候选生成、不污染 E 表
  ④ 单次发声的更新量可手算复现（反事实 EMA）

运行：./venv/bin/python experiments/test_response_model.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import response_model as rm_mod  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def cfg(enabled=True, shuffle=False, alpha=0.5, half_life_days=1e6):
    return {"response_model": {
        "enabled": enabled, "shuffle": shuffle, "top_k": 5,
        "window_seconds": 60.0, "half_life_days": half_life_days, "ema_alpha": alpha}}


def case1_disabled():
    print("\n[①] 关闭时选择 == 检索胜者（逐位）")
    rm = rm_mod.ResponseModel(cfg(enabled=False))
    cands = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
    sel, meta = rm.select(cands, "a")
    check("select 返回胜者", sel == "a", f"got {sel}")
    check("meta 为 None（无行为改变）", meta is None)
    rm.note_vocal(100.0, "a")
    rm.advance_clock(1.0, 101.0, 1)
    check("关闭时 E 表恒空", len(rm.E) == 0)
    check("关闭时无历史", len(rm.history) == 0)


def case2_tie_fallback():
    print("\n[②] E 全等时选择退化为 top-1")
    rm = rm_mod.ResponseModel(cfg(enabled=True))
    cands = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
    # 未学习 → 全部 uniform=1.0 → 全等
    sel, meta = rm.select(cands, "a")
    check("全等时返回 top-1", sel == "a", f"got {sel}")
    check("标记 e_tie", meta and meta.get("reason") == "e_tie", f"meta={meta}")
    # 学习后分化 → 应选 E 最大者
    rm.E = {"a": 1.0, "b": 3.0, "c": 2.0}
    sel2, meta2 = rm.select(cands, "a")
    check("分化后选 E 最大者", sel2 == "b", f"got {sel2}")
    check("was_winner 记为 False", meta2 and meta2.get("was_winner") is False)


def case3_shuffle_isolated():
    print("\n[③] shuf 打乱键不改变候选生成、不污染 E 表")
    rm = rm_mod.ResponseModel(cfg(enabled=True, shuffle=True))
    cands = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
    before_texts = [t for t, _ in cands]
    sel, meta = rm.select(cands, "a")
    check("候选生成不变（文本集合一致）",
          [t for t, _ in cands] == before_texts)
    check("所选仍在候选内", sel in before_texts, f"got {sel}")
    check("E 表未被 select 修改", len(rm.E) == 0, f"E={rm.E}")
    # 打乱键稳定：同 tick 同集合两次调用得到相同映射
    m1 = rm._shuffle_lookup(before_texts)
    m2 = rm._shuffle_lookup(before_texts)
    check("同集合映射稳定", m1 == m2, f"{m1} vs {m2}")


def case4_manual_ema():
    print("\n[④] 单次发声的更新量可手算复现（反事实 EMA）")
    rm = rm_mod.ResponseModel(cfg(enabled=True, shuffle=False, alpha=0.5))
    # 发声于 t=0。窗口 = 半开区间 [0, 60) → in_win 当且仅当 (t-0) < 60，即 t∈1..59
    rm.note_vocal(0.0, "X")
    # 窗口内 t=1..59：偶数 tick 有言语（2,4,...,58 共 29 次）
    for t in range(1, 60):
        rm.advance_clock(1.0, float(t), 1 if (t % 2 == 0) else 0)
    # 窗口外 t=60..120：t=60 及 t=61..66 有言语（共 7 次），时长 61s
    for t in range(60, 121):
        rm.advance_clock(1.0, float(t), 1 if (t == 60 or 61 <= t <= 66) else 0)
    # 再发声 → 结算上一窗口
    rm.note_vocal(120.0, "X")
    # half_life_days=1e6 → 单 tick 衰减 ~1e-12，手算按无衰减（误差 << 1e-6）
    r_in = 29.0 / 59.0
    r_out = 7.0 / 61.0
    observed = r_in / r_out
    predicted = 1.0
    expected = predicted + 0.5 * (observed - predicted)
    got = rm.E.get("X")
    check("E[X] 手算复现", got is not None and abs(got - expected) < 1e-6,
          f"got {got}, expected {expected}")
    check("历史记录一条", len(rm.history) == 1, f"n={len(rm.history)}")
    h = rm.history[0] if rm.history else {}
    check("历史 predicted 正确", abs(h.get("predicted", -1) - 1.0) < 1e-9, f"{h}")
    check("历史 observed 手算复现",
          abs(h.get("observed", -1) - round(observed, 4)) < 1e-9,
          f"got {h.get('observed')}, expected {round(observed, 4)}")
    check("历史 err = observed-predicted",
          abs(h.get("err", -1) - round(observed - predicted, 4)) < 1e-9, f"{h}")


def case5_counts():
    print("\n[⑤] P14c：按条数计入（n=3 的窗口内言语累计是 n=1 的 3 倍）")
    def win(n):
        rm = rm_mod.ResponseModel(cfg(enabled=True, alpha=1.0, half_life_days=1e6))
        rm.note_vocal(0.0, "X")
        for t in range(1, 60):
            rm.advance_clock(1.0, float(t), n)
        for t in range(60, 120):
            rm.advance_clock(1.0, float(t), 0)
        return rm._win_speech
    a, b = win(1), win(3)
    check("窗口内言语计数 3×", abs(b - 3 * a) < 1e-6, f"n1={a}, n3={b}")


if __name__ == "__main__":
    print("=" * 60)
    print("P14 response_model 单测（预注册 audits.unit_test_required）")
    print("=" * 60)
    case1_disabled()
    case2_tie_fallback()
    case3_shuffle_isolated()
    case4_manual_ema()
    case5_counts()
    print("\n" + "=" * 60)
    print(f"结果：{PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)
