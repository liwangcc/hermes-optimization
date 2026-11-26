# 上游提交：余量放宽加小模型复核（补丁和验证记录）

2026-11-22 起草，2026-11-25 按维护者在 #121 的 5 点要求重做。这里是提给上游插件库 `itpartypattaya/hermes-plugin-holographic` 的一个测量开关，以及它在官方探针和门禁上的端到端结果。只写和验证，没有推送，也没有开 PR。

**维护者已同意开 PR（#121，2026-11-25T12:01Z）。分支重做好了，门禁在两个题池上都报 `gate PASSES`，数字与 #121 里公开的一致。** 向量模型是本地 bge-m3，复核模型是本地 Qwen3-Reranker-0.6B。行出自分支的干净提交 `31de6eb`，门禁命令是分支自带的 `--pair check_margin`：

| 题池 | 命中@5 | 救回 / 丢失 | p | 噪声 | 混淆 | 门禁 |
|---|---:|---:|---:|---:|---:|---|
| 决定池：multi（18 种语言）、contrast 英俄中、household test，540 道真问题 | 480 → 486 | 6 / 0 | 0.031 | 93 → 93 | 34 → 34 | 通过 |
| 并列：再加 household dev 和 `synthetic_zh`，696 道 | 565 → 573 | 8 / 0 | 0.008 | 142 → 142 | 46 → 46 | 通过 |

新的回执、行和版本信息都在 [repro/README.md](repro/README.md)。11-22 那一版的结果和之前离线拼出来的逐题一致（见 [../UPSTREAM-VERIFY-GATE-RESULTS.md](../UPSTREAM-VERIFY-GATE-RESULTS.md)）；这次重测与 11-22 那一版只差 3 行 multi 的展示内容，门禁计数不变（`repro/compare-with-a11.txt`）。

## 这里有什么

| 文件 | 内容 |
|---|---|
| `RUNBOOK.md` | **给 Hermes 的执行手册**。第 3 节（H5）已按新分支改写：核对、推送、开 PR |
| `CLAUDE-BRIEF-H5-REWORK.md` | Hermes 11-25 写的重做任务书，含维护者原文 |
| `PR-BODY.md` | PR 标题和英文正文，逐条对应维护者的 5 点和单函数接口 |
| `repro/` | 重做后的行、门禁回执、红测试证据、全量套件、版本与复现材料 |
| `ISSUE-121-COMMENT.md` | #121 评论的英文正文，已于 2026-11-23 发出 |
| `ISSUE-D-REVISED.md` | Hermes 11-22 06:56 起草的 #121 替换稿，没有用，只留作参考 |
| `holo-recall-check-margin.patch`、`gate-five-sets.txt`、`gate-seven-sets.txt`、`rows/` | 11-22 的旧补丁（基于 `76689f9`，7 个文件 +328 −7）和它的旧记录。行的 `git_sha` 带 `-dirty`，用的是旧行戳（`margin=0.5`、`margin_check=1.0`）。只留作历史，已被分支和 `repro/` 取代 |

分支在 `vendor/holo-check/plugin`（`vendor/` 不在版本管理里）：`feat/recall-check-margin` = `67229de5886bf802887cf88c4ef53162d2400a1f`，7 个提交，基于上游 main `ceb802be781e9e31cd9509755ad18ea46194a774`（v0.31.4）。前 6 个是代码，到 `31de6eb5af2ae3366f1be32c3b847f338cbf2a7c`，8 个文件 +607 −27，其中新测试文件 378 行；第 7 个只加数据 `results/issue121/`（行、门禁回执、指令、README），行的 `git_sha` 是 `31de6eb`。旧提交存在同一检出的 `rescue/b7b5a64`。

## 分支做了什么

