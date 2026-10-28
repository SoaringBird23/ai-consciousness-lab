# arXiv 投稿：可直接照抄的字段

**状态**：提交包已验证（空目录独立编译，18 页，0 缺图，0 未定义引用，14 个标准宏包）。
**阻塞点**：① arXiv 计划维护（`11:00–16:00 UTC` = 北京时间 `19:00–24:00`）② 需要 endorsement。

---

## 1. Title

```
Growing Rather Than Training: A Pre-Registered Developmental System, and the Read-Only Nature of Its Workspace
```

## 2. Authors

```
Chengze Luo
```

（单位留空；ORCID 在 arXiv 账号设置里绑定 `0009-0007-3316-6292`，不写进作者行）

## 3. Abstract

从 [abstract_arxiv.txt](abstract_arxiv.txt) 整份复制（**1916 字符**，上限 1920）。

`cat abstract_arxiv.txt | pbcopy`

## 4. Comments（可选但建议填）

```
18 pages, 11 figures, 20 references. Every experiment has a frozen pre-registration
and a matching results file. Code and data: https://github.com/SoaringBird23/ai-consciousness-lab
(archived at doi:10.5281/zenodo.23728049)
```

## 5. Categories

| 项 | 填 |
|---|---|
| Primary | **cs.AI** (Artificial Intelligence) |
| Cross-list | **q-bio.NC** (Neurons and Cognition) |

> 若 endorsement 只拿到一个类别，就只填 Primary，别硬凑 cross-list。

## 6. License

选 **CC BY 4.0**。

理由：论文与文档在本仓库里已声明 CC BY 4.0（见 [AUTHORS.md](AUTHORS.md)），
arXiv 上保持一致，避免"仓库一个许可、预印本另一个许可"的歧义。
若你更希望只给 arXiv 默认的非独占分发许可，也合法，但要同步改 [AUTHORS.md](AUTHORS.md)。

## 7. Files

上传 **`submission.tar.gz`**（23 个文件，607 KB）：

```bash
cd paper/arxiv && tar tzf submission.tar.gz | head
```

构成：`main.tex` + `figs/`（11 张 eps/pdf/png）。**不含 `.bib`**——参考文献用内联
`thebibliography`，因此不存在 arXiv 常见的 `.bbl` 缺失问题。

---

## 8. endorsement 怎么办（唯一真正的关卡）

arXiv 对**首次投稿的新作者**要求 endorsement。三个可行路径，按成功率排：

| 路径 | 做法 |
|---|---|
| **最现实** | 找你大伯。他在 DC 的神经科学机构，arXiv 上大概率已有发表记录。让他用自己账号进 <https://arxiv.org/auth/endorse>，填你的 arXiv 作者 ID 与类别（cs.AI 或 q-bio.NC） |
| 次选 | 任何在 arXiv cs.AI / q-bio.NC 发过文章的同行，同样填那个 endorsement 页 |
| 自证 | 若有机构邮箱（大学/研究所 .edu），arXiv 会自动给 endorsement 资格。你是 Independent Researcher，这条走不通 |

**注意**：endorsement 是"认可你这个人可以投稿"，与你的论文内容无关，也不代表他认同结论。
可以直接跟他说"只需要你在页面上点一下，不涉及任何学术背书"。

---

## 9. 提交顺序（维护结束后照做）

1. <https://arxiv.org/user> → **Register**（用 ORCID 一键登录，会带出姓名与 ORCID）
2. 拿 endorsement（见第 8 节）—— 没这一步会卡在最后一步
3. **Start New Submission**
   - License：CC BY 4.0
   - 类别：cs.AI
   - 上传 `submission.tar.gz`
   - 填 Title / Authors / Abstract / Comments
4. **Process** → arXiv 会编译并让你看 PDF 预览
5. 核对预览：**18 页**，第 1 页有标题、作者、摘要；参考文献 20 条；11 张图都在
6. **Submit**

---

## 10. 拿到编号之后

把 `arXiv:XXXX.XXXXX` 发我，我做：

- `CITATION.cff` 的 `preferred-citation.url` → arXiv 链接（`doi` 仍保留 Zenodo）
- `PROVENANCE.md` 第 5 层把"arXiv 编号 ❌ 仍缺"改为 ✅
- `PUBLISH.md` 第 6 步标记完成
- 刷新 `MANIFEST.sha256`，打 `v0.3.0` 签名标签（这次值得打——内容实质变化）
