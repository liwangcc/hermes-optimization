# 上游提交：余量放宽加小模型复核（补丁和验证记录）

2026-11-22。这里是提给上游插件库 `itpartypattaya/hermes-plugin-holographic` 的一个测量开关，以及它在官方探针和门禁上的端到端结果。只写和验证，没有提交、推送，也没有发 Issue 或 PR。

**官方门禁脚本在两个题池上都报 `gate PASSES`。** 向量模型是本地 bge-m3，复核模型是本地 Qwen3-Reranker-0.6B。

| 题池 | 命中@5 | 救回 / 丢失 | p | 噪声 | 混淆 | 门禁 |
|---|---:|---:|---:|---:|---:|---|
| multi（18 种语言）、contrast 英俄中、household test，540 道真问题 | 480 → 486 | 6 / 0 | 0.031 | 93 → 93 | 34 → 34 | 通过 |
| 再加 household dev 和 `synthetic_zh`，696 道 | 565 → 573 | 8 / 0 | 0.008 | 142 → 142 | 46 → 46 | 通过 |

这是开关真正接进插件后，由探针端到端跑出来的，和之前离线拼出来的结果逐题一致（见 [../UPSTREAM-VERIFY-GATE-RESULTS.md](../UPSTREAM-VERIFY-GATE-RESULTS.md)）。

## 这里有什么

| 文件 | 内容 |
|---|---|
| `RUNBOOK.md` | **给 Hermes 的执行手册**：先在 #121 下发更正评论，等维护者回应后再开 PR |
| `ISSUE-121-COMMENT.md` | #121 评论的英文正文：更正双档余量在 bge-m3 上噪声上涨，说明复核的补丁和结果 |
| `holo-recall-check-margin.patch` | 补丁，基于上游 main `76689f9`，7 个文件 +328 −7（其中新测试文件 246 行），默认行为不变，换行已归一成 LF。不含方案一（双档余量）的改动 |
| `PR-BODY.md` | PR 标题和英文正文，引用 #121 |
| `ISSUE-D-REVISED.md` | Hermes 06:56 起草的 #121 替换稿。现在改用评论，这份只留作参考，不发 |
| `gate-five-sets.txt`、`gate-seven-sets.txt` | 官方 `mcnemar_gate.py --pair margin` 的原始输出 |
| `rows/` | 探针写出的 14 个记录文件，两臂各 7 个题集，共 2,136 行，只含上游公开的测试数据 |

打好补丁的检出在 `vendor/holo-check/plugin`（`vendor/` 不在版本管理里）。

## 补丁做了什么

- `embeddings.RECALL_CHECK_MARGIN`：模块值，默认 `None`。设成比 `RECALL_MARGIN` 低的值并且配了复核接口时，语义流按这个较低的余量取候选；在 `RECALL_MARGIN` 上不够格的事实，要复核模型给出的分数高于刻度中点才展示。本来就够格的事实照旧展示，不问。
- 没配接口时余量保持 `RECALL_MARGIN`。调用没发出、失败或判为否，这条事实都不展示。
- 每一轮最多问一次，只问最近的那条需要复核的事实，不超出召回的时间预算。
- 复核模型走插件已有的 `rerank_*` 配置，`rerank` 本身保持关闭，候选池不重排。
- 探针加 `--recall-check-margin <v>`，门禁脚本在报告里写明这一臂带复核，并拒绝同一侧混着带和不带复核的记录。

## 验证记录

环境：Windows 11，Python 3.11，Hermes main `152fe189`（`vendor/hermes-agent`）。

- 新增 16 个用例，在未改动的 main 上 15 个失败，第 16 个是「不带复核的余量照旧」的对照。
- 新用例加上门禁、探针、单文档重排三个已有文件：46 通过。
- 全量：3,709 通过、16 跳过、7 失败。7 个都在 `tests/test_holographic_blas_threads.py`，在未改动的 main 的全新克隆上本机同样失败（单跑这个文件是 7 失败、1 通过、1 跳过）。
- `ruff check .` 干净。
- 补丁能打到全新克隆的 `76689f9` 上（`git apply --check`）。
- 端到端：两臂各跑 7 个题集，官方门禁脚本的结论见上表。

## 复现端到端

`$CoreDir` 是提交 `e8a31a1` 里的 `memory/keyword-gate/core_shim`，`$Rows` 是放结果的目录，`$Home` 是空的沙盒目录。两个接口都只监听本机。

