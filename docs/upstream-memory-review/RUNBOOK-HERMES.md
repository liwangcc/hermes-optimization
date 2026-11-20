# Hermes 执行手册：提交 issue 和 PR

- **执行者**：Hermes Agent。按本手册一步一步做，每做一个动作都写进 [`SUBMISSION-LOG.md`](SUBMISSION-LOG.md)。
- **来源**：原始手册、补丁和正文由 Claude Code 准备；本轮本地实装、复验与 Issue-first 流程整理见执行记录。
- **用户**：@liwangcc。所有对外动作的批准人。

相关文件（都在本目录）：

| 文件 | 作用 | Hermes 能不能改 |
|---|---|---|
| `RUNBOOK-HERMES.md`（本文件） | 执行依据 | 不能。需要改就停下来报告 |
| [`ISSUES.md`](ISSUES.md) / `issues/` | 先发的三份 Issue 草稿 | 生成投稿正文时另存到 `posted/` |
| `PR-DRAFT.md` | 独立 PR 的英文正文（含占位符） | 同上 |
| `patches/01–07-*.patch` | 每个主库 PR 的代码 | 不能 |
| `SUBMISSION.md` | 背景和理由（给人看的） | 不能 |
| `SUBMISSION-LOG.md` | 执行记录 | 只能在末尾追加行 |
| `posted/` | 实际发出去的正文存档 | 只能新增文件 |

---

## 1. 必须遵守的规则

### 1.1 什么需要批准

**对外动作**必须先得到用户批准，没有批准就不做。对外动作包括：
- `git push`（推到任何远程）
- 开 issue、开 PR、发评论、编辑已经发出去的正文
- 把 Draft PR 改成 Ready

批准的方式：
- 用户可以一次批准整个阶段（例如「批准阶段 A」），也可以逐条批准。
- 把用户批准的原话写进记录的「批准」一列。

**本地动作**不需要批准：建分支、应用补丁、跑测试、生成正文文件。但都要记录。

### 1.2 永远不做的事

- 不推送到 `NousResearch/hermes-agent` 或 `itpartypattaya/hermes-plugin-holographic`，只推到用户自己的 fork。
- 不对 main 分支强制推送。PR 分支变基后只能用 `--force-with-lease`，并且要先得到批准。
- 不在原有项目或投稿工作树执行 `git reset --hard`、`git stash drop`、`git clean -fd`，也不删除任何分支或 stash。testkit 仅重置专属于它的临时克隆。
- 不 @ 任何人；不评论和本手册无关的 issue 或 PR；不关闭、不合并任何东西。
- 不读取、不打印、不保存任何 token 或凭据。登录由用户自己完成（例如在终端里执行 `gh auth login`）。
- 不修改网络、代理、证书或环境设置。
- 不修改补丁内容，也不替补丁修代码。补丁打不上或者测试失败，就停下来报告（见 1.3）。
- 不代写 HOLO-2/3。HOLO-1 已有补丁，按 `RUNBOOK-HOLO.md` 和维护者反馈单独处理。

### 1.3 遇到这些情况就停下来报告，不要自己处理

- 补丁冲突发生在生成文件以外的文件（生成文件怎么处理见 4.3）。
- 测试或检查失败，并且不在 1.4 的已知失败列表里。
- 网络、认证、推送失败。不要换参数或换方式重试，原样报告错误。
- 评审者要求改动代码或范围。草拟一份回复交给用户，等用户决定。
- 本手册和实际情况对不上（文件不存在、分支名不对、编号冲突等）。

报告时要写清楚：步骤 ID、执行的命令、原始错误输出（凭据要打码）、当前状态，以及建议的下一步。

### 1.4 已知失败（遇到不算失败，但要在记录里注明）

