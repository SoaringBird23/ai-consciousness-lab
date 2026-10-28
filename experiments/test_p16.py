"""test_p16.py — P16 semantics 单测（预注册 audits.unit_test_required）"""
import os
import random
import sys

# 必须在 import semantics 之前设置，避免污染真实 state/
os.environ["STATE_DIR"] = "/tmp/p16_test_state"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import semantics as sem_mod
import analyze_P16 as A

PASS = 0
FAIL = 0


def check(d, c, e=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ✓ {d}")
    else:
        FAIL += 1; print(f"  ✗ {d} {e}")


def case1_bind():
    print("\n[①] 指称表在线累加")
    s = sem_mod.Semantics({"semantics": {"enabled": True, "phi_threshold": 0.5}})
    for _ in range(3):
        s.bind("球", 0.9, 1.0)
    for _ in range(2):
        s.bind("球", 0.1, 1.0)
    check("HIGH 计数=3", s.table["球"][1] == 3, f"{s.table}")
    check("LOW 计数=2", s.table["球"][0] == 2, f"{s.table}")
    check("n_bind=5", s.n_bind == 5)


def case2_shuffle():
    print("\n[②] shuffle 破坏 w↔φ 关联")
    random.seed(1)
    s = sem_mod.Semantics({"semantics": {"enabled": True, "shuffle": True}})
    for _ in range(400):
        s.bind("球", 0.9, 1.0)          # 真实恒 HIGH；shuffle 后应被打散
    row = s.table["球"]
    frac_high = row[1] / (row[0] + row[1])
    check("shuffle 后 HIGH 占比≈0.5", 0.35 < frac_high < 0.65, f"{frac_high:.2f}")


def case3_decode():
    print("\n[③] 二值解码 acc 与理论一致")
    rows = []
    rng = random.Random(2)
    for _ in range(200):
        rows.append({"w": "球", "phi": 1})
        rows.append({"w": "灯", "phi": 0})
        rows.append({"w": "闲话", "phi": rng.randint(0, 1)})
    acc_world, n_world = A.decode_acc(rows, rows, A.WORLD)
    check("world 词可完美解码 → acc=1.0", acc_world == 1.0, f"{acc_world}")
    acc_rand, _ = A.decode_acc([r for r in rows if r["w"] == "闲话"],
                               [r for r in rows if r["w"] == "闲话"], None)
    check("纯随机词 acc≈0.5", acc_rand is not None and 0.35 < acc_rand < 0.65, f"{acc_rand}")


def case4_disabled():
    print("\n[④] 未启用 → 不产出")
    s = sem_mod.Semantics({"semantics": {"enabled": False}})
    s.bind("球", 0.9, 1.0)
    check("disabled：表为空", s.table == {} and s.n_bind == 0)


if __name__ == "__main__":
    print("=" * 60); print("P16 semantics 单测"); print("=" * 60)
    case1_bind(); case2_shuffle(); case3_decode(); case4_disabled()
    print("\n" + "=" * 60); print(f"结果：{PASS} passed, {FAIL} failed"); print("=" * 60)
    sys.exit(1 if FAIL else 0)