- `embeddings.RECALL_CHECK_MARGIN`：模块值，默认 `None`，不是设置。设成比 `RECALL_MARGIN` 低的值、并且 rerank 关着时，语义流按这个较低的余量取候选；在 `RECALL_MARGIN` 上不够格的事实，要复核说 yes 才展示，每轮最多问一次，问最近的那条。本来就够格的事实照旧展示，不问。
- 复核收在一个函数后面：`recall_check.CHECK`，签名是 `(消息, 事实) -> (yes / no / not_answered, 原始分数)`。默认 `None`，用的是 `recall_check.cross_encoder`，走插件已有的 `rerank_*` 配置，第一次用到时才建，没配 `rerank_url` 就不建。探针一侧把这个值换成别的函数，就能换复核（维护者要在 `tools/` 里加 OpenAI 的那一个），插件代码不用改。
- 守卫和 rerank 一样：一次超时（`rerank.Settings` 把它和 `embedding_timeout` 一起压在 7.5 秒预算内）、失败后暂停；消息和整条事实都做密钥筛查和长度筛查，筛掉就不发。复核报错或者回的不是 yes/no，按未答处理，召回保持不开这个值时的结果。**rerank 开着时不运行**：值不起作用，不发请求。
- `rerank.Rescorer.scores(..., single=True)`：只有一条文档时也照发。
- 探针：`--recall-check-margin off | 0.5` 跑显式的关闭臂和复核臂，两臂普通 `margin` 都是 1.0。每行带 `check_margin`，文件名带 `_coff` / `_c0.5`；复核臂的行带 `check_model`（`--check-model`）和指令的 sha256（`--check-instruction`）；每行都带这一轮的调用数、结果、原始分数和耗时，什么都没展示的轮也带。复核未答时整次运行停下。
- 门禁：`check_margin` 加进 `_HEAD`，`--pair margin` 和 `--pair embed_text` 拒绝 check margin 不同的两次运行（旧行没有这个戳，按 off 读）。新增 `--pair check_margin`：要求两臂普通 margin 相同、行不带 `-dirty`、复核臂只有一个模型名和一个指令哈希，报告里写出复核的调用数、结果和最长耗时。
- README 加一段，含维护者要的那句：设了值之后，消息和一条事实会发给复核端点，而 rerank 关着时这个端点今天什么都收不到。

## 验证记录

环境：Windows 11，Python 3.11.4。测试用的核心是 `vendor/hermes-agent`（Hermes main `152fe189`，带着别的工作留下的未提交改动，分支和 main 两遍用同一份）；测量用的核心是 `e8a31a1` 里的 `core_shim`。

- 新测试 28 个，在干净 main（`ceb802b`）上 28 个全红：10 个红在自己的断言上（没有发起调用、事实没放进来、行里没有记录、没有停下、没有拒绝），18 个红在它测的东西 main 上不存在（`RECALL_CHECK_MARGIN`、`recall_check`、`_recall_checker`、`scores(single=)`、`--recall-check-margin`、`--pair check_margin`）。逐条原因在 `repro/main-red-reasons.txt`。分支上 28 个全过。
- 新测试加门禁、探针、单文档重排、#95 工具、分类五个已有文件：96 通过。
- 全量：分支 3,830 通过、16 跳过、7 失败；干净 main 3,802 通过、16 跳过、7 失败。两边失败的是同样 7 个，都在 `tests/test_holographic_blas_threads.py`；多出的 28 个通过就是新测试。原始输出在 `repro/suite-*.txt`。
- `ruff check .` 干净。
- 端到端：两臂各跑 7 个题集，门禁结论见上表。复核在 696 池里被问了 46 次，11 yes、35 no、0 未答；复核耗时最长 171 ms，最慢一轮 232 ms。
- `--set budget`（token 预算集，不开嵌入）在分支和 main 上写出的 160 行除耗时外完全一致；分支拒绝在这个集上开复核。

## 复现端到端

`$Root` 是本仓库根目录（用 `C:/aiprojects/hermes-optimization` 这种写法）。两个接口都只监听本机，各开一个终端，等它打印 `ready`：