| 项目 | 原因 |
|---|---|
| `tests/tools/test_memory_tool.py::TestMemoryFileLockPermissions`（2 个测试） | Windows 上的 NTFS 没有 POSIX 权限位。未改动的 main 上同样失败 |
| ByteRover 子进程用例 | 仅基线已复现的 Windows `PATH` 首项分隔符断言，按 `testkit/plan.py` 的失败签名；其他失败不豁免 |
| `scripts/check` 的 `shims`、`line-endings` | Windows 上的已知问题。未改动的 main 上同样失败 |
| `scripts/check` 的 `no-tmp`，报 `plugin-catalog/layersift.yaml` | main 上已有的目录条目触发。如果报的是别的文件，就不算已知失败 |

### 1.5 记录格式

每个动作在 `SUBMISSION-LOG.md` 末尾追加一行，格式见那个文件的表头。

- 对外动作要记下得到的链接（issue、PR 的 URL）或推送后的 commit SHA。
- 测试要记下通过数和失败数。
- 实际发出去的正文，另存为 `posted/<步骤ID>.md`，内容和发出去的完全一致（占位符已替换）。

---

## 2. 环境（Windows，Git Bash）

```bash
ROOT="$PWD"                                       # 先进入本仓库根目录
UP=$ROOT/vendor/upstream-hermes-pr                 # 为对应 PR 新建的干净克隆，绝不是旧 vendor/hermes-agent
DOCS=$ROOT/docs/upstream-memory-review
source $ROOT/vendor/tools/env.sh                  # 把 Node 26 / pnpm 12 加进当前 shell 的 PATH
PY=$UP/.venv/Scripts/python.exe                   # 上游测试用的 Python
export PYTHONIOENCODING=utf-8                     # scripts/check 在 GBK 控制台上需要
```

- 跑 Python 测试：`cd $UP && HERMES_PYTHON=$PY bash scripts/run_tests.sh <测试文件...>`
- 跑上游检查：`cd $UP && $PY scripts/check --staged`
- 跑 e2e：先把 `TMP`、`TEMP`、`TMPDIR` 都指到 `$ROOT/vendor/tools/tmp`（Windows 路径写法），再在 `$UP/apps/desktop` 下执行 `pnpm run build && pnpm exec playwright test <spec>`。
- e2e 结束时偶尔会报 `EPERM rm ...\tmp\pw-*`，那是 Windows 删不掉被占用的临时目录，以 `passed`/`failed` 那一行为准。

---

## 3. 阶段 0：准备（全部完成之后才能进入阶段 A）

### S0.1 确认身份和登录（本地）

- `git -C $UP config user.email`、`git -C $ROOT config user.email`：必须是绑定在 GitHub 账号 @liwangcc 上的邮箱。不是的话停下来问用户，不要自己改。
- 如果要用 `gh`：执行 `gh auth status`，只记录「已登录 / 未登录」，不要记录输出内容。未登录就请用户自己执行 `gh auth login`。没有 `gh` 的话，所有对外动作都改成「Hermes 准备好正文和链接，由用户在浏览器里提交，再把得到的 URL 告诉 Hermes 记录」。

### S0.2 禁用向上游推送（本地）

```bash
git -C $UP remote set-url --push origin DISABLED   # 任何误推到 NousResearch 的操作都会直接失败
```

### S0.3 保留现有投稿工作克隆（本地）

不要切换、暂存或清理保存七份合体未提交改动的旧克隆。本地备份和固定基线已另存。实际提某个 PR 时，用独立的干净克隆 (`$UP`) 从届时的 `origin/main` 开分支；不要直接提交合体工作区。

### S0.4 固定适配器提交（本地）与可选发布（需批准）

本轮候选使用本地 `memory-review-rc`，给 Mac 的复验方式见 [`MAC-TEST.md`](MAC-TEST.md)。它不是已发布链接。
只有用户同意发布后，才推送约定的分支；读回远端 commit，确认可访问后才在 PR 中加参考实现链接。Issue 可以先征询方向；没有可访问的版本就说明参考实现暂未发布，不贴本地 SHA 链接。
只用白名单提交代码、补丁、测试和正文。不提交整个工作区、`vendor/`、权重、测试库或原始回执。

