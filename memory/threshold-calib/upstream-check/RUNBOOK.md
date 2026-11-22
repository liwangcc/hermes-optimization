# Hermes 执行手册：#121 的更正评论与 HOLO-5（余量放宽加小模型复核）

- **执行者**：Hermes Agent。**编写者**：Claude Code，2026-11-22。**对外批准人**：@liwangcc。
- 规则沿用 `docs/upstream-memory-review/RUNBOOK-HERMES.md` 第 1 节：哪些动作要批准、永远不做的事、什么情况停下来报告、记录格式。本手册只写这条线自己的步骤。
- 每个动作记进 `docs/upstream-memory-review/SUBMISSION-LOG.md`，步骤 ID 用 `A11`、`H5.x`。
- 这条线只涉及插件库 `itpartypattaya/hermes-plugin-holographic`。

## 0. 现在的状态

- Issue D 已经在 2026-11-22 01:03 发为 #121。它的主提议是 A（双档余量），正文写的是「噪声、混淆不变，差一道题」。
- 之后用官方探针在 bge-m3 上直接跑，A 的噪声是 93 → 95，过不了。#121 里的那句话需要更正。
- C（小模型复核）已经做成补丁，官方门禁在两个题池上都通过。Hermes 在 06:56 做过本地核对，分支 `feat/recall-check-margin`，本地提交 `b7b5a64`。
- **结论：#121 不删、不改正文和标题，在它下面发一条评论更正并说明 C 的结果。HOLO-4（双档余量）的 PR 不再提。**

为什么用评论而不是改正文：维护者可能已经读过 #121。改正文和标题不会通知对方，也抹掉了原来的说法；评论会通知，更正和原话并排留着。`ISSUE-D-REVISED.md` 是 06:56 起草的替换稿，现在只留作参考，不发。它里面有一句「那 1 条非答案落在本来就带非答案的行上」是回放那一轮的说法，bge-m3 这一轮没有逐行核对过，评论稿里没有用这句。

| 文件 | 作用 | Hermes 能不能改 |
|---|---|---|
| 本文件 | 执行依据 | 不能 |
| `ISSUE-121-COMMENT.md` | #121 评论的正文（英文），第一行 Target 不发 | 只能按第 1 节的核对结果改指定的句子，改动要记录 |
| `PR-BODY.md` | PR 的标题和正文（英文） | 只能按第 3 节填测试数字和编号 |
| `holo-recall-check-margin.patch` | 代码，基于插件库 main `76689f9`，7 个文件 +328 −7，换行已归一成 LF，SHA-256 `959eda1f…639ac3` | 不能 |
| `gate-five-sets.txt`、`gate-seven-sets.txt`、`rows/` | 门禁原始输出和探针记录 | 不能 |
| `README.md` | 验证记录和复现命令 | 不能 |

## 1. A11：在 #121 下发更正评论（需批准 → 对外）

发之前逐项核对，任何一项对不上就停下来报告：

1. **先看 #121 现在的状态。** 维护者如果已经回复，把原话报告给用户，不要直接发评论：评论的写法要跟着对方说了什么改。#121 如果已被关闭，同样先报告。
2. **查重。** 两个仓库按现态搜 `RECALL_CHECK_MARGIN`、`check margin`、`cross-encoder`，确认没有同题的 Issue 或 PR。
3. **核对评论里的数。** 第一张表对 `../UPSTREAM-MARGIN-GATE-RESULTS.md`，第二张表对 `gate-five-sets.txt` 和 `gate-seven-sets.txt`，真实库那一条对 `README.md` 的交接一节，「82 行」对补丁（328 减去测试文件的 246）。
4. **错开日期。** 不和别的帖子同一天发。#121 是 2026-11-22 发的，这条评论最早 2026-11-23。
5. 正文按既有约定提取：`---` 之后到文件末尾，Target 行不发。存为 `docs/upstream-memory-review/posted/A11.md`，记下 sha256。
6. 正文和要执行的命令交给用户，等批准。批准后发评论，读回核对逐字节一致，记录 URL。