```bash
python -E -B memory/threshold-calib/embed_endpoint.py vendor/models/bge-m3 12371
cd memory/threshold-calib && python -B rerank_endpoint.py ../../vendor/models/qwen3-reranker-0.6b 12372
```

然后跑两臂和门禁（脚本里写好了 `HERMES_HOME` 沙盒、`e8a31a1` 的 `core_shim`、`EMB_URL`、`EMB_MODEL`）：

```bash
bash memory/threshold-calib/upstream-check/repro/run-probe.sh $Root            # 插件检出有未提交改动就停下
PYTHONIOENCODING=utf-8 bash memory/threshold-calib/upstream-check/repro/run-gate.sh $Root
```

每个题集各跑两遍，参数是：

```bash
--emb on --modes off --repeats 1 --endpoint http://127.0.0.1:12372/v1/rerank --out <rows> --set <题集>
# 关闭臂：
--recall-check-margin off
# 复核臂：
--recall-check-margin 0.5 --check-model Qwen/Qwen3-Reranker-0.6B --check-instruction repro/instruction.txt
```

题集是 `multi --langs ar,bn,de,en,es,fr,hi,id,it,ja,ko,nl,pl,pt,ru,th,tr,zh`、`contrast_en`、`contrast_ru`、`contrast_zh`、`household --split test`、`household --split dev`、`synthetic_zh`。门禁：

```bash
python -B tools/mcnemar_gate.py --pair check_margin <每个题集的 _coff 和 _c0.5 两个文件>
```

## 要留意的

- **决定池上没有余量。** 救回 6 题正好是门禁要求的最低数，少一题就不过。
- **0.5、规则和指令都是在这几个题集上选出来的**，p 是探索性的。冻结一切换一个模型跑是复现（维护者自己跑 `text-embedding-3-small`），确认需要没参与挑选的问题。PR 正文第 4 节原话写明了。
- **只测了一个复核模型和一种指令。** 指令在本机接口里，不在插件里；维护者要原样复现，所以指令和配对格式一字不能改（`repro/instruction.txt`，sha256 `5336bc93…d7b73b72`）。换成普通的重排模型，分数大于 0 的含义是「相关」，比「能直接回答」宽，没有测过。
- 上游 0.31.3、0.31.4 换了多语种语料里的人名，结果文件只做了文本替换没有重跑。这次在新语料上重测，3 行 multi 的展示内容变了，门禁计数没变。
- 两个模型的 Hugging Face revision 没有记录（HF 缓存在项目目录外，没去读），`repro/README.md` 给了权重文件的 sha256。
- 多带一个 1.19 GB 的模型，和 bge-m3 一起显存在 4 GB 以内。

## 交接

**给 Hermes（提交线）**

按 [RUNBOOK.md](RUNBOOK.md) 第 3 节执行。要点：

1. 维护者已在 #121 同意开 PR，5 点要求和单函数接口都已在分支里落实，逐条对应写在 `PR-BODY.md`。
2. 分支已经提交好（HEAD `67229de`），只核对、推送、开 PR。不 rebase、不 amend、不 squash：行里的 `git_sha` 指向其中的 `31de6eb`。
3. upstream main 如果又前进了，停下交回 Claude Code。
4. 行已按 Hermes 的建议进了分支（第 7 个提交，`results/issue121/`）；用户不要的话交回 Claude Code 退回。开 PR 要用户批准。

**给有真实库副本的一方（Codex）**

11-22 的真实库结果仍然有效（见下），这次重做没有重跑真实库。注意：`calib_check_real.py` 是按旧补丁写的，它读 `provider._recall_check.calls`；重做后 `_recall_check` 是一个 `functools.partial`，客户端在 `.args[0]` 上，再用之前要先改这一行。

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

都在 `memory/threshold-calib/`：`embed_endpoint.py`（本机向量接口）、`rerank_endpoint.py`（本机复核接口）、`calib_answerability.py`（复核的指令和打分）、`calib_check_real.py`（真实库）、`calib_verify_gate.py`（离线拼的那一版）、`calib_margin_gate.py`（配对脚本）。
