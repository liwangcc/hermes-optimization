# 投稿证据：不要把三种实验混为一谈

## 1. 固定补丁基线：Windows testkit

Hermes `152fe18976002e9a987422b7c6102c805d61264b`；插件侧基线 `76689f954f500d49a7ef2eb73d0e868a5b43b53e`。命令入口为 [testkit](../testkit/README.md)，每个 PR 的选择器在 [`plan.py`](../testkit/plan.py)，完整步骤与计数见 [`windows-pr-checks.json`](windows-pr-checks.json)。

| 口径 | 结果 | 说明 |
|---|---|---|
| PR1–PR7 + 7 份合体 | 47 个步骤通过、9 个已知基线失败、0 个新增失败 | 原跑与失败项复验汇总，不是一次全量；不含 HOLO-1 整套或独立适配器自检 |
| PR3 单独 | 后端 6；Desktop 21 个文件、119 个测试 | 含 i18n 检查；能先单独提分层容量 |
| PR7 单独 | 后端 17（testkit 最小集）；Desktop 18 文件、106；Electron 126；E2E 1 | 更广的作者验证与这里选的后端文件不同，不混写 |
| 合体 | Desktop 258 文件、2,442 个测试；真实适配器 E2E 2 | 体检是 mock 生成模型；建索引用替身侧车。不能把那张截图当作真实模型证明 |

9 个已知步骤包含 8 个代码健康检查步骤（报告基线问题），以及 1 个后端步骤的 3 个 Windows 基线断言。ByteRover 仅按精确已复现的 `PATH` 分隔符断言豁免；2 个权限断言是 NTFS 与 POSIX 行为差异。数据是本机验证，不是 CI，也不替发 PR 前在新 `main` 上验切片。

## 2. 旧流程的真实模型对照：对话后回填

来源是用户提供的 `hermes-embedding-backfill-windows-evidence.zip`。合成库 40 条事实、5 条语义探针；Windows CPU，Holographic **0.30.0**，用真实模型，预热后串行跑的是已有 `HolographicMemoryProvider.sync_turn`，不是新 `Run` 按钮。以下从附件 `serial-results.json` 和 `qwen3-initial.json` 得到，复算代码是 [`summarize_backfill.py`](summarize_backfill.py)，汇总为 [`backfill-summary.json`](backfill-summary.json)。原始 ZIP 与逐请求日志留本机，不随候选发布。

| 嵌入模型 | 维度 | 最终索引 | 语义探针 | 已记录回填时间 |
|---|---:|---:|---:|---:|
| `all-MiniLM-L6-v2` | 384 | 40/40 | 3/5 | 2.851 s |
| `multilingual-e5-small` | 384 | 40/40 | 1/5 | 0.836 s |
| `bge-small-zh-v1.5` | 512 | 40/40 | 2/5 | 0.718 s |
| `bge-m3` | 1024 | 40/40 | 5/5 | 8.207 s |
| `Qwen3-Embedding-0.6B` | 1024 | 40/40（两进程） | 4/5 | 20.629 s（第二段，仅 12 条） |

Qwen3 第一段是刻意有界运行：4 次 sync 后保存 **28/40**。下一进程的 12 个成功回填输入哈希与首段的 28 个不重叠，并集为 40。同维换模型的 `384 → 384` 对照中，E5 没有把 MiniLM 的已有向量当作就绪。本表不做速度或质量排名；尤其不要把 Qwen3 只补 12 条的用时与别款补 40 条直接相比。

## 3. 独立实装：真实 Desktop 一键建索引

用 `testkit/run.py --only live`：固定核心基线叠七个补丁（合体补丁 SHA-256 `6cec54f8fc700d5bba88b30e0a72e9c0f5f1a0ae51bd6b3dd0cff3fb7942f957`），实际加载 `holographic-semantic` 与基于 0.30.1 的 Holographic。只用独立 home 和 12 条合成事实。外部生成式调用由本机替身回答；embedding 由本机侧车加载 BGE-M3 权重。具体命令和下载 pin 见 [Mac 复验](../MAC-TEST.md)。

本节等本机真模型回执后更新；不以第 1、2 节的结果代替。

## 4. 仍需什么

- **Mac 未跑**，另收报告；兼容性不从 Windows 推断。
- **PR4 的真实生成式模型体检另做**。建议在同一份合成库上针对 2–3 个常用模型记录每模型有效解析数、总运行次数和失败样本；不要把向量模型或 mock 回执当成这项门槛。本地候选和独立 PR3/PR7 不等此结果。
- 未对外发布，截图和原始日志不随候选提交。用合成输入重新生成截图、复核后再考虑贴到对应 PR。
