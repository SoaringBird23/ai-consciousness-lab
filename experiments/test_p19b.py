"""test_p19b.py — P19b 发声习惯化 + 去回声 单测

覆盖：① 关闭时恒 1.0 ② 习惯化抑制 ③ 半衰期恢复 ④ 精确回声 ⑤ 近回声
     ⑥ shuffle 打断关联 ⑦ select 接入（penalty_fn=None 逐位不变）⑧ 持久化
"""
import json
import os
import random
import sys
import tempfile

os.environ["STATE_DIR"] = "/tmp/p19b_test_state"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import habituation as H
import response_model as RM

PASS = FAIL = 0


def check(d, c, e=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ✓ {d}")
    else:
        FAIL += 1; print(f"  ✗ {d} {e}")


def mk(**kw):
    cfg = {"habituation": {"enabled": True, "half_life_hours": 1.0, "strength": 0.8}}
    cfg["habituation"].update(kw)
    return H.Habituation(cfg)


def case_off():
    print("\n[①] 关闭时 penalty 恒 1.0")
    h = H.Habituation({"habituation": {"enabled": False}})
    for _ in range(50):
        h.note_spoken("对不对", 0)
    check("penalty=1.0", h.penalty("对不对", 0) == 1.0)


def case_hab():
    print("\n[②] 习惯化：说得越多，得分越低")
    h = mk()
    for i in range(5):
        h.note_spoken("对不对", 0)
    h.note_spoken("还好", 0)
    p_many, p_once = h.penalty("对不对", 0), h.penalty("还好", 0)
    check("高频句被抑制更多", p_many < p_once < 1.0, f"{p_many:.3f} vs {p_once:.3f}")
    check("5 次 ≈ 0.8^5", abs(p_many - 0.8 ** 5) < 1e-6, f"{p_many:.4f}")
    check("未说过 = 1.0", h.penalty("没说过", 0) == 1.0)


def case_decay():
    print("\n[③] 半衰期恢复（τ=1h）")
    h = mk()
    for _ in range(4):
        h.note_spoken("X", 0)
    p0 = h.penalty("X", 0)
    p1 = h.penalty("X", 3600)      # 1 个半衰期
    p2 = h.penalty("X", 7200)
    check("随时间回升", p0 < p1 < p2, f"{p0:.3f} < {p1:.3f} < {p2:.3f}")


def case_echo():
    print("\n[④⑤] 去回声 / 近回声")
    h = mk()
    pe = h.penalty("我在这儿", 0, partner_last="我在这儿")
    pn = h.penalty("看球", 0, partner_last="看球啊")
    pb = h.penalty("看球", 0, partner_last="妈妈")
    check("精确回声 ×0.15", abs(pe - 0.15) < 1e-9, f"{pe}")
    check("近回声 ×0.5", abs(pn - 0.5) < 1e-9, f"{pn}")
    check("无回声 = 1.0", pb == 1.0)


def case_shuffle():
    print("\n[⑥] shuffle 打断「说得多→被抑制」关联")
    random.seed(7)
    hf, hs = mk(), mk(shuffle=True)
    for _ in range(6):
        hf.note_spoken("A", 0); hs.note_spoken("A", 0)
    hf.note_spoken("B", 0); hs.note_spoken("B", 0)
    hf.note_spoken("C", 0); hs.note_spoken("C", 0)
    pf = hf.penalty("A", 0)
    ps = sum(hs.penalty("A", 0) for _ in range(400)) / 400.0
    check("full 对高频句抑制更强", pf < ps - 0.1, f"full={pf:.3f} shuf_mean={ps:.3f}")


def case_select():
    print("\n[⑦] select 接入")
    cfg = {"response_model": {"enabled": True}}
    rm = RM.ResponseModel(cfg)
    rm.E = {"A": 1.0, "B": 0.2}
    pool = [("A", 1.0), ("B", 0.9)]
    t0, _ = rm.select(pool, "A")
    check("penalty_fn=None → 仍选 E 最高的 A", t0 == "A", t0)
    t1, _ = rm.select(pool, "A", penalty_fn=lambda t: 0.01 if t == "A" else 1.0)
    check("抑制 A 后改选 B", t1 == "B", t1)


def case_persist():
    print("\n[⑧] 持久化往返")
    h = mk()
    for _ in range(3):
        h.note_spoken("看", 100.0)
    fd, p = tempfile.mkstemp(suffix=".json"); os.close(fd)
    h.save(p)
    h2 = mk(); h2.load(p)
    check("质量往返一致", abs(h2.penalty("看", 100.0) - h.penalty("看", 100.0)) < 1e-9)


if __name__ == "__main__":
    print("=" * 64); print("P19b 习惯化 + 去回声 单测"); print("=" * 64)
    case_off(); case_hab(); case_decay(); case_echo()
    case_shuffle(); case_select(); case_persist()
    print("\n" + "=" * 64); print(f"结果：{PASS} passed, {FAIL} failed"); print("=" * 64)
    sys.exit(1 if FAIL else 0)
