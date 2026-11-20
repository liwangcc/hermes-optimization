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