### S0.5 确认 fork（需批准 → 对外，如果需要新建或同步）

- 用户在 GitHub 上必须有 `liwangcc/hermes-agent`（NousResearch/hermes-agent 的 fork），并且已经同步到最新 main。没有的话请用户自己创建或同步，然后记录。
- 在本地加上 fork 远程：`git -C $UP remote add fork https://github.com/liwangcc/hermes-agent.git`

---

## 4. 每个主库 PR 的固定流程

把下面的 `<n>`、`<branch>`、`<patch>`、`<title>` 换成第 5 节表格里对应那一行的值。

### 4.1 本地准备（不需要批准）

```bash
cd $UP
git fetch --depth=1 origin main
git switch -c <branch> origin/main
git apply --3way $DOCS/patches/<patch>
```

### 4.2 验证（不需要批准）

1. 跑这个 PR 的测试，命令见第 5 节；用表中数量核对选测范围。若上游已移动测试，以同条件的最新基线对照说明差异。
2. 跑上游检查：`git add -A && $PY scripts/check --staged`。除 1.4 的已知失败外，必须全部通过。
3. 有任何不在已知列表里的失败，按 1.3 停下来。

### 4.3 冲突处理（不需要批准，但要记录）

- 只有下面两个**生成文件**可以重新生成；其他任何文件冲突都要停下来。
  - `locales/_keys.desktop.json`：在 `$UP/apps/desktop` 下执行 `pnpm run i18n:keys`。
  - `tests/hermes_cli/serve_handler_ledger.json`：执行 `$PY scripts/gen_serve_handler_ledger.py`。它在 Windows 上会写出 CRLF，要转回 LF；转换后如果 `git diff --stat` 显示 `website/docs/developer-guide/programmatic-integration.md` 没有真实改动，就把它还原。
- PR7 在 PR4 已经合并之后提交时，路由台账的计数行一定会冲突，按上面的方法重新生成即可，属于预期情况。

### 4.4 提交（本地）

提交信息的第一行就是第 5 节的 `<title>`，正文写一句「See #ISSUE-x」（用实际的 issue 编号）。提交作者是用户本人（S0.1 确认过的身份）。

### 4.5 推送和开 PR（需批准 → 对外）

1. 生成正文：从 `PR-DRAFT.md` 复制对应 PR 那一节，替换占位符（见第 6 节），存为 `posted/<步骤ID>.md`。
   - 正文要按上游 `.github/PULL_REQUEST_TEMPLATE.md` 的结构来写。模板里的勾选项只勾确实做到的，例如「tested on」只写 Windows 11。
2. 把正文和要执行的命令一起交给用户，等批准。
3. 批准后：
   ```bash
   git push -u fork <branch>
   gh pr create -R NousResearch/hermes-agent --base main --head liwangcc:<branch> \
     --title "<title>" --body-file $DOCS/posted/<步骤ID>.md            # 依赖的 PR 还没合并时加 --draft
   ```
4. 截图要用浏览器拖进 PR 正文才能显示，`gh` 做不到。请用户上传（文件名见第 5 节），然后在记录里注明「截图已由用户上传」。
5. 记录 PR 的 URL，并回到对应 issue，在 Plan 清单里补上这个链接（编辑 issue 也是对外动作，同样需要批准）。

---

## 5. 主库 PR 一览