```powershell
python -E -B memory/threshold-calib/embed_endpoint.py vendor/models/bge-m3 12371
cd memory/threshold-calib; python -B rerank_endpoint.py ../../vendor/models/qwen3-reranker-0.6b 12372

$env:HERMES_HOME=$Home; $env:HERMES_AGENT_REPO=$CoreDir
$env:EMB_URL='http://127.0.0.1:12371/v1'; $env:EMB_MODEL='bge-m3'
cd vendor/holo-check/plugin
$Common='--emb','on','--modes','off','--repeats','1','--endpoint','http://127.0.0.1:12372/v1/rerank','--out',$Rows
$Langs='ar,bn,de,en,es,fr,hi,id,it,ja,ko,nl,pl,pt,ru,th,tr,zh'
# 下面七条各跑两遍：一遍原样，一遍加 --recall-check-margin 0.5
python -B tools/provenance_probe.py @Common --set multi --langs $Langs
python -B tools/provenance_probe.py @Common --set contrast_en
python -B tools/provenance_probe.py @Common --set contrast_ru
python -B tools/provenance_probe.py @Common --set contrast_zh
python -B tools/provenance_probe.py @Common --set household --split test
python -B tools/provenance_probe.py @Common --set household --split dev
python -B tools/provenance_probe.py @Common --set synthetic_zh
python -B tools/mcnemar_gate.py --pair margin <每个题集的两个文件>
```

## 要留意的

- **五个题集上没有余量。** 救回 6 题正好是门禁要求的最低数。上游自己的模型上只有回放的结果（同样是 6 / 0），没有直接测过，本机没有那个模型的接口。
- **只测了一个复核模型和一种提示语。** 提示语在本机接口里，不在插件里。换成普通的重排模型，分数大于 0 的含义是「相关」，比「能直接回答」宽，没有测过。
- 记录里的 `git_sha` 带 `-dirty`，因为是在补丁提交之前跑的。Hermes 那边在分支上提交后可以按上面的命令重跑一遍，换成干净的提交号。
- 多带一个 1.19 GB 的模型，和 bge-m3 一起显存在 4 GB 以内。复核一次约 45 毫秒。

## 交接

**给 Hermes（提交线）**

按 [RUNBOOK.md](RUNBOOK.md) 执行。要点：

1. Issue D 已经发为 #121，主提议是 A（双档余量），正文写的是「噪声、混淆不变，差一道题」。那是上游模型上的回放；在 bge-m3 上用官方探针直接跑，A 的噪声是 93 → 95，过不了（见 [../UPSTREAM-MARGIN-GATE-RESULTS.md](../UPSTREAM-MARGIN-GATE-RESULTS.md)）。
2. #121 不删、不改正文，在它下面发一条评论（`ISSUE-121-COMMENT.md`）：更正 A，说明 C 的补丁和结果，问能不能提 PR。
3. 维护者说可以之后再开 PR。分支从 `upstream/main` 新开，只打这一个补丁，不带 HOLO-1 和方案一的改动。方案一的 PR（HOLO-4）不再提。
4. 评论和 PR 都要用户批准后才发。

**给有真实库副本的一方（Codex）**

真实库只发往本机的两个接口，脚本会检查地址，不是本机地址就直接退出。输出只有计数。

```powershell
python -E -B memory/threshold-calib/embed_endpoint.py vendor/models/bge-m3 12371
cd memory/threshold-calib; python -B rerank_endpoint.py ../../vendor/models/qwen3-reranker-0.6b 12372

$env:EMB_URL='http://127.0.0.1:12371/v1'; $env:EMB_MODEL='bge-m3'
python -B memory/threshold-calib/calib_check_real.py --plugin vendor/holo-check/plugin --core-src $CoreDir --store $StoreCopy --queries $Queries --endpoint http://127.0.0.1:12372/v1/rerank
```

- `$StoreCopy` 是冻结的真实库副本，只读打开。`$Queries` 是同一次冻结的标注题。
- 要看的：`checked` 相对 `default` 的 `rescued`、`lost_targets`、`noise`、`confusion`、`added_other`，以及 `checker_calls`。
- 预期变化很小：真实库只有 54 条事实，z 门槛在这个规模上很少放出候选。这一步要确认的是不丢目标、不新增噪声。
- **结果（Codex 跑，用户 2026-11-22 转述）**：默认余量 1.0 和 0.5 加复核完全相同，命中@5 34/44 → 34/44，噪声题 3 → 3，混淆题 30 → 30。没有代价，也没有增益。复核被问了 1 次、0 次失败（`checker_calls=1`，`checker_failures=0`）：这两个数是 Codex 之后写进 [../STACK-RESULTS.md](../STACK-RESULTS.md)「冻结真实库」一节末段的，评论和 PR 正文里的「one question asked」以那里为准。
- 这个脚本在一个替身库（household 中文，199 条事实）上跑通过：11 次复核调用，0 次失败。

## 相关脚本

都在 `memory/threshold-calib/`：`embed_endpoint.py`（本机向量接口）、`rerank_endpoint.py`（本机复核接口）、`calib_check_real.py`（真实库）、`calib_verify_gate.py`（离线拼的那一版）、`calib_margin_gate.py`（配对脚本）。
