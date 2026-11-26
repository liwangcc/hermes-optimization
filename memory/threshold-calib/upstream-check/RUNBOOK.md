# Hermes 执行手册：#121 的更正评论与 HOLO-5（余量放宽加小模型复核）

- **执行者**：Hermes Agent。**编写者**：Claude Code，2026-11-22；2026-11-25 改写第 0 节开头、文件表和第 3 节。**对外批准人**：@liwangcc。
- 规则沿用 `docs/upstream-memory-review/RUNBOOK-HERMES.md` 第 1 节：哪些动作要批准、永远不做的事、什么情况停下来报告、记录格式。本手册只写这条线自己的步骤。
- 每个动作记进 `docs/upstream-memory-review/SUBMISSION-LOG.md`，步骤 ID 用 `A11`、`H5.x`。
- 这条线只涉及插件库 `itpartypattaya/hermes-plugin-holographic`。

## 0. 现在的状态

**2026-11-25 更新（Claude Code）**：A11 评论已在 2026-11-23 发出。维护者 2026-11-25T12:01Z 在 #121 明确同意为 `RECALL_CHECK_MARGIN` 开 PR，提了 5 点要求，并要求复核收在一个可替换的函数后面。旧补丁 `b7b5a64` 不满足这些条件，已按 `CLAUDE-BRIEF-H5-REWORK.md` 重做：

- 分支在 `vendor/holo-check/plugin`（`vendor/` 不入版本管理）：`feat/recall-check-margin` = `67229de5886bf802887cf88c4ef53162d2400a1f`，7 个提交，基于上游 main `ceb802be781e9e31cd9509755ad18ea46194a774`（v0.31.4）。前 6 个是代码（到 `31de6eb5af2ae3366f1be32c3b847f338cbf2a7c`，8 个文件 +607 −27），第 7 个只加数据 `results/issue121/`（按 Hermes 的建议，行进 PR）。
- 旧提交抢救在同一检出的 `rescue/b7b5a64`。重做前的工作树和 b7b5a64 逐文件相同，存在 `stash@{0}`。
- 测量、门禁、可复现材料都在 `repro/`（入口 `repro/README.md`）。两池数字与 A11 一致，行出自 `31de6eb`，不带 `-dirty`。
- 英文 PR 正文已重写：`PR-BODY.md`。
- **第 3 节（H5）已按新分支改写，下面第 0 节其余几条是 11-22 的记录。**

以下是 2026-11-22 的记录：

- Issue D 已经在 2026-11-22 01:03 发为 #121。它的主提议是 A（双档余量），正文写的是「噪声、混淆不变，差一道题」。
- 之后用官方探针在 bge-m3 上直接跑，A 的噪声是 93 → 95，过不了。#121 里的那句话需要更正。
- C（小模型复核）已经做成补丁，官方门禁在两个题池上都通过。Hermes 在 06:56 做过本地核对，分支 `feat/recall-check-margin`，本地提交 `b7b5a64`。
- **结论：#121 不删、不改正文和标题，在它下面发一条评论更正并说明 C 的结果。HOLO-4（双档余量）的 PR 不再提。**

为什么用评论而不是改正文：维护者可能已经读过 #121。改正文和标题不会通知对方，也抹掉了原来的说法；评论会通知，更正和原话并排留着。`ISSUE-D-REVISED.md` 是 06:56 起草的替换稿，现在只留作参考，不发。它里面有一句「那 1 条非答案落在本来就带非答案的行上」是回放那一轮的说法，bge-m3 这一轮没有逐行核对过，评论稿里没有用这句。

| 文件 | 作用 | Hermes 能不能改 |
|---|---|---|
| 本文件 | 执行依据 | 不能 |
| `ISSUE-121-COMMENT.md` | #121 评论的正文（英文），已于 2026-11-23 发出 | 不能 |
| `PR-BODY.md` | PR 的标题和正文（英文），2026-11-25 按维护者 5 点重写 | 不能。数字和命令都已填好；对不上就停下报告 |
| `vendor/holo-check/plugin` 的 `feat/recall-check-margin` | 7 个提交，HEAD `67229de`：6 个代码提交到 `31de6eb`，第 7 个只加 `results/issue121/` | 不能改提交：不 rebase、不 amend、不 squash、不用 `git am` 重放，行里的 `git_sha` 指向 `31de6eb` |
| `repro/` | 新的行、门禁回执、版本和复现材料 | 不能 |
| `holo-recall-check-margin.patch`、`gate-five-sets.txt`、`gate-seven-sets.txt`、`rows/` | 11-22 的旧补丁（基于 `76689f9`）和它的旧记录（`-dirty`），只留作历史，已被上两行取代 | 不能 |
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

