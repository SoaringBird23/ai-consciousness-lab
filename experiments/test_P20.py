#!/usr/bin/env python3
"""P20 构造语法冒烟测试：切词、句式学习、理解、问句回答、词法纯净。"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import constructions as C  # noqa: E402

CORPUS = [
    "这是苹果", "这是三角形", "这是紫颜色", "这是小狗", "那是狮子",
    "小狗在睡觉", "小狗在上面", "小狗在下面", "妈妈去外面了", "妈妈去学校了",
    "我喜欢小狗", "我喜欢拼图", "你陪我", "我陪你", "你叫什么名字",
    "乌龟在睡觉", "乌龟在动", "我长大了", "今天天气晴", "今天天气冷",
    "苹果在哪里", "苹果在上面", "苹果在下面", "这是什么形状", "这是什么颜色",
    "你在做什么", "我在玩", "它在干什么", "它在洗澡", "你真棒", "谢谢",
    "我很难过", "不哭哦", "好吗", "好不好", "是不是", "对不对",
]


def build():
    g = C.ConstructionGrammar(os.path.join(ROOT, "corpus", "lexicon.json"))
    for t in CORPUS:
        g.learn(t, state=[0.5] * 8, world=0.5)
    g.finalize(min_n=1, min_fillers=1, min_literal=1)
    return g


def main():
    g = build()
    assert g.tok.segment("苹果在哪里") == ["苹果", "在", "哪里"]
    assert g.tok.segment("这是什么") == ["这", "是", "什么"]
    assert g.frames, "no constructions learned"
    rng = random.Random(0)
    state, world = [0.5] * 8, 0.5

    und = g.understand("小狗在哪里", state=state)
    assert und["speech_act"] == "wh_question", und["speech_act"]
    assert und["coverage"] == 1.0, und["coverage"]

    und2, gen2 = g.respond("你陪我好不好", state=state, world=world, rng=rng)
    assert und2["speech_act"] == "yesno_question"
    assert gen2 and gen2["tokens"][0] in ("我", "嗯"), gen2

    for q in ("这是什么", "小狗在哪里", "这是什么形状", "你叫什么名字",
              "它在干什么", "你是谁", "你真棒"):
        und, gen = g.respond(q, state=state, world=world, rng=rng)
        assert gen is not None, q
        assert all(w in g.word_count for w in gen["tokens"]), (q, gen)
        assert not any(w in C.WH_WORDS for w in gen["tokens"]), (q, gen)
        assert "".join(gen["tokens"]) != q
    print("P20 smoke tests passed "
          f"(frames={len(g.frames)}, words={len(g.word_count)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
