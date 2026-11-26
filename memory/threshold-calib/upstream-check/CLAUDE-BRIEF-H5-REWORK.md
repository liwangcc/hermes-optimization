# H5 重做 brief —— RECALL_CHECK_MARGIN 备 PR（Claude Code 执行）

2026-11-25 07:52 EST，Hermes 编写。下方所有路径、SHA、数字均由 Hermes 今日在本机核实。开工前重验上游 main SHA（可能再前进）。

## 0. 任务一句话

维护者 itpartypattaya 已在 #121 明确批准 C 补丁开 PR（2026-11-25T12:01:48Z 评论），附 5 点要求＋单函数接口要求。你的任务：**把现有补丁重做到满足全部要求，rebase 到当前 main，重跑测量与官方门禁，产出 PR-ready 分支＋英文 PR 正文＋可复现证据包。全部本地动作，不做任何远端写。**开 PR 由用户批准后另行执行，不是你的动作。

## 1. 权威要求（维护者评论原文，逐字）

> Thanks — and thanks for withdrawing A on your own run rather than leaving the replay standing. That is exactly what the gate is for.
>
> **C: yes, please open the PR for `RECALL_CHECK_MARGIN`** as a probe-only module value, unset by default. Any user-facing setting is a separate decision after the result replicates. A few things we'd ask for:
>
> 1. **Tests that fail without the change** (our `CLAUDE.md`, section "Tests"): unset leaves recall as it is and makes zero checker calls; an eligible turn makes exactly one call; accept, reject and a failed call are each covered, and a failure keeps the baseline result. Each red on `main` for the reason it names.
> 2. **Rows anyone can re-pair.** Plain `--pair margin` on `main` needs two values of `margin`, so it would refuse these rows — please say how your patch pairs them, and give the exact gate command. We'd like: an explicit off arm and the 0.5 arm, the same ordinary margin in both, stamped in rows and file names; the new stamp joining the head of the existing pairs, so `--pair margin` / `--pair embed_text` refuse two runs that also differ in check margin; the checker's model name and a hash of the instruction in the rows (you found the wording matters); rows from one clean commit, with the test split as the decisive pool and dev reported beside it.
> 3. **The cost stays bounded.** The check runs inside prefetch, so it needs the same guards as `rerank`: one timeout, the pause after a failure, the secret and length screens for both the message and the fact, and embeddings plus the check inside the prefetch budget. A slow endpoint may cost one timeout, then it is left alone. For now, run it only with `rerank` off (please say what happens with it on — not running there is fine). Report call counts, outcomes and elapsed time in the probe rows, including turns that emit nothing; the journal doesn't see those. And one line in the docs: with the value set, the message and one fact go to the checker's endpoint, which gets nothing today while `rerank` is off.
> 4. **Say plainly what it was measured on:** bge-m3 with `Qwen3-Reranker-0.6B`, and that 0.5, the rule and the instruction were chosen on these same question sets, so p is exploratory. A run on a second model with everything frozen is a replication; confirmation needs questions it wasn't chosen on.
> 5. **So we can repeat your run:** the server and model versions, the exact instruction and pair format, and one synthetic request and response showing how the score maps to yes or no.
>
> On our side: the run you can't do is ours to do — `text-embedding-3-small`, same commit, same sets, 0.5 frozen, `rerank` off. We plan three arms, each against the same default:
>
> - **The plain 0.5 margin, no check** — how many targets it offers on that model at all. With fewer than six, no checker can pass.
> - **Your checker as you ran it** — `Qwen3-Reranker-0.6B`, your instruction and pair format, yes above no. Only the embedding model changes, so this arm is the replication. (Our own `jina-reranker-v2-base-multilingual` can't stand in: its score means "relevant", not "answers it", and it would need a fitted threshold.)
> - **A second checker, as a new result** — OpenAI's Decisions API (`/v1/decisions`, `gpt-6-luna`, one `predicate` question, admit when the probability is above 0.5). We use that API elsewhere as a three-way judge with a threshold measured there; the yes/no form is new to us, so 0.5 is the midpoint, fixed before the run, not a measured value. We'll post the exact question text and its hash before running, commit the rows with the returned probabilities so the gate can be replayed without a key, and treat a failed or refused call as a broken run, not as a no.
>
> To make that a small addition, please keep the check behind one function: (message, fact) → yes, no or not answered, plus the raw score, with the probe able to swap in another one. Nothing OpenAI-specific is needed in your PR; we'll add the second checker ourselves, in `tools/`.
>
> **B:** not as an opt-in for now. It doesn't pass the gate, and its floor is tied to the model (#95, #110); a second per-model threshold next to `embedding_min_score` is more than we want to ask people to tune.

背景：同日 #110（校准工具提案）被关 not_planned，B 明确拒绝——PR 里不要带任何 B/floor/校准工具内容。维护者将亲自跑 te3-small 三臂复现，其中一臂原样用你的 instruction 和 pair format——**这两样必须精确交付，措辞不能变**（你自己在 #121 证明过 wording matters）。

注：CLAUDE.md 在两仓库公开 main 均 404（11-24 已核），测试规则以评论第 1 点写明内容为准。

## 2. 现状盘点（已核实）

| 工件 | 位置 / 值 |
|---|---|
| 插件工作克隆（scratch，**闲置 24h 会被清理，先抢救**） | `<HERMES_HOME>/cache/scratch/checkmargin/plugin`，分支 `feat/recall-check-margin` = `b7b5a64`，base `76689f9`，7 文件 +328 −7（测试 246 行） |
| 既定插件检出（**工作位置，在本仓库内**） | `vendor/holo-check/plugin`：main `76689f9`＋未提交 C 补丁工作树（7 文件与 b7b5a64 同），origin 指向本地 `vendor/holo-margin/plugin`；vendor/ 不入版本管理 |
| 上游 main 现态 | `ceb802be781e9e31cd9509755ad18ea46194a774`（v0.31.4，2026-11-24 合并 #133） |
| 本线文档 | `C:/aiprojects/hermes-optimization/memory/threshold-calib/upstream-check/`：`RUNBOOK.md`（H5 节）、`PR-BODY.md`（旧稿，需重写）、`README.md`（**完整复现配方，含供电命令与探针命令**）、`holo-recall-check-margin.patch`（旧 LF 补丁）、`gate-five-sets.txt`/`gate-seven-sets.txt`（旧门禁回执）、`rows/`（旧 14 文件 2136 行） |
| 供电脚本（instruction 在这里，不在插件里） | `memory/threshold-calib/embed_endpoint.py`（bge-m3，端口 12371）、`memory/threshold-calib/rerank_endpoint.py`（Qwen3-Reranker-0.6B，端口 12372，logit 刻度，yes logit > no logit 即 score > 0） |
| 模型权重 | 仓库 `vendor/models/bge-m3`、`vendor/models/qwen3-reranker-0.6b`（vendor/ 不入版本管理）；HF cache 亦有 `models--BAAI--bge-m3`、`models--Qwen--Qwen3-Reranker-0.6B` |
| 测试环境 | Python 3.11；`HERMES_AGENT_REPO` = `memory/keyword-gate/core_shim`（kg-1 分支 commit `e8a31a1`）；`HERMES_HOME` 用空沙盒目录；全量套件参照 `vendor/hermes-agent`（Hermes main `152fe189`） |
| 旧测量行（scratch 副本） | `<HERMES_HOME>/cache/scratch/gate-rows/`，`git_sha` 带 `-dirty`，旧 schema `margin=0.5 / margin_check=1.0`——正是维护者点名要改的 |
| 提交身份（沿用，勿改全局配置） | `找不到工作的路边野狗 <288790282+liwangcc@users.noreply.github.com>` |

旧补丁已实现：`embeddings.RECALL_CHECK_MARGIN`（None 默认）、`__init__.py` prefetch 内每轮至多一问、`rerank.scores(single=True)`、探针 `--recall-check-margin`、gate 报告带复核臂。旧验证：16 新用例 15 红＋1 对照，合跑 46 通过，ruff 干净。

## 3. 工作项

**W0 抢救＋rebase（全部在工作目录内）。** 既定插件检出在本仓库 `vendor/holo-check/plugin`（vendor/ 不入版本管理）：main `76689f9`＋未提交的 C 补丁工作树，origin 现指向本地 `vendor/holo-margin/plugin`。步骤：① 把 scratch 克隆 `<HERMES_HOME>/cache/scratch/checkmargin/plugin` 加为临时 remote 并 fetch，**抢救已提交分支 `b7b5a64`**（scratch 闲置 24h 会被清理，提交历史先救进来）；② 加 upstream `https://github.com/itpartypattaya/hermes-plugin-holographic.git` 并 fetch main；③ 从 `ceb802b`（或届时最新）开重做分支，以 `b7b5a64` 的改动为起点（工作树已有同一份补丁，逐文件核对一致后再动）；④ 解决冲突。分支不带 HOLO-1、HOLO-4、B 的任何改动。记录最终 base SHA。**不把工作克隆挪出工作目录**，测量与交付都在这条检出里做。

**W1 单函数接口（评论末段）。** 把复核收在一个函数后：`(message, fact) → yes / no / not_answered ＋ raw score`。`not_answered`（未发出/失败）在召回上等同 no，但行里要能区分。探针侧可换入另一个 checker（维护者将在 `tools/` 加 OpenAI Decisions checker，不改插件代码）——设计好注入点（如模块级可替换 callable），PR 里不含任何 OpenAI 特定代码。

**W2 守卫与成本（第 3 点）。** 对照 `rerank.py` 现有守卫逐项补齐：一次超时、失败后暂停、**message 和 fact 双方**的密钥与长度筛查、embeddings＋check 都在 prefetch 预算内（跑 `provenance_budget` 模式留回执）。**只在 rerank off 时运行**；现补丁在 rerank on 时复用 rescorer——改为不运行，并在 PR/文档写明 on 时的行为。文档加一句：设值后 message＋一条 fact 会发给 checker 端点（rerank off 时它今天什么都收不到）。

**W3 行 schema 与配对（第 2 点）。** 两臂普通 `margin` 相同（都是 1.0）；0.5 作为**新 check 戳**（如 `check_margin`）进行与文件名（保留 `_c0.5` 后缀语义）；新戳加入 `_HEAD`，使 `--pair margin`/`--pair embed_text` 拒绝 check margin 不同的两次运行；off 臂与 0.5 臂的配对走新戳（设计新配对路径或扩展 `report_margins`，给出**精确 gate 命令**写进 PR 正文）。行里带：checker 真实模型名（不能再是 `probe-reranker`）、instruction 文本的 sha256、调用数/结果/耗时/raw score——**包括零产出的 turn**。行必须出自单一干净提交（先 commit 再跑探针，`git_sha` 不带 `-dirty`）。

**W4 测试（第 1 点）。** 逐条对照：unset → 召回不变＋零 checker 调用；合格 turn → 恰好一次调用；accept / reject / 失败调用各有覆盖；失败保留基线结果。缺的补上。**每条在 main（新 base）上红、且红的原因就是它命名的原因**——在 main worktree 实跑留输出为证，不许 skip。合跑既有 46 用例口径不回退；全量套件重跑，`test_holographic_blas_threads.py` 的既有失败在干净 main 克隆上对照确认（数字随 0.31.4 可能变，如实报）。ruff 干净。

**W5 重跑测量。** 按 `upstream-check/README.md`「复现端到端」配方：起 12371/12372 两个本机接口，七题集各跑两臂（off / `--recall-check-margin 0.5`），test split 五集 540 为决定池，household dev＋synthetic_zh 并列报告（696 池）。**目标复现 A11 已公开数字**：540 池 480→486、b6/c0、p≈0.031、噪声 93→93、混淆 34→34；696 池 565→573、b8/c0、p≈0.008、142→142、46→46。instruction 用 `rerank_endpoint.py` 里那一份，一字不改。数字漂移、冲突解不开、instruction 有疑 → **停下报告，不调门禁、不改题集、不凑数**。

**W6 可复现包（第 5 点）。** 供电脚本版本（commit SHA）＋两个模型的精确版本（vendor 目录来源/HF revision）、instruction 全文＋sha256、pair format（query=message、document=fact 单行内容，以代码为准）、一条合成 request/response 展示 score→yes/no 映射（logit 刻度 >0 为 yes）。落盘到本仓库 `memory/threshold-calib/upstream-check/repro/`（未提交，等审）。

**W7 PR 正文（英文，重写 `PR-BODY.md`）。** 逐条对应 5 点要求＋单函数接口；第 4 点披露原话口径：bge-m3＋Qwen3-Reranker-0.6B，0.5/规则/instruction 均在同一批题集上选出，p 是探索性；第二模型冻结复现＝维护者的 te3-small 跑；确认需未参与选题的问题。写明精确 gate 命令、行戳含义、rerank on 时行为、数据去向句。提交按可回退粒度拆分（ wiring → 接口 → 守卫 → 行/门禁 → 测试 → 文档），PR 说明建议直接 merge 不 squash。

**W8 文档与日志。** 更新 `RUNBOOK.md` H5 节与 `upstream-check/README.md` 复现配方至新 schema；`SUBMISSION-LOG.md` 末尾**追加**本次工作行（只追加，不改旧行）。hermes-optimization 仓库内所有改动**保持未提交**，等用户审阅；提交与推送分别等明确指令。

## 4. 红线

- 不 push、不开 PR、不发评论、不做任何远端写（fetch 只读可以）。
- 不碰日常安装 `<HERMES_HOME>/plugins/holographic`、`<HERMES_HOME>/plugins/holographic-semantic`。
- 不改门禁判定数学凑过；只按第 2 点加戳与配对 wiring。不改题集、targets、噪声/混淆定义。
- 不碰私有真实库、不做任何导出（维护者明说不需要 opaque export）；行里只含上游公开测试数据。INTERNAL-* 文件的私有内容不进 PR 与公开文档。
- 不扩 scope：无 B/floor、无 HOLO-1、无用户可见设置、无 OpenAI 特定代码。
- 失败如实报告，不伪造数字、不用调超时/重试掩盖问题。

## 5. 交付与报告格式

交付清单：① PR-ready 分支（最终 SHA、base SHA、diff stat）② main 红测试证据＋分支绿回执 ③ 干净 SHA 新行＋两池 gate 回执＋budget 回执 ④ repro 包 ⑤ 英文 PR 正文 ⑥ 更新后的 RUNBOOK/README＋日志追加行（未提交）。

报告按「完成 / 失败 / 剩余」三段，每项带路径、SHA、回执原文位置；任何停下原因原样给出。Hermes 将按清单逐项验收（远端状态以 API 读回为准，本地数字以门禁回执为准）。