2026-11-25 改写。分支已由 Claude Code 按维护者的 5 点重做好，Hermes 不再打补丁、不再提交，只核对、推送、开 PR。下面 `$P` 是 `vendor/holo-check/plugin`，命令在本仓库根目录执行。

### H5.1 核对分支（本地，只读）

```bash
P=vendor/holo-check/plugin
git -C $P status --short                          # 空
git -C $P rev-parse feat/recall-check-margin      # 67229de5886bf802887cf88c4ef53162d2400a1f
git -C $P log --oneline ceb802be781e9e31cd9509755ad18ea46194a774..feat/recall-check-margin   # 7 个提交，倒数第二个是 31de6eb
git -C $P diff --name-only 31de6eb HEAD | grep -vc '^results/issue121/'   # 0：第 7 个提交只有数据
git -C $P fetch upstream main && git -C $P rev-parse upstream/main   # 2026-11-25 是 ceb802be…
```

- 任何一项对不上，按 `RUNBOOK-HERMES.md` 1.3 停下来报告。
- **upstream main 前进了：停下报告，交回 Claude Code。** 不要自己 rebase：rebase 会换掉提交号，`results/issue121/` 和 `repro/rows/` 里的 `git_sha`（`31de6eb`）就不再是分支里的提交，维护者要求行出自一个干净提交。

### H5.2 验证（本地）

```bash
cd vendor/holo-check/plugin
HERMES_AGENT_REPO=../../hermes-agent python -m pytest -q -p no:cacheprovider \
  tests/test_holographic_recall_check_margin.py tests/test_mcnemar_gate.py tests/test_holographic_provenance_recall_margin.py \
  tests/test_holographic_rerank_single.py tests/test_issue95_tools.py tests/test_holographic_provenance_classify.py   # 96 passed
../../hermes-agent/.venv/Scripts/ruff.exe check .   # All checks passed!
```

全量套件的数字在 `repro/suite-branch.txt` 和 `repro/suite-main.txt`，已写进 `PR-BODY.md` 的 Checked 一节，不用 Hermes 再填。

### H5.3 提交

不需要新提交。7 个提交按原样推，不 amend、不 squash、不 rebase，也不用 `git am` 在别的克隆里重放（重放同样换提交号）。

### H5.4 推送和开 PR

1. `PR-BODY.md` 第一行去掉 `Title: ` 是标题，`---` 之后到末尾是正文。正文存为 `docs/upstream-memory-review/posted/H5.md`，记 sha256。
2. 行已经进了分支：第 7 个提交 `67229de` 加了 `results/issue121/`（14 个行文件、4 份门禁回执、指令文件、README），PR 正文已同步改。用户如果不要行进 PR，交回 Claude Code 退回第 7 个提交、还原正文那几句，不要自己动分支。
3. 正文和下面的命令一起交给用户，等批准。
4. 批准后执行。用户的 fork 先确认存在；推送前再看一次 `git -C $P rev-parse HEAD` 还是 `67229de`：

```bash
P=vendor/holo-check/plugin
git -C $P remote add fork https://github.com/liwangcc/hermes-plugin-holographic.git
git -C $P push -u fork feat/recall-check-margin
gh pr create -R itpartypattaya/hermes-plugin-holographic --base main --head liwangcc:feat/recall-check-margin \
  --title "RECALL_CHECK_MARGIN: a probe-only lower margin whose facts a check confirms (#121)" \
  --body-file docs/upstream-memory-review/posted/H5.md
```

   这个检出里 `upstream` 和 `scratch` 两个 remote 的推送地址设成了 `DISABLED-no-push`，防止误推到上游，不要改回来。
5. 读回 PR 正文逐字节对比，记录 URL。后续评审按 `RUNBOOK-HERMES.md` 第 8 节处理；要改代码就停下，交回 Claude Code。
6. 维护者跑出 `text-embedding-3-small` 三臂的结果后，不论过不过，都原样报告用户，不替用户回应「是否改默认」。

## 4. 这一轮没有变的

别的投稿不受影响：C（设置面板，已发）、A（内置文件用量）、B（提供者的维护任务）讲的都不是语义召回。

有一件事要留意：用户计划把日常版从本仓库搬到另一个文件夹。B 稿里引用了本仓库里日常版插件的路径，发 B 之前要按搬完后的位置核对链接。

## 5. 没有做的

- 上游记录用的模型（`text-embedding-3-small`）没有直接跑过，本机没有接口。评论和 PR 正文里都如实写了；维护者已说这一轮由他们跑。
- 另一条提议（只删不加的否决规则，走门禁的精度那一支）还没有移植到上游插件，不在这份手册里。
- Claude Code 没法查看 #121 的现状（本机没有 `gh`），第 1 节第 1 步必须由 Hermes 做。
