# Hermes 执行手册：holographic 插件库 Issue D 与 HOLO-4

- **执行者**：Hermes Agent。**编写者**：Claude Code，2026-11-21（代码、补丁、测试、正文）。**对外批准人**：@liwangcc。
- 规则全部沿用 [`RUNBOOK-HERMES.md`](RUNBOOK-HERMES.md) 第 1 节：哪些动作要批准、永远不做的事、什么情况停下来报告、记录格式。本手册只写这条线自己的步骤。
- 每个动作照样记进 [`SUBMISSION-LOG.md`](SUBMISSION-LOG.md)，步骤 ID 用本手册的 `A10`、`H4.x`。
- 这条线只涉及插件库。主库不需要任何改动：改的是插件里「语义放不放行」这一步，主库只调用召回、渲染设置。

| 文件 | 作用 | Hermes 能不能改 |
|---|---|---|
| 本文件 | 执行依据，第 6 节是 PR 正文 | 不能 |
| [`issues/D-recall-margin-shown.md`](issues/D-recall-margin-shown.md) | Issue D 的正文（英文） | 只能按第 2 节的核对结果改指定的一句，改动要记录 |
| `patches/holo-4-recall-margin-shown.patch` | HOLO-4 的代码，基于插件库 main `76689f9`（0.30.1），8 个文件，+180 −4 | 不能 |
| `validation/replay_margin_shown.py` | 复算 Issue D 里那张表，只读插件库已提交的行，不联网 | 不能 |

## 1. 这条线提的是什么

三套语义准入方案，测试过程和全部数字在仓库根目录的 `INTERNAL-recall-hypotheses.md`（本机文件，不发布）。

- **方案一，纯提升**：z 门槛分两档。这一轮本来什么都不展示时用较严的余量，已经有词法或实体事实时用较宽的余量。上游已提交的行上回放是救回 5、丢失 0，噪声和混淆不变。Issue D 请维护者在门禁上测它，HOLO-4 是它的测量开关。
- **方案二，取舍最优**：只取余弦最高的 1 条，配绝对阈值。增益更大，但带进非答案，过不了门禁。只作为对照写在 Issue D 里，不提 PR。
- **方案三，判别器复核**：余量放宽到 0.5，新增的那一条先交给本地小模型判断能不能直接回答问题。只在大库上有效，需要常驻一个模型。只作为说明写在 Issue D 的 C 一节，不提 PR，由维护者决定要不要。

HOLO-4 **不改默认行为**：新增的模块值默认是 `None`，这时召回路径和现在逐行相同。

## 2. A10：发 Issue D（需批准 → 对外）

发之前逐项核对，任何一项对不上就停下来报告：

1. **重读 #17 的关闭评论。** 正文第一句只说了「#17 没过门禁，噪声上升」。评论的原话与此有出入时，只改这一句，并把改前改后记进记录。
2. **查重。** 按当时两个仓库的状态搜一遍 `RECALL_MARGIN`、`margin`、`by meaning`，确认没有同题的 Issue 或 PR；确认 #95 仍是关闭、#110 仍是打开。
3. **复算那张表。** 在插件库当前 main 的克隆上运行：

   ```bash
   python $DOCS/validation/replay_margin_shown.py <插件库克隆>
   ```

   必须和正文一致：`0.5 before every turn` 是 481 → 487、b=6、c=0、噪声 94 → 98、混淆 34 → 34；`0.7 silent / 0.5 shown` 是 481 → 486、b=5、c=0、p=0.0625、噪声 94 → 94、混淆 34 → 34；第一行打印 `identical at margin 0.95 and 1.0: 810`。
4. **核对两个小库的数字。** 正文 B 一节的 `29 → 33 of 36`、`34 → 38 of 44`、噪声和混淆的增量、「A：+1 and +1」，要和仓库根目录 `INTERNAL-recall-answerability-findings.md` 里「两个小库的候选与准入」那张表的前两行一致（那张表是经插件 `prefetch` 实测的）。对不上就停下来报告。
5. **核对 C 一节的数字。** 那一行表（487、6 / 0、0.031、94、34）和「19 条里 6 条目标、13 条其他」要和 `INTERNAL-recall-hypotheses.md` 3.1 的最后一行及其下方说明一致；household 开发题的 `74 → 76 of 99`、噪声 48、混淆 7、直接放宽是 80 和 52、拒掉 6 条非目标和 4 条目标，要和 3.2 一致；小库的候选数 3 和 1 要和 3.3 一致。这些数需要本地判别模型才能重跑，Hermes 只做文档核对，不重跑。对不上就停下来报告。
6. **不和别的帖子同一天发。** #119（Issue C）是 2026-11-20 发的。
7. 正文取 `issues/D-recall-margin-shown.md` 里 `**Target:**` 那一行之后的全部内容，标题用文件第一行。存为 `posted/A10.md`，连同标题交给用户批准。

批准后在插件库新开 Issue，读回核对标题和正文，记录 URL。

## 3. 什么时候做 HOLO-4

- **前提**：A10 已经发出，并且维护者明确表示愿意看这个 PR。沉默不算同意。
- 维护者表示要自己接（#95 那次的测量开关就是他自己写的）：不提 PR，停下来报告用户。
- 维护者只对方案二或方案三感兴趣，或者要求换参数、换判定方式：停下来，交回 Claude Code。
- 两周没有回应：报告用户，由用户决定是否直接提 PR（#17 是直接提的 PR，维护者当时按门禁审了）。

