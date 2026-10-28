"""analyze_R2_overlap.py —— R2 逐 tick 检索重合率（离线分析，不改系统）

背景：R2 的四个行为指标（检索率 / 多样性 / 自我模型 / 目标）都可能对
"检索成分被改变"不敏感——rate 只看条数、diversity 太粗、self-model 要跨
字符差阈值、goals 要跨 20% 占比。于是"扰动逐 tick 改变了它正在想什么，但
四个指标一个都不动"这一混淆无法排除。

本脚本直接测成分：把每条扰动臂的检索序列与对照臂 ctl_none 按仿真 tick
对齐（各臂同父，tick 网格相同），计算
  - 双方同一 tick 都有检索时，命中"同一短语"的比例
  - 命中"同一记忆条目"（text + heard_at 指纹）的比例
  - 检索事件集合的 Jaccard 重合
  - 首个分歧 tick（text 不同、或只有一方有检索）
  - 置换基线：把臂的短语在共同 tick 上打乱后重算命中率（控制"词汇表
    本身高度偏斜导致的高偶然命中"）

判读：命中率 ≈ 1 且远高于置换基线 → "无影响"成立，指标不敏感不是问题；
      命中率显著低于 1（或与基线无异）→ 扰动改变了检索成分，四个指标的
      "nothing moved" 是测量盲区，而非结论。

输入：state_exp/inner_speech.jsonl（fork 点长度，用于剔除继承历史）
      state_R2_{ctl_none,dead_gate,open_dead_target,open_s4_lo,open_s4_mid,open_s4_hi}/inner_speech.jsonl
输出：打印对齐表；--json 时另写 experiments/results_R2_overlap.json
"""
import json
import os
import random
import sys

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARMS = ["dead_gate", "open_dead_target", "open_s4_lo", "open_s4_mid", "open_s4_hi"]
N_PERM = 2000


def _jsonl(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def window_map(state, n_inherit):
    """{t: (text, heard_at)}，仅实验窗口内 type=retrieval 的记录。"""
    out = {}
    for r in _jsonl(os.path.join(LAB, state, "inner_speech.jsonl"))[n_inherit:]:
        if r.get("type") == "retrieval":
            out[r["t"]] = (r.get("text"), round(float(r.get("heard_at", -1.0)), 1))
    return out


def main():
    n_inherit = len(_jsonl(os.path.join(LAB, "state_exp", "inner_speech.jsonl")))
    ctl = window_map("state_R2_ctl_none", n_inherit)

    print("R2 逐 tick 检索重合率（对照 = ctl_none，继承前缀 %d 条已剔除）" % n_inherit)
    print("对照窗口内检索 = %d 条" % len(ctl))
    print()
    hdr = ("%-18s %6s %6s %7s %9s %9s %9s %8s"
           % ("arm", "n_arm", "n_comm", "phrase%", "entry%", "perm%", "jaccard", "first_div"))
    print(hdr)
    print("-" * len(hdr))

    results = {"control": "ctl_none", "n_inherit": n_inherit,
               "n_control_window_retrievals": len(ctl),
               "permutations": N_PERM, "arms": {}}
    rng = random.Random(0)

    for arm in ARMS:
        m = window_map("state_R2_" + arm, n_inherit)
        common = sorted(set(ctl) & set(m))
        if not common:
            print("%-18s %6d %6d   (无共同 tick)" % (arm, len(m), 0))
            continue
        same_txt = sum(1 for t in common if ctl[t][0] == m[t][0])
        same_ent = sum(1 for t in common if ctl[t] == m[t])
        phrase = same_txt / len(common)
        entry = same_ent / len(common)

        # 置换基线：打乱臂在共同 tick 上的短语，重算命中率
        arm_txt = [m[t][0] for t in common]
        ctl_txt = [ctl[t][0] for t in common]
        hits = []
        for _ in range(N_PERM):
            rng.shuffle(arm_txt)
            hits.append(sum(1 for a, b in zip(ctl_txt, arm_txt) if a == b) / len(common))
        perm = sum(hits) / len(hits)

        jac = len(common) / len(set(ctl) | set(m))

        allt = sorted(set(ctl) | set(m))
        first = None
        for t in allt:
            a, b = ctl.get(t), m.get(t)
            if (a is None) != (b is None) or (a and b and a[0] != b[0]):
                first = t
                break

        first_s = ("%.1f" % first) if first is not None else "无分歧"
        print("%-18s %6d %6d %6.1f%% %8.1f%% %8.1f%% %9.3f %10s"
              % (arm, len(m), len(common), phrase * 100, entry * 100,
                 perm * 100, jac, first_s))
        results["arms"][arm] = {
            "n_arm_window_retrievals": len(m),
            "n_common_ticks": len(common),
            "phrase_agreement": phrase,
            "entry_agreement": entry,
            "permutation_baseline": perm,
            "phrase_agreement_over_baseline": (phrase / perm) if perm else None,
            "jaccard": jac,
            "first_divergence_t": first,
        }

    print()
    print("phrase%  = 共同 tick 上命中同一短语的比例")
    print("entry%   = 命中同一记忆条目（text+heard_at）的比例")
    print("perm%    = 置换基线（打乱短语后的偶然命中率）")
    print("jaccard  = 两臂检索事件集合的重合度 |∩|/|∪|")
    print("first_div= 首个分歧 tick（text 不同或单方缺失）")

    if "--json" in sys.argv:
        out = os.path.join(LAB, "experiments", "results_R2_overlap.json")
        with open(out, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        print("\n已写", out)


if __name__ == "__main__":
    main()
