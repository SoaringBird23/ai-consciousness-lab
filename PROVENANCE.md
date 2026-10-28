# 归属与优先权证据链

本文件的作用：**在缺少机构背书与外部时间戳的情况下，把"这份工作是谁、什么时候做的"变成可验证的事实。**

作者：**Chengze Luo（罗承泽）**，ORCID [0009-0007-3316-6292](https://orcid.org/0009-0007-3316-6292)，独立研究者。
见 [AUTHORS.md](AUTHORS.md)。

---

## 一、本仓库主张什么（也只主张这些）

1. 本仓库所载的**系统设计、41 份预注册、30 份结果、20 个分析器、10 组单测、全部阴性结果**，
   由 Chengze Luo 独立完成，时间跨度见下方证据链。
2. 其中被认为最具优先权价值的一条是：
   **「一个非 LLM、零生成的发育系统，其全局工作空间是只读的」**
   —— 即广播可被下游读到（念头改变目标与自我表征），但**念头不能改写产生它的自身状态**；
   且该结论经 **6 轮独立加码**（通道先证明为活 → 换被消费变量 → 耦合提到 1.99σ → 全池候选 →
   念—念真值图 + 学习/使用相位分离）后仍然成立。
3. **不主张**：系统有意识；不主张任何现象学结论；不主张"第一"以外的排他性
   —— 见第五节，同期已有独立工作落在相邻位置，本文的差异是被明确划界的，不是被隐去的。

---

## 二、证据链（5 层，由内到外）

### 第 1 层：预注册文件的内部冻结时间

每份 `experiments/prereg_*.json` 含 `created` 字段，写于**采集数据之前**。
最早：`2026-10-05 10:55`（`prereg_E1E2.json`）；最新：`prereg_P19b.json`（2026-10-15）。
带时戳的预注册共 **37** 份。

这一层的关键性质：预注册先于结果存在，且**判据在结果出现后未回溯修改**
（例外必以 `amendment` / `methods_note` 显式记录，可从文件内检索）。

### 第 2 层：预注册与结果的成对哈希

下表的哈希是本仓库提交时的内容指纹，用于证明「现在看到的判据 = 当时冻结的判据」。

| 主张 | 预注册 | 结果 | 结果日期 | 结果 sha256[:16] |
|---|---|---|---|---|
| 只读工作空间（首次钉定） | `prereg_R2.json` | `results_R2_overlap.json` | 2026-10-07 | `096eb13917db67cf` |
| 只读·剂量加码 | `prereg_R2x.json` | —（并入 R2 阶梯） | 2026-10-10 | `c90599b23d56ebc6` |
| 念头—念头工作空间 | `prereg_P13.json` | `results_P13.json` | 2026-10-10 | `6557c9e5b01a36fc` |
| 意图选择（正结果） | `prereg_P14c.json` | `results_P14c.json` | 2026-10-11 | `8cec212ea3d51e63` |
| 指称落地 | `prereg_P16.json` | `results_P16.json` | 2026-10-13 | `33068f141c0dd1f6` |
| 词级组合 | `prereg_P18.json` | `results_P18.json` | 2026-10-14 | `bfe016f90472bd33` |
| 对话状态向量 | `prereg_P19.json` | `results_P19.json` | 2026-10-15 | `7e6ddd3dd86cd971` |

验证方式（任何人在任何机器上可复算）：

```bash
cd ai-consciousness-lab
python3 - <<'PY'
import hashlib
for p in ["experiments/results_R2_overlap.json","experiments/results_P13.json",
          "experiments/results_P14c.json","experiments/results_P16.json",
          "experiments/results_P18.json","experiments/results_P19.json"]:
    print(p, hashlib.sha256(open(p,'rb').read()).hexdigest()[:16])
PY
```

### 第 3 层：全量产物清单

`MANIFEST.sha256` 记录仓库内全部追踪文件的哈希。任何人可用
`shasum -a 256 -c MANIFEST.sha256` 校验整份记录未被改动。

### 第 4 层：git 提交与附注标签

**必须声明的限制**：本仓库的 git 历史于 `2026-10-06` 一次性建立，因此
**git 提交时间不能作为"更早想到"的证据**，它只证明"此内容在某次提交时已存在"。
真正的先后顺序由第 1、2 层（预注册内部时间戳 + 文件哈希）承担。

为补强这一点，本仓库使用**已签名的附注标签（signed annotated tag）**把作者身份绑定到内容：

| 项 | 值 |
|---|---|
| 标签 | `v0.2.0`（annotated + SSH 签名） |
| 标签对象 | `refs/tags/v0.2.0` |
| 签名密钥 | `ssh-ed25519`，指纹 `SHA256:tGWNy0MdB8XzbeZyWGnpoqEhrQHKaEgsCPk0GYOtENs` |
| 公钥 | `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIO++zQk244iHGKdUIBOnmjSq2/WuNCKvsO/mHuE6ZpqH` |

第三方验证方式（无需信任本仓库的任何陈述）：

```bash
printf 'chengze ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIO++zQk244iHGKdUIBOnmjSq2/WuNCKvsO/mHuE6ZpqH\n' > /tmp/allowed_signers
git -c gpg.ssh.allowedSignersFile=/tmp/allowed_signers verify-tag v0.2.0
# 期望：Good "git" signature for chengze with ED25519 key SHA256:tGWNy0MdB8XzbeZyWGnpoqEhrQHKaEgsCPk0GYOtENs
```

### 第 5 层：外部时间戳（**已成立**）

| 锚点 | 状态 |
|---|---|
| 公开代码仓库 | ✅ `https://github.com/SoaringBird23/ai-consciousness-lab`（2026-10-28） |
| 签名标签被 GitHub 托管 | ✅ `v0.2.0`，验签方法与第六节一致 |
| **归档 DOI（Zenodo）** | ✅ **`10.5281/zenodo.23728049`**（版本 DOI，归档时间 2026-10-28T10:54:18Z） |
| 概念 DOI（指向所有版本） | ✅ `10.5281/zenodo.23728048` |
| arXiv 编号 | ❌ 仍缺（需 endorsement，未提交） |

Zenodo 记录中的作者字段由**第三方机构**登记，不依赖本仓库的自述：

```
Luo, Chengze · ORCID 0009-0007-3316-6292 · Independent Researcher
```

归档包为 `SoaringBird23/ai-consciousness-lab-v0.2.0.zip`（12,213,719 字节），
与 `isSupplementTo` 关联到 GitHub 的 `tree/v0.2.0`。

**一个必须说明的技术事实**：归档快照是 `v0.2.0` 标签的内容，
**不包含**本次 DOI 回填（因为一个版本无法包含它自己的 DOI）。这是所有归档发布的通例，
不是遗漏。读到这份文件的人，若想确认归档内容与当前内容的关系，比对 `MANIFEST.sha256` 即可。

**优先权的表述因此可以升级为**：截至 `2026-10-28`（Zenodo 归档时间），
作者已以预注册、内容哈希、签名标签与第三方归档 DOI 四层证据，固定了这一记录。
但**仍不得**表述为"首次发表"——arXiv 未上、未经同行评审，
且第六节列出的同期工作在本记录之前已获得外部时间戳。

---

## 三、为什么需要这份文件

独立研究者最常见的失败不是做错，而是**做了但无法证明是自己做的、何时做的**。
本项目的核心结论是**阴性**的（"它推不动自己"），阴性结果尤其容易被后来者独立重做后
当作自己的发现。因此：

- **判据先于数据**（预注册）→ 排除"事后挑指标"；
- **内容哈希**→ 排除"事后改判据"；
- **外部时间戳**→ 排除"时间上可有可无"。

三者缺一，阴性结果就没有优先权，只有参考价值。

---

## 四、克隆者/引用者须知

- 若你基于本仓库的**判据设计**做实验，请引用本仓库与论文（见 `CITATION.cff`）。
- 若你复现出**不同**结论，这非常有价值 —— 请把预注册与结果一起公开，
  本项目对"被推翻"的欢迎程度高于对"被赞同"的期待（见论文 Limitations）。
- 请**不要**把本仓库的阴性结果表述为"该系统没有工作空间"：
  本仓库证明的是**写回通道不承重**（read-only），不是**没有广播**（broadcast 是成立的）。

---

## 五、同期独立工作（明确的划界，非回避）

提交本记录时检索到以下工作落在相邻位置。它们**先于**本仓库获得外部时间戳，
因此本仓库**不主张**在这些方向上的优先权，只主张下述差异：

| 工作 | 位置 | 与本仓库的关系 |
|---|---|---|
| Wender, *Preregistered Somatic-Marker Ablation…: A Negative Result on the Verbal-Output Axis* | [Zenodo 10.5281/zenodo.21218491](https://zenodo.org/records/21218491)，发布 2026-08-30 | **结论同型**（内部状态对言语输出不承重），且**先发布**。差异：其输出面是前沿 LLM，作者自陈该混淆是最致命缺口；本仓库无 LLM 在回路内 |
| Chevalier, *KAINE: A Continuously Running Predictive Global Workspace* | [Zenodo 10.5281/zenodo.21348144](https://zenodo.org/records/21348144)，2026-07-14 | 同样做**预注册的工作空间中介消融**。差异：其问的是「有无工作空间是否承重」，本仓库问的是「工作空间**可不可写**」 |
| Liu, *Self-Emergence Agent Architecture* | [arXiv:2609.17331](https://arxiv.org/abs/2609.17331)，2026-09-15 | 自我涌现（HMM 行为惯性 + 反身元认知 + 社会对比）。差异：其自我由 HMM 参数与多智能体对比生成；本仓库的自我由**检索竞争**在给定语料上长出 |
| Vera, *Lexical Consensus: Grounded Word Learning…* | [arXiv:2606.22207](https://arxiv.org/abs/2606.22207)，2026-06-20 | 接地词学习，严谨度高于本仓库的 P16。差异：其用冻结视觉嵌入做感知—语义解离；本仓库用二值世界场，**明确更弱**（见论文 Limitations） |
| Niazi, *Beyond mimicry…（mPCAB）* | [Front. Artif. Intell. 8:1686752](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1686752/xml)，2026-01-12 | 跨基底指标电池（扰动复杂度 / 全局工作空间 / 规范内化 / 能动性）。本仓库的 D1–D6 与之的对照及**未实现项**见 [docs/indicator_mapping.md](docs/indicator_mapping.md) |

---

## 六、若要挑战本记录

请针对以下任一具体点，本仓库承诺以同样的公开方式回应：

1. 复算第 2 层的哈希，指出与 `MANIFEST.sha256` 不符之处；
2. 指出某份 `results_*.json` 的判据与对应 `prereg_*.json` 冻结判据不一致且未标 `amendment`；
3. 指出某条"阴性"实际源于**机制未执行**（本项目历史上发生过 4 次，均已修正并记录
   —— 见 `docs/项目手册.html` §5 复盘）；
4. 指出 D6 的加码阶梯仍不足以排除"通道太弱"这一替代解释。

---

## 七、签名（已完成，第三方可独立验证）

标签 `v0.2.0` 已用本机 SSH 密钥签名并推送至公开仓库。任何人可复验，无需信任本文档：

```bash
git clone https://github.com/SoaringBird23/ai-consciousness-lab
cd ai-consciousness-lab

# 1) 内容未被改动
shasum -a 256 -c MANIFEST.sha256

# 2) 标签由该作者的密钥签发
printf 'chengze ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIO++zQk244iHGKdUIBOnmjSq2/WuNCKvsO/mHuE6ZpqH\n' > /tmp/allowed_signers
git -c gpg.ssh.allowedSignersFile=/tmp/allowed_signers verify-tag v0.2.0
```

两步都通过，说明：**清单 → 内容未改；签名 → 标签由该密钥签发。**

一条必须说清的边界：签名绑定的是**密钥**，不是法律身份。密钥与 ORCID 的对应
关系由作者在 ORCID 记录与仓库 README 中声明 —— 这一环是**信任假设**，不是密码学保证。