## 4. 环境和准备

环境变量、fork、测试用的 core 和依赖，全部照 [`RUNBOOK-HOLO.md`](RUNBOOK-HOLO.md) 第 2、3 节（H1.1 到 H1.3）。HOLO-1 已经做过的不用重做，fork 克隆可以共用，换一个分支即可。

## 5. 应用、验证、提交（本地）

### H4.1 应用补丁

```bash
cd $FORK
git fetch --depth=1 upstream main
git switch -c feat/recall-margin-shown upstream/main
git apply --3way $DOCS/patches/holo-4-recall-margin-shown.patch
```

打不上就按 `RUNBOOK-HERMES.md` 1.3 停下来报告。这个分支不要带上 HOLO-1 的改动。

### H4.2 验证

```bash
cd $FORK
HERMES_AGENT_REPO=$CORE PYTHONPATH=$DEPS $PY -m pytest -q -p no:cacheprovider \
  tests/test_holographic_recall_margin_shown.py tests/test_holographic_provenance_recall_margin.py \
  tests/test_mcnemar_gate.py                                                          # 32 passed
$UP/.venv/Scripts/ruff.exe check .                                                    # All checks passed!
```

- 32 个里有 7 个是新的。这 7 个在没打补丁的 main 上全部失败，另外 25 个不受影响。
- 完整测试套件交给 PR 上的 CI 跑。本地的完整结果见第 6 节正文的 **Checked**。

### H4.3 提交

```bash
cd $FORK && git add -A
git commit -m "tools: measure a second recall margin for a turn that already shows a fact" -m "See #<A10 的编号>."
```

## 6. 推送和开 PR（需批准 → 对外）

1. 把下面正文里的 `#ISSUE-D` 换成 A10 的编号，存为 `posted/H4.md`。
2. 正文和下面两条命令一起交给用户，等批准。
3. 批准后执行：

```bash
git -C $FORK push -u origin feat/recall-margin-shown
gh pr create -R itpartypattaya/hermes-plugin-holographic --base main --head liwangcc:feat/recall-margin-shown \
  --title "tools: measure a second recall margin for a turn that already shows a fact" --body-file $DOCS/posted/H4.md
```

4. 记录 PR 的 URL。后续评审按 `RUNBOOK-HERMES.md` 第 8 节处理：Hermes 草拟回复交给用户；要改代码就停下来，交回 Claude Code。
5. 维护者跑出门禁结果后，不论过不过，都原样报告用户，不替用户回应「是否改默认」。

**PR 正文**（英文，从下一行开始到本节末尾）：

---

A measurement switch for #ISSUE-D, added the way `EMBED_TEXT` was added for #95. Nothing changes by default.

- **`embeddings.RECALL_MARGIN_SHOWN`** (a module value, `None`). When set, it is the margin before a turn that already shows a fact: the words found one, or the message names an entity that has one. `RECALL_MARGIN` stays the margin of a turn that would otherwise show nothing. With `None`, `_stream_extras` passes `RECALL_MARGIN` as before and asks nothing else.
- **`_names_a_fact`**. Stream 3 runs after the meaning stream, so whether it will show a fact has to be known beforehand. This makes stream 3's own test (not shown yet, not recent, recallable) on the facts stream 3 reads. It is called only when the value is set.
- **`tools/provenance_probe.py --recall-margin-shown <v>`** sets the value for one run and puts it back. Every row carries `margin_shown` (`None` on a plain run), and the file name gets `_s<v>` after `_m<v>`.
- **`tools/mcnemar_gate.py --pair margin`** names the second margin beside each side's margin and refuses a side whose rows carry two of them. Rows written before the stamp existed read as none. The two runs of a pair still have to differ in `--recall-margin`: a pair that differs only in the second margin would need a wider pairing key, which I left out.

**Tests**: 7 new, all failing on `main`.

- `tests/test_holographic_recall_margin_shown.py`: one margin before every turn by default; a turn the words already answer admits at the second margin; a turn that would stay silent keeps `RECALL_MARGIN`; an entity the message names counts as a fact shown.
- `tests/test_holographic_provenance_recall_margin.py`: the value is stamped, gets a file of its own and does not outlive its run.
- `tests/test_mcnemar_gate.py`: the report names the second margin; two second margins under one margin are refused.

**Checked** on Windows 11, Python 3.11, against Hermes `main` at `152fe189`:

- The three test files above: 32 passed.
- Full suite: 3,700 passed, 16 skipped, 7 failed. The seven are in `tests/test_holographic_blas_threads.py` and fail the same way on `main` in this setup.
- `ruff check .` is clean.

**Not done**:

- I have not run the probe against an embeddings endpoint with the value set, so there are no rows here. The pair I proposed in #ISSUE-D is `--recall-margin 0.7 --recall-margin-shown 0.5` against the default, `--modes off`, with `synthetic_zh` in the pool.
- `hermes plugins validate` not run; the patch adds no file outside `tests/` and no import.
- Version and CHANGELOG left to you. Not run on Linux or macOS; CI covers them.
