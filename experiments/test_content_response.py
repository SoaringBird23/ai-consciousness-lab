"""test_content_response.py — P14b 预注册审计用例

对应 prereg_P14b_content_sensitive_caregiver.json → audits.unit_test_required：
  ① content_response 关闭时 _vocal_response_prob == vocal_response_prob（与 P14 逐位一致）
  ② 映射生成确定性（同 seed 两次一致；冻结文件 sha 可复算）
  ③ r(HIGH)=0.9 / r(LOW)=0.1 生效（构造性：固定条件下实测应答率）
  （④ off 臂选择恒等于检索胜者 → 由 experiments/test_response_model.py 覆盖）

运行：./venv/bin/python experiments/test_content_response.py
"""
import importlib.util
import json
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

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


def load_language():
    spec = importlib.util.spec_from_file_location("language", os.path.join(ROOT, "language.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def base_config(content=True, map_file=None):
    lang_cfg = {"enabled": True, "evoke_threshold": 0.72}
    cg = {"mode": "contingent", "speech_per_hour_quiet": 0.0,
          "speech_prob_with_event": 0.0, "self_directed_prob": 0.0,
          "vocal_response_prob": 0.7}
    if content:
        cg["content_response"] = {"enabled": True, "map_file": map_file, "default_r": 0.5}
    return {"language": lang_cfg, "caregiver": cg}


def case1_disabled_identity(LANG):
    print("\n[①] content_response 关闭 → 应答概率恒为 vocal_response_prob")
    lang = LANG.Language(base_config(content=False))
    check("enabled=False", lang.content_response_enabled is False)
    for w in ["看", "睡吧", "不存在的词", ""]:
        check(f"p({w!r}) == vocal_response_prob",
              lang._vocal_response_prob(w) == lang.vocal_response_prob,
              f"got {lang._vocal_response_prob(w)}")


def case2_map_determinism(LANG):
    print("\n[②] 映射生成确定性（与冻结文件一致）")
    pools = (LANG.CORPUS_EVENT + LANG.CORPUS_NIGHT + LANG.CORPUS_DAY
             + LANG.CORPUS_SELF + LANG.FP_SOOTHE)
    types = sorted(set(pools))
    n = len(types)
    def gen():
        t = list(types)
        random.Random(1401).shuffle(t)
        k = (n + 1) // 2
        return {x: ("HIGH" if i < k else "LOW") for i, x in enumerate(t)}
    g1, g2 = gen(), gen()
    check("两次生成一致", g1 == g2)
    frozen_path = os.path.join(ROOT, "experiments", "p14b_content_map.json")
    if os.path.exists(frozen_path):
        frozen = json.load(open(frozen_path, encoding="utf-8"))
        check("冻结文件的 classes 与复算一致", frozen.get("classes") == g1)
        check("冻结 n_high/n_low 一致",
              frozen.get("n_high") == sum(v == "HIGH" for v in g1.values())
              and frozen.get("n_low") == n - sum(v == "HIGH" for v in g1.values()))
    else:
        print("  (冻结文件不存在，跳过一致性检查)")


def case3_high_low_rates(LANG):
    print("\n[③] HIGH≈0.9 / LOW≈0.1 生效（构造性实测应答率）")
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump({"r": {"HI": 0.9, "LO": 0.1}}, tmp)
    tmp.close()
    try:
        lang = LANG.Language(base_config(content=True, map_file=tmp.name))
        check("映射已载入", lang.content_r == {"HI": 0.9, "LO": 0.1}, f"{lang.content_r}")
        check("p(HI)=0.9", lang._vocal_response_prob("HI") == 0.9)
        check("p(LO)=0.1", lang._vocal_response_prob("LO") == 0.1)
        check("未知词回退 default=0.5", lang._vocal_response_prob("???") == 0.5)

        # 只留发声通道：其它通道全部置 0（quiet=0/event=0/自我指向=0），状态低张力低无聊
        state = [0.5, 0.0, 0.1, 0.2, 0.3, 0.0, 0.0, 0.1]   # s4=0.2, s8=0.1
        def rate(word, N=4000):
            random.seed(20261011)
            hits = 0
            for _ in range(N):
                lang._vocal_win_active = False
                lang._vocal_responded = False
                r = lang.caregiver_speaks(0.05, 12.0, False, state_vec=state,
                                          asleep=False, salience=0.0,
                                          vocal_recent=True, vocal_text=word)
                if r is not None:
                    hits += 1
            return hits / N
        r_hi = rate("HI")
        r_lo = rate("LO")
        print(f"    实测应答率：HI={r_hi:.3f}  LO={r_lo:.3f}")
        check("HI 应答率≈0.9（±0.05）", abs(r_hi - 0.9) < 0.05, f"got {r_hi:.3f}")
        check("LO 应答率≈0.1（±0.05）", abs(r_lo - 0.1) < 0.05, f"got {r_lo:.3f}")
    finally:
        os.unlink(tmp.name)


def case4_burst(LANG):
    print("\n[④] P14c 短爆：HIGH 词一次窗口回 k 句，LOW 词不短爆")
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump({"r": {"HI": 0.95, "LO": 0.05}}, tmp)
    tmp.close()
    try:
        cfg = base_config(content=True, map_file=tmp.name)
        cfg["caregiver"]["content_response"]["burst_high_k"] = 3
        lang = LANG.Language(cfg)
        state = [0.5, 0.0, 0.1, 0.2, 0.3, 0.0, 0.0, 0.1]
        random.seed(7)
        hi_resp, hi_ok = 0, True
        for _ in range(3000):
            lang._vocal_win_active = False
            lang._vocal_responded = False
            r = lang.caregiver_speaks(0.05, 12.0, False, state_vec=state, asleep=False,
                                      salience=0.0, vocal_recent=True, vocal_text="HI")
            if r is not None:
                hi_resp += 1
                if len(lang.drain_burst()) != 2:      # k-1 = 2 条补充
                    hi_ok = False
        lo_burst = 0
        for _ in range(3000):
            lang._vocal_win_active = False
            lang._vocal_responded = False
            lang.caregiver_speaks(0.05, 12.0, False, state_vec=state, asleep=False,
                                  salience=0.0, vocal_recent=True, vocal_text="LO")
            lo_burst += len(lang.drain_burst())
        check("HIGH 有回应时短爆恰为 2 句", hi_resp > 0 and hi_ok, f"resp={hi_resp} ok={hi_ok}")
        check("LOW 从不短爆", lo_burst == 0, f"lo_burst={lo_burst}")
    finally:
        os.unlink(tmp.name)


if __name__ == "__main__":
    print("=" * 60)
    print("P14b/P14c content_response 单测（预注册 audits.unit_test_required）")
    print("=" * 60)
    LANG = load_language()
    case1_disabled_identity(LANG)
    case2_map_determinism(LANG)
    case3_high_low_rates(LANG)
    case4_burst(LANG)
    print("\n" + "=" * 60)
    print(f"结果：{PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)
