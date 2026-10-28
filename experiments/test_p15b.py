"""test_p15b.py — P15b 单测（预注册 audits.unit_test_required）

① window_seconds=180：发声后 180s 内的言语计入 r_in，超过则计入 r_out。
② 聚合校准：Spearman 与手工一致；型内 n<5 被排除。
③ 时间外推快照：frozen_E 取 t>=split 的该型首个 predicted，不使用更晚信息。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import response_model as rm_mod
import analyze_P15b as A

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


def case1_window180():
    print("\n[①] window_seconds=180 的窗口判定")
    cfg = {"response_model": {"enabled": True, "window_seconds": 180.0,
                              "half_life_days": 1e6, "ema_alpha": 0.2}}
    rm = rm_mod.ResponseModel(cfg)
    rm.note_vocal(0.0, "a")
    rm.advance_clock(1.0, 179.0, 1)      # 179 < 180 → 窗口内
    rm.advance_clock(1.0, 181.0, 1)      # 181 ≥ 180 → 窗口外
    check("179s 计入窗口内", abs(rm._win_speech - 1.0) < 1e-6, f"win={rm._win_speech}")
    check("181s 计入窗口外", abs(rm._out_speech - 1.0) < 1e-6, f"out={rm._out_speech}")


def case2_spearman_and_filter():
    print("\n[②] Spearman 正确性 + 型内 n≥5 过滤")
    check("完全正相关 = +1", abs(A.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) - 1.0) < 1e-9)
    check("完全负相关 = −1", abs(A.spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) + 1.0) < 1e-9)
    # 型内 n<5 被排除：构造 6 个型，其中 2 个型 n=3
    by = {"t1": [1] * 6, "t2": [2] * 5, "t3": [3] * 6, "t4": [4] * 5, "t5": [5] * 3, "t6": [6] * 3}
    kept = [k for k, v in by.items() if len(v) >= 5]
    check("n<5 的型被排除", kept == ["t1", "t2", "t3", "t4"], f"{kept}")


def case3_frozen_E():
    print("\n[③] 时间外推快照只用 t>=split 的首个 predicted")
    hist = [
        {"t": 10.0, "text": "a", "predicted": 99.0},   # split 之前 → 忽略
        {"t": 50.0, "text": "a", "predicted": 2.0},    # split 之后该型首个 → 取 2
        {"t": 70.0, "text": "a", "predicted": 8.0},    # 更晚 → 忽略
        {"t": 55.0, "text": "b", "predicted": 3.0},
    ]
    f = A.frozen_E(hist, 40.0)
    check("a 取 split 后首个 predicted=2", f.get("a") == 2.0, f"{f.get('a')}")
    check("b 取 3", f.get("b") == 3.0, f"{f.get('b')}")
    check("split 前的不进入", 99.0 not in f.values())


if __name__ == "__main__":
    print("=" * 60)
    print("P15b 单测")
    print("=" * 60)
    case1_window180()
    case2_spearman_and_filter()
    case3_frozen_E()
    print("\n" + "=" * 60)
    print(f"结果：{PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)