| 步骤 ID | PR | 分支 | 补丁 | 标题（= 提交信息第一行） | 什么时候提 | 截图 |
|---|---|---|---|---|---|---|
| A3（后续） | 1 | `refactor/desktop-profile-families` | `01-profile-families.patch` | `refactor(desktop): move the profile-keyed storage families out of session-states.ts` | 提醒方向获认可后，不阻塞 PR3 | — |
| A4（后续） | 2 | `refactor/desktop-composer-offers` | `02-composer-offers.patch` | `refactor(desktop): pick the composer's one offer from a table` | 提醒方向获认可后，不阻塞 PR3 | — |
| A-PR3 | 3 | `feat/memory-capacity-by-layer` | `03-memory-capacity.patch` | `feat(memory): show memory capacity by layer` | Issue A 对应反馈后 | `2-capacity.png` |
| A-PR7 | 7 | `feat/memory-provider-jobs` | `07-memory-provider-jobs.patch` | `feat(memory): run a memory provider's maintenance jobs from the Desktop` | Issue B 对应反馈后 | `5-provider-job.png` |
| B2 | 4 | `feat/memory-checkup` | `04-memory-checkup.patch` | `feat(memory): a read-only memory checkup the user starts` | PR3 合并后，且 B1 已完成 | `3-proposals.png`、`4-facts.png` |
| B3 | 6 | `feat/memory-catalog-suggestion` | `06-catalog-suggestion.patch` | `feat(desktop): say when a provider's catalog makes MEMORY.md optional` | PR3、PR4 都合并后 | `6-catalog-suggestion.png` |
| C1 | 5 | `feat/desktop-memory-checkup-reminder` | `05-checkup-reminder.patch` | `feat(desktop): an opt-in reminder for the memory checkup` | PR1、2、4 都合并后 | `1-reminder.png` |

**依赖 PR 的应用顺序**：PR4 要在已经包含 PR3 的 main 上应用；PR6 要求 main 已包含 PR3 和 PR4（代码只依赖 PR3，但它改的两段文档在 PR4 新增的文字里）；PR5 要求 main 已包含 PR1、2、4。PR4 如果被拒或长期搁置，PR6 改基于只含 PR3 的 main 时，两个文档文件会冲突，按 1.3 停下来报告，不要自己改。如果依赖的 PR 还没合并，但用户批准先开 Draft，就从依赖 PR 的分支上开新分支，依次应用补丁，开 `--draft`，并在正文开头写「Depends on #PRx; review only the last commit」。

**每个 PR 的测试命令**（4.2 用；通过数是在 Windows 上实测的）：

| PR | 后端（在 `$UP`） | 前端（在 `$UP/apps/desktop`） | 通过数 |
|---|---|---|---|
| 1 | — | `pnpm exec vitest run src/store/session-states.test.ts src/store/session-states-profile-rename.test.ts src/store/session-tiles-connection-scope.test.ts src/store/composer-queued-pick.test.ts src/store/preview-status-edge-cases.test.ts src/store/preview-status-lifecycle.test.ts src/lib/browser-profile-prefs.test.ts src/lib/browser-desktop-bridge-saved-connections.test.ts src/sdk/profile-routing.test.ts src/sdk/open-session-refresh-in-place.test.ts src/app/profiles/rename-profile-dialog.test.tsx`；`pnpm run typecheck` | 11 个文件，210 个测试 |
| 2 | — | `pnpm exec vitest run src/app/chat/composer/status-stack`；`pnpm run typecheck` | 15 个文件，42 个测试 |
| 3 | `tests/hermes_cli/test_web_memory_layers.py` | `pnpm exec vitest run src/app/settings/memory src/app/command-center src/i18n scripts/i18n-keys.test.mjs`；`pnpm run typecheck` | 后端 6；前端 21 个文件 119 个测试（含 i18n） |
| 4 | `tests/agent/test_memory_checkup.py tests/hermes_cli/test_web_memory_checkup.py tests/hermes_cli/test_serve_handler_ledger.py` | `pnpm exec vitest run src/app/command-center src/store/memory-checkup.test.ts src/app/settings/memory src/i18n scripts/i18n-keys.test.mjs`；`pnpm exec vitest run --project electron electron/connection-config.test.ts`；e2e `e2e/memory-checkup.spec.ts` | 前端 23 个文件 126 个测试；electron 126；e2e 通过 |
| 5 | — | `pnpm exec vitest run src/store/memory-checkup-reminder.test.ts src/components/memory-checkup src/app/command-center src/app/chat/composer/status-stack`；e2e `e2e/memory-checkup.spec.ts e2e/boot.spec.ts` | e2e 通过 |
| 6 | `tests/hermes_cli/test_web_memory_layers.py` | `pnpm exec vitest run src/app/settings/memory src/i18n scripts/i18n-keys.test.mjs` | 前端 18 个文件 111 个测试 |
| 7 | `tests/hermes_cli/test_memory_actions.py tests/hermes_cli/test_serve_handler_ledger.py tests/ci/test_docs_drift.py` | `pnpm exec vitest run src/app/settings/memory src/i18n scripts/i18n-keys.test.mjs`；`pnpm exec vitest run --project electron electron/connection-config.test.ts`；e2e `e2e/memory-provider-jobs.spec.ts`；`pnpm run typecheck` | 前端 18 个文件 106 个测试；electron 126；e2e 通过 |

