# 提交执行记录

下方是历史记录，当时的步骤编号和章节号不随手册改版；当前入口见 [ISSUES.md](ISSUES.md) 和 [验证说明](validation/EVIDENCE.md)。

按 [`RUNBOOK-HERMES.md`](RUNBOOK-HERMES.md) 执行时，每个动作在表格末尾追加一行。只追加，不修改、不删除已有的行。

- **时间**：本地时间，精确到分钟，例如 `2026-11-20 10:05`。
- **执行者**：做这个动作的一方，例如 `Hermes`、`用户`（比如在浏览器里上传截图）。
- **批准**：对外动作写用户批准的原话或它所在的位置；本地动作写 `—`。
- **结果**：链接（issue、PR、评论的 URL）、commit SHA、测试的通过数和失败数，或者停下来的原因。
- **存档**：发出去的正文对应的 `posted/` 文件。

| 时间 | 步骤 | 执行者 | 动作 | 批准 | 结果 | 存档 |
|---|---|---|---|---|---|---|
| 2026-11-19 | 准备 | Claude Code | 写了补丁 01–07、`PR-DRAFT.md`、`SUBMISSION.md`、本手册；在 main `152fe189` 上完成验证（见 `SUBMISSION.md` 第 10 节） | — | 都没有提交，也没有推送 | — |
| 2026-11-19 14:01 | 准备 | Claude Code | 修订手册和正文，补丁没动：① RUNBOOK 第 6 节规定 A1、A2 时 `#ISSUE-B`、`#HOLO-ISSUE` 还没有编号怎么写，A9 负责换回真实编号，A9 的前提改为 A3–A7；② PR-DRAFT 中 Issue A、B 和插件 issue、HOLO-2 里要发出去的跨仓库引用都加上仓库名；③ PR4、PR6 的 "How to Test" 命令补全，和正文写的测试数一致 | 用户在 Claude Code 会话中回复「可以」 | 在 7 段合一的工作区复核：PR4 前端命令 24 个文件（减去 PR7 的 1 个即 23），PR6 后端两个文件共 12 个通过 | — |
| 2026-11-19 14:08 | 准备 | Claude Code | RUNBOOK 新增第 9 节「条件满足后交回去做的任务」：R1–R3 是 HOLO-1/2/3，R4 真实模型验证，R5 PR6 重做，R6 本仓库发版，由 Hermes 在条件满足时提醒用户；第 7、8 节各加一句指向第 9 节。R1 现在就满足 | 用户在 Claude Code 会话中要求「标记上，这样 Hermes 知道什么时候提醒」 | 只改了文档。HOLO-1/2/3 的代码都还没写 | — |
| 2026-11-19 14:14 | R1 已开始 | Claude Code | 开始写 HOLO-1（holographic 的 `config_schema.py`） | 用户在 Claude Code 会话中回复「开始做」 | 进行中 | — |
| 2026-11-19 14:37 | R1 完成 | Claude Code | HOLO-1 完成：补丁 `patches/holo-1-config-schema.patch`（基于插件库 main `76689f9`，5 个文件 +199 行），执行手册和 PR 正文在 `RUNBOOK-HOLO.md`。工作克隆在 `vendor/hermes-plugin-holographic`，未提交 | — | core 用 Hermes main `152fe189`：新测试 5 个加 save_config 2 个共 7 个通过，在 v0.23.2 上也是 7 个通过，新测试在原版插件上全部失败；完整套件 3698 通过 / 16 跳过 / 7 失败，失败的 7 个在原版插件上完全相同（`test_holographic_blas_threads.py`，本地依赖装在 `PYTHONPATH` 里，子进程继承不到）；ruff 干净；`hermes plugins validate` 通过；补丁能干净打到插件库 main 上。下一步按 `RUNBOOK-HOLO.md`，前提是 A7 已开出 | — |
| 2026-11-20 02:13 | 本地候选 | Hermes | 独立安装合体 Hermes、Desktop、适配器与真实 BGE-M3；修复 Windows Electron AppData 夹具后复验 | — | `a510d70`：真侧车 2 个 E2E 通过，12 个 1024 维向量，重复新增 0，侧车重启保留 12。未发 Issue、PR 或推送；Mac 待复验。 | [脱敏结果](validation/windows-live-checks.json) |
| 2026-11-20 09:49 | 准备 | Claude Code | 按上游先例核查重写三份征询草稿和投稿计划：A 改为 #5320 下的评论且只问两个内置文件；B 改写动机，去掉对话后回填的数字；C 只留一个问题。`ISSUES.md` 给出发布顺序 C → A → B；`SUBMISSION.md` 重写切片处置、依赖、仓库关系和升级兼容矩阵；`validation/EVIDENCE.md` 第 4 节改为按优先级的证据缺口。RUNBOOK、PR-DRAFT、补丁没有动，其中与新方案对不上的地方已列给用户，等批准后再改 | 用户在 Claude Code 会话中要求「整理 issue 和 PR 怎么提、怎么分」，并允许「在这个文件夹里分段提交到本地」 | 本地分支 `memory-review-plan`（基于 `9210c41`），提交 `6509423`、`f7089c5`、`ff35bcf`、`29bdb6a`、`3bb301c`。未推送，未发任何 Issue、评论或 PR | — |
| 2026-11-20 10:35 | 准备 | Claude Code | 改适配器的 Desktop 设置布局：`semantic_tau`、`semantic_max_extra`、`catalog_max_tokens` 从「Full config…」移到面板本身，各排在所属开关下面；这三个数字改成文本输入框，避免滚轮改值后失焦自动保存，由 `settings.to_store` 校验并转成数字。只动了 `memory/plugin/`，核心补丁没动 | 用户在 Claude Code 会话中要求「改一次 UI」 | 适配器自检 10 个通过；用核心的 schema 模块按路径加载确认 6 个字段全部 inline、没有 number 输入框。**没有在真实 Desktop 里跑，Windows 候选 `a510d70` 的 E2E 也没有重跑**；发给 Mac 的 bundle（`9210c41`）不含这次改动 | — |