发完之后：**不提 PR，等维护者明确说愿意看。** 两周无回应就报告用户，由用户决定下一步。

## 2. 等维护者回应

- 对方说可以提 PR：进第 3 节。
- 对方要自己接、要换写法、或者只想先在自己的模型上测：原话报告用户，不替用户答应。要改代码就停下来，交回 Claude Code。
- 对方在自己的模型上测出不过：原样报告用户，这条线停。
- 不论哪种，都不要再提 HOLO-4（`--recall-margin-shown`）。

## 3. H5：开 PR（需批准 → 对外）

### H5.1 分支

06:56 的预检已经做过一遍。开 PR 前在当时的 `upstream/main` 上重做，因为 main 可能已经前进：

```bash
cd $FORK
git fetch --depth=1 upstream main
git switch -c feat/recall-check-margin upstream/main
git apply --3way $CHECK/holo-recall-check-margin.patch
```

`$CHECK` 是本目录。打不上就按 `RUNBOOK-HERMES.md` 1.3 停下来报告。这个分支不带 HOLO-1 和 HOLO-4 的改动。

### H5.2 验证

```bash
cd $FORK
HERMES_AGENT_REPO=$CORE $PY -m pytest -q -p no:cacheprovider \
  tests/test_holographic_recall_check_margin.py tests/test_mcnemar_gate.py \
  tests/test_holographic_provenance_recall_margin.py tests/test_holographic_rerank_single.py   # 46 passed
$UP/.venv/Scripts/ruff.exe check .                                                           # All checks passed!
```

全量套件在补丁上是 3,709 通过、16 跳过、7 失败，7 个都在 `tests/test_holographic_blas_threads.py`，在未改动的 main 上本机同样失败。main 前进后数字会变，以当时实际跑出来的为准，填进 `PR-BODY.md` 的 Checked 一节。

### H5.3 提交

```bash
cd $FORK && git add -A
git commit -m "tools: measure a lower recall margin whose facts a cross-encoder confirms" -m "See #121."
```

### H5.4 推送和开 PR

1. `PR-BODY.md` 第一行是标题，`---` 之后是正文。存为 `docs/upstream-memory-review/posted/H5.md`。
2. 正文和下面两条命令一起交给用户，等批准。
3. 批准后执行：

```bash
git -C $FORK push -u origin feat/recall-check-margin
gh pr create -R itpartypattaya/hermes-plugin-holographic --base main --head liwangcc:feat/recall-check-margin \
  --title "tools: measure a lower recall margin whose facts a cross-encoder confirms" --body-file $DOCS/posted/H5.md
```

4. 记录 PR 的 URL。后续评审按 `RUNBOOK-HERMES.md` 第 8 节处理。
5. 维护者跑出门禁结果后，不论过不过，都原样报告用户，不替用户回应「是否改默认」。

探针记录（`rows/`）不放进分支。维护者要的话再加到 `results/`，或者按 `README.md` 的命令在提交后的分支上重跑一遍，换成干净的提交号。

## 4. 这一轮没有变的

别的投稿不受影响：C（设置面板，已发）、A（内置文件用量）、B（提供者的维护任务）讲的都不是语义召回。

有一件事要留意：用户计划把日常版从本仓库搬到另一个文件夹。B 稿里引用了本仓库里日常版插件的路径，发 B 之前要按搬完后的位置核对链接。

## 5. 没有做的

- 上游记录用的模型（`text-embedding-3-small`）没有直接跑过，本机没有接口。评论和 PR 正文里都如实写了。
- 另一条提议（只删不加的否决规则，走门禁的精度那一支）还没有移植到上游插件，不在这份手册里。
- Claude Code 没法查看 #121 的现状（本机没有 `gh`），第 1 节第 1 步必须由 Hermes 做。