表中数量用于检查是否漏选；如因 main 更新而变化，记录实际选择器、基线与通过数，不静默跳过用例。

---

## 6. 占位符替换

生成 `posted/` 正文时替换，不改已归档的原文：`<ADAPTER_SHA>` 或 `<SHA>` 用已验证可访问的固定提交；没有则去掉死链接。`#ISSUE-A`、`#ISSUE-B`、`#PR1` … `#PR7`、`#HOLO-ISSUE` 仅在真实编号存在时替换；还没有的用文字说明或删掉。跨仓库用 `owner/repo#编号`，同仓库用 `#编号`。

---

## 7. 阶段和步骤

### 阶段 A：先征询，再开相应 PR

| 步骤 | 动作 | 前提 |
|---|---|---|
| A1 | 主库 Issue A：分层容量，询问是否先审 PR3 | 查重，用户批准对应正文 |
| A2 | 主库 Issue B：独立的 provider jobs，询问是否审 PR7 | 查重，用户批准对应正文 |
| A7 | 插件 Issue C：先问是否愿意看 HOLO-1 | 查重，用户批准对应正文；只链接已存在的主库 Issue |
| A-PR3 | 单独准备、验证、提交容量 PR3 | 维护者明确愿意审这段；用户批准发布 |
| A-PR7 | 单独准备、验证、提交 provider jobs PR7 | Issue B 对应的明确回应；用户批准发布 |
| A-HOLO1 | 按 `RUNBOOK-HOLO.md` 准备 HOLO-1 | 插件维护者愿意审而非打算自行实现；用户批准发布 |

不要求同一天发，也不把沉默当同意。PR1、2 只在确有需求时单开，不阻挡第一批。每份 PR 带自己的完整结果、复现命令和已知限制；有了真实链接再按需补交叉引用。

### 阶段 B

| 步骤 | 动作 | 对外 | 前提 |
|---|---|---|---|
| B1 | **真实模型验证**：这一步不由 Hermes 做，由用户或用户指定的测试 agent 完成。结果写在 `validation/real-model.md`，至少包含：用了哪些模型、每个模型跑了几次、回复能被解析的比例、失败时的原始错误 | 否 | — |
| B2 | PR4 | 是 | PR3 已合并；`validation/real-model.md` 存在。把它的结论放进 PR4 正文的 "How to Test" |
| B3 | PR6 | 是 | PR3、PR4 都已合并 |

### 阶段 C

| 步骤 | 动作 | 对外 | 前提 |
|---|---|---|---|
| C1 | PR5 | 是 | 提醒方向获认可，且 PR1、2、4 都已合并 |
| C2 | 主库 PR 合并后，在插件 issue 里同步一句（「Cross-references」的第三段） | 是 | 对应 PR 已合并 |

### 不在本手册范围内（需要用户另开任务，并单独记录）

