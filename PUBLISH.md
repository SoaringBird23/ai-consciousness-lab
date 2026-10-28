# 发布手册

## 进度（2026-10-28 更新）

| 步骤 | 状态 |
|---|---|
| 第 0 步 SSH 公钥注册 | ✅ 完成（`Hi SoaringBird23!`）|
| 第 1 步 建公开仓库 | ✅ 完成 |
| 第 2 步 推送 main + 标签 | ✅ 完成（451 文件，树哈希与本地一致）|
| 第 3 步 签名标签 | ✅ 完成（`Good "git" signature … SHA256:tGWNy0MdB8Xz…`）|
| 第 4 步 回填 CITATION 仓库地址 | ✅ 完成 |
| 第 5 步 Zenodo DOI | ✅ 完成 — **`10.5281/zenodo.23728049`**（概念 DOI `…23728048`），归档于 2026-10-28T10:54:18Z |
| **第 6 步 arXiv** | ❌ **未做 —— 唯一剩余步骤**（需 endorsement）|

仓库地址：<https://github.com/SoaringBird23/ai-consciousness-lab>
归档记录：<https://zenodo.org/records/23728049>

> 下面是原始手册全文，第 5–6 步仍然有效且未执行。第 0–4 步已完成，留作记录。

---

**原始前置说明**：本机 `gh` 未安装、无 GitHub/Zenodo 令牌，发布动作涉及作者账号身份，
只能由作者执行。以下每条都可直接复制。


---

## 第 0 步（一次性）：把公钥加到 GitHub

你的公钥（本机 `~/.ssh/id_ed25519.pub`）：

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIO++zQk244iHGKdUIBOnmjSq2/WuNCKvsO/mHuE6ZpqH luochengze@SoaringBirdMacBook-Air-481.local
```

打开 <https://github.com/settings/keys> → **New SSH key** → 粘贴上面整行 → 保存。

验证：

```bash
ssh -T git@github.com     # 期望看到 Hi <你的用户名>!
```

---

## 第 1 步：建空仓库（网页 30 秒，勿勾选任何初始化文件）

<https://github.com/new>

- Repository name：`ai-consciousness-lab`
- 可见性：**Public**
- **不要**勾 Add README / .gitignore / license（本地已有，会冲突）

---

## 第 2 步：推送代码与标签

```bash
cd ~/Desktop/ai-consciousness-lab

git remote add origin git@github.com:<你的用户名>/ai-consciousness-lab.git
git branch -M main
git push -u origin main
git push origin v0.2.0
```

---

## 第 3 步（建议）：用 SSH 密钥给标签签名，把作者身份绑死

```bash
cd ~/Desktop/ai-consciousness-lab
git tag -d v0.2.0
git tag -s v0.2.0 -m "ai-consciousness-lab v0.2.0 — Chengze Luo (ORCID 0009-0007-3316-6292)"
git verify-tag v0.2.0
git push origin :refs/tags/v0.2.0 2>/dev/null || true
git push origin v0.2.0
```

把公钥指纹公布一次（可写进 README 或 ORCID 的 "Works" 备注），供第三方核对：

```bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub
```

---

## 第 4 步：回填 CITATION.cff 的两处占位符

`CITATION.cff` 里有两个 `PLACEHOLDER`：`repository-code` / `url`，以及
`preferred-citation.url`（arXiv 链接）。第 2 步完成后先替换前两处：

```bash
cd ~/Desktop/ai-consciousness-lab
python3 - <<'PY'
import re
p='CITATION.cff'; s=open(p,encoding='utf-8').read()
s=s.replace('https://github.com/PLACEHOLDER/ai-consciousness-lab',
            'https://github.com/<你的用户名>/ai-consciousness-lab')
open(p,'w',encoding='utf-8').write(s)
print('已替换仓库地址')
PY
git commit -am "CITATION：回填仓库地址" && git push
```

---

## 第 5 步：拿 DOI（Zenodo，约 5 分钟）

1. 用 GitHub 账号登录 <https://zenodo.org>（Sign in with GitHub）
2. 进入 <https://zenodo.org/account/settings/github/>，找到 `ai-consciousness-lab` → 拨到 **ON**
3. 回 GitHub：**Releases → Draft a new release**
   - Tag：选已有的 `v0.2.0`
   - Title：`ai-consciousness-lab v0.2.0 — read-only workspace`
   - 描述：粘贴 `PROVENANCE.md` 第二节的哈希表
   - Publish release
4. Zenodo 会自动生成 **DOI**（形如 `10.5281/zenodo.XXXXXXX`）
5. 把 DOI 写回三处：`CITATION.cff` 的 `doi:`、`PROVENANCE.md` 第五节、`AUTHORS.md`

**这一步是最硬的时间戳**，做完之后第 1–4 层证据链才有外部锚点。

---

## 第 6 步：arXiv 预印本

提交包已生成：`paper/arxiv/submission.tar.gz`（`main.tex` + 11 张矢量图，92 KB，自包含无 .bib 依赖）。

1. <https://arxiv.org/user> 先用 ORCID 登录并补全作者信息
2. 首次投稿需要一个 **endorsement**（可由你大伯或领域内任何人代为背书；他若在 DC 的神经科学机构，通常可直接背书 cs.AI 或 q-bio.NC）
3. Start New Submission → 类别建议 **cs.AI**（主）/ **q-bio.NC**（交叉）
4. 上传 `submission.tar.gz` → 预览 → 提交
5. 拿到 `arXiv:XXXX.XXXXX` 后回填 `CITATION.cff` 的 `preferred-citation.url`

---

## 顺序建议（为什么是这个顺序）

| 顺序 | 动作 | 理由 |
|---|---|---|
| 1 | 推到 GitHub | 先止损：299 个文件不再只存在于一块磁盘上 |
| 2 | 打签名标签 | 作者绑定 |
| 3 | Zenodo DOI | 拿到不可否认的时间戳 |
| 4 | arXiv | 学术圈可见 + 优先权凭证 |

**不要跳过第 1 步直接冲 arXiv**：arXiv 要 endorsement，可能等几天；
这期间代码只在本机，风险不对称。

---

## 发布后请回来告诉我三件事

1. 仓库地址（我替换 `CITATION.cff` 剩余占位符并重新生成清单）
2. DOI
3. arXiv 编号

我会据此更新 `PROVENANCE.md` 第五、六节，把「外部时间戳缺失」这一最弱环节补上。
