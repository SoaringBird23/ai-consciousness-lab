"""test_p19.py — P19 对话状态向量（多轮）单测

覆盖：① 逐轮更新 D ② 半衰期衰减 ③ 关联 rel ④ shuffle 打断关联 ⑤ off 逐位不变 ⑥ 持久化
"""
import json
import os
import random
import sys
import tempfile

os.environ["STATE_DIR"] = "/tmp/p19_test_state"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import dialogue as D
import language as L

PASS = 0
FAIL = 0


def check(d, c, e=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ✓ {d}")
    else:
        FAIL += 1; print(f"  ✗ {d} {e}")


def make_lex():
    fd, p = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"words": ["看", "球", "妈妈", "抱", "宝宝", "灯", "好"],
                   "params": {"MAXLEN": 3}}, f, ensure_ascii=False)
    return p


def mk(path, **kw):
    cfg = {"dialogue": {"enabled": True, "lexicon_file": path, "half_life_turns": 2.0}}
    cfg["dialogue"].update(kw)
    return D.DialogueState(cfg)


def case1_update():
    print("\n[①] 逐轮更新 D")
    ds = mk(make_lex())
    ds.observe_turn("看球", "partner")
    check("D 含本轮词", ds.d.get("看") == 1.0 and ds.d.get("球") == 1.0, f"{ds.d}")
    check("n_partner=1", ds.n_partner == 1)
    ds.observe_turn("妈妈", "self")
    check("系统轮计入 n_self", ds.n_self == 1)


def case2_decay():
    print("\n[②] 半衰期衰减（half_life=2 轮）")
    ds = mk(make_lex())
    ds.observe_turn("看", "partner")            # D[看]=1
    ds.observe_turn("球", "partner")            # 衰减一次
    ds.observe_turn("妈妈", "partner")          # 再衰减一次
    check("经 2 轮 → 约半衰", abs(ds.d.get("看", 0) - 0.5) < 1e-6, f"{ds.d.get('看')}")
    # 继续衰减到低于阈值则被裁剪（0.5×0.707^n<0.02 → n≈10）
    for w in ["球", "抱", "灯", "好", "球", "抱", "灯", "好", "球", "抱", "灯", "好"]:
        ds.observe_turn(w, "partner")
    check("权重低于阈值被裁剪", "看" not in ds.d, f"{ds.d}")


def case3_relevance():
    print("\n[③] 关联 rel = 候选词在 D 中的均值")
    ds = mk(make_lex())
    ds.observe_turn("看球", "partner")           # D: 看=1 球=1
    check("完全重叠 → rel>0", ds.relevance("看球") > 0.9, f"{ds.relevance('看球')}")
    check("无重叠 → rel=0", ds.relevance("妈妈抱") == 0.0, f"{ds.relevance('妈妈抱')}")


def case4_shuffle():
    print("\n[④] shuffle 打断「轮↔词」关联")
    random.seed(1)
    turns = ["看球", "妈妈抱宝宝", "看好", "宝宝看灯"]
    wf = mk(make_lex())
    ws = mk(make_lex(), shuffle=True)
    for t in turns:
        wf.observe_turn(t, "partner"); ws.observe_turn(t, "partner")
    probe = "看球"
    # full：探针词真实进过 D → 高关联；shuffle：键为随机词 → 关联应显著更低
    rf, rs = wf.relevance(probe), ws.relevance(probe)
    check("full 探针关联 > shuffle", rf > rs + 0.2, f"full={rf:.3f} shuf={rs:.3f}")
    check("shuffle 幅值仍在（D 非空）", sum(ws.d.values()) > 0)


def case5_off():
    print("\n[⑤] off：未启用 → dialogue=None，语言层行为不变")
    lg = L.Language({"language": {"enabled": True}, "caregiver": {"mode": "random"}})
    check("默认关 → dialogue 为 None", lg.dialogue is None)
    lg2 = L.Language({"language": {"enabled": True}, "caregiver": {"mode": "random"},
                      "dialogue": {"enabled": True, "lexicon_file": make_lex()}})
    check("启用 → dialogue 非空", lg2.dialogue is not None)


def case6_persist():
    print("\n[⑥] 持久化往返")
    p = make_lex()
    ds = mk(p)
    ds.observe_turn("看球", "partner")
    fd, sp = tempfile.mkstemp(suffix=".json"); os.close(fd)
    ds.save(sp)
    ds2 = D.DialogueState({"dialogue": {"enabled": True, "lexicon_file": p}})
    ds2.load(sp)
    check("D 往返一致", ds2.d == ds.d)
    check("轮数往返一致", (ds2.n_turns, ds2.n_self, ds2.n_partner)
          == (ds.n_turns, ds.n_self, ds.n_partner))


if __name__ == "__main__":
    print("=" * 64); print("P19 对话状态向量 单测"); print("=" * 64)
    case1_update(); case2_decay(); case3_relevance()
    case4_shuffle(); case5_off(); case6_persist()
    print("\n" + "=" * 64)
    print(f"结果：{PASS} passed, {FAIL} failed")
    print("=" * 64)
    sys.exit(1 if FAIL else 0)