- **HOLO-2、HOLO-3 的代码**：待接口与维护者反馈，另开任务。HOLO-1 补丁和手册已具备。
- **回复评审意见、按评审要求改代码**：Hermes 只负责草拟回复交给用户，不自行修改代码。
- **本仓库发版**（改 `plugin.yaml` 版本号等）。什么时候提醒，见第 9 节 R6。

---

## 8. 评审期间

- 每天看一次自己开的 issue 和 PR 有没有新回复，有回复就整理给用户：谁说了什么、要求什么，附上草拟的回复。
- 同一次检查里对照第 9 节的提醒表，条件满足就提醒用户。
- 用户批准了回复才能发。用户要求改代码时，停下来等用户安排（可能交回 Claude Code 去改）。
- 维护者要求变基时：
  ```bash
  git fetch --depth=1 origin main && git rebase origin/main
  ```
  然后重跑 4.2 的验证，**批准后**再执行 `git push --force-with-lease fork <branch>`。
- PR 合并后：在记录里写上合并的 commit；在 issue 的 Plan 清单里勾上（需批准）；需要的话执行 C2。

---

## 9. 条件满足后交回去做的任务（由 Hermes 负责提醒）

下面这些任务不由 Hermes 执行。但只有 Hermes 每天在看 issue 和 PR 的动态，所以条件一满足，由 Hermes 提醒用户，免得被忘掉。

**怎么提醒**

- 条件满足的当天提醒用户一次，并在记录里追加一行，步骤写 `提醒 R2` 这样的 ID。
- 之后每次例行检查（第 8 节）时，只要记录里还没有这项任务「已开始」或「已取消」的行，就在汇报末尾再提一句。
- 提醒的内容包括：任务 ID、满足了哪个条件（附链接），以及一句可以直接转给 Claude Code 的话：
  > 按 `docs/upstream-memory-review/RUNBOOK-HERMES.md` 第 9 节的 R2 开始做。依据：<链接>。
- 「正面回应」指维护者明确表示方向可以接受，或者已经开始逐行评审。拿不准时当作没满足，在汇报里写出来，让用户判断。
- 做事的一方（Claude Code 或用户）在开始和完成时，各在记录里追加一行。Hermes 看到「已开始」就停止提醒；看到「完成」后，按它附带的执行手册继续。

| ID | 任务 | 谁做 | 什么时候提醒 | 什么时候取消 | 产出 |
|---|---|---|---|---|---|
| R1 | HOLO-1 代码和定向验证 | 已备妥 | 不再提醒写代码；待插件维护者反馈 | 对方表示自行实现 | HOLO-1 补丁与 `RUNBOOK-HOLO.md` |
| R2 | HOLO-2 的代码：`usage_report`、`review_items` | Claude Code | 同时满足两条：PR3、PR4 都已合并或得到正面回应；插件 issue 里 `protected`、`unconfirmed` 两个字段有了答复。没有回复不算接口或字段达成共识 | 插件维护者表示要自己写；或 PR3、PR4 被拒 | 同 R1 |
| R3 | HOLO-3 的代码：一键建索引任务 | Claude Code | PR7 已合并或得到正面回应 | 插件维护者表示要自己写；或 PR7 被拒 | 同 R1 |
| R4 | 真实模型验证（即 B1） | 用户或测试 agent | PR3 已合并或得到正面回应 | — | `validation/real-model.md` |
| R5 | 把 PR6 重做成只依赖 PR3 的补丁 | Claude Code | PR4 被拒，或维护者明确表示不要体检进核心 | PR4 合并 | 新的 `06-*.patch` |
| R6 | 本仓库发版：改 `plugin.yaml` 版本号；README 里「Core does not call them yet」改成写明从哪个 Hermes 版本起生效；提醒用户更新 sidecar | Claude Code 改文件，Hermes 提交 | 带新接口的主库 PR（PR3、PR4 或 PR7）第一次随 Hermes 发版 | — | 本仓库的改动，交给 Hermes 提交 |
