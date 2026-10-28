"""test_counterfactual.py — P15 反事实配对单测（预注册 audits.unit_test_required）

覆盖：
① off（未启用）→ select 返回 meta=None，不产生 cf。
② runner-up：给定已知 E 的候选池，alt = 决策时点第 2 名，delta = E_chosen − E_alt。
③ 无泄漏：cf 用『select 时点』的 E；其后 _commit 更新 E 不影响已捕获的 cf。
④ shuffle：shuf 臂仍逐条产出 cf（预测基于打乱后的 E）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import response_model as rm_mod

PASS = 0
FAIL = 0


def check(desc, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {desc}")
    else:
        FAIL += 1
        print(f"  ✗ {desc} {extra}")


def cfg(enabled=True, shuffle=False, alpha=0.5, half_life_days=1e6):
    return {"response_model": {"enabled": enabled, "shuffle": shuffle,
                               "window_seconds": 60.0, "half_life_days": half_life_days,
                               "ema_alpha": alpha}}


def case1_disabled():
    print("\n[①] off（未启用）→ 无 cf")
    rm = rm_mod.ResponseModel(cfg(enabled=False))
    text, meta = rm.select([("a", 1.0), ("b", 0.5)], "a")
    check("disabled：返回 winner 且 meta 为 None", text == "a" and meta is None)


def case2_runnerup():
    print("\n[②] runner-up = 决策时点第 2 名")
    rm = rm_mod.ResponseModel(cfg())
    rm.E = {"a": 3.0, "b": 2.0, "c": 0.5}
    text, meta = rm.select([("a", 1.0), ("b", 0.9), ("c", 0.8)], "a")
    cf = meta["cf"]
    check("chosen = E 最大者", text == "a")
    check("alt = E 第 2 名", cf["alt"] == "b", f"got {cf['alt']}")
    check("delta = E_chosen − E_alt", abs(cf["delta"] - 1.0) < 1e-9, f"got {cf['delta']}")


def case3_no_leak():
    print("\n[③] 无泄漏：cf 取 select 时点 E，不随后续 _commit 改变")
    rm = rm_mod.ResponseModel(cfg(alpha=1.0, half_life_days=1e6))
    rm.E = {"a": 3.0, "b": 2.0}
    _, meta = rm.select([("a", 1.0), ("b", 0.9)], "a")
    d1 = meta["cf"]["delta"]
    rm.note_vocal(0.0, "a")
    for t in range(1, 60):          # 窗口内大量言语 → 观测极高
        rm.advance_clock(1.0, float(t), 5)
    rm.note_vocal(70.0, "b")        # 触发 _commit，E[a] 被改写
    check("cf.delta 保持 select 时点的值", meta["cf"]["delta"] == d1, f"{meta['cf']['delta']} vs {d1}")
    check("E[a] 确实被事后更新了（证明测试有效）", rm.E["a"] != 3.0, f"E[a]={rm.E['a']}")


def case4_shuffle():
    print("\n[④] shuffle：仍逐条产出 cf")
    rm = rm_mod.ResponseModel(cfg(shuffle=True))
    rm.E = {"a": 3.0, "b": 2.0, "c": 0.5}
    text, meta = rm.select([("a", 1.0), ("b", 0.9), ("c", 0.8)], "a")
    check("shuf：select 仍返回 meta 且含 cf", meta is not None and meta.get("cf") is not None)


def case5_tie():
    print("\n[⑤] E 全等（冷启动）→ cf 仍给出 delta=0")
    rm = rm_mod.ResponseModel(cfg())
    rm.E = {}
    text, meta = rm.select([("a", 1.0), ("b", 0.9)], "a")
    cf = meta.get("cf")
    check("tie：cf 存在且 delta=0", cf is not None and cf["delta"] == 0.0)


if __name__ == "__main__":
    print("=" * 60)
    print("P15 counterfactual 单测")
    print("=" * 60)
    case1_disabled()
    case2_runnerup()
    case3_no_leak()
    case4_shuffle()
    case5_tie()
    print("\n" + "=" * 60)
    print(f"结果：{PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)
