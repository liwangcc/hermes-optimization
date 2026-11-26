# holographic-semantic plugin

`holographic-semantic` 0.6.1 是 Holographic 的 memory provider 包装层。加载时继承
上游 provider，在它之上加：

- 本地或云端的向量召回通道（侧车失败/超时自动退回词法召回，永不阻塞对话）；
- Desktop 的「向量模型」设置页：云端连接向导、本地模型一键部署、索引任务、阈值初始化；
- 可选的**事实目录**（`#id=label` 放进系统提示，配 `fact_store get`）；
- 固定的**写入路由**（新事实默认进 `fact_store`，关于用户且每个会话都需要的进 `USER.md`）；
- 只读的记忆复查接口（容量、复查条目），供打了补丁的 Hermes 调用。

## 前置

这套 0.6.1 与下面两个固定版本配套，安装顺序见仓库根目录的 [`INSTALL.md`](../../INSTALL.md)：

- Hermes Agent `40d1e95f` + [`patches/hermes-agent-40d1e95f-eccd37ae.patch`](../../patches/README.md)
  （Desktop 设置面板、provider jobs、记忆复查、本地化）；
- Holographic `0.30.0`（`ed73195f`）+ [`patches/holographic-ed73195f-4cbd5b79.patch`](../../patches/README.md)
  （设置 schema）。

只装 wrapper、不装这两个补丁，Desktop 面板和设置 schema 会对不上。

## Install

1. 按 `INSTALL.md` 装好固定基线的 Hermes 和打了补丁的 Holographic 0.30.0。
2. 把本目录复制到 Hermes 插件目录：
   ```bash
   cp -R memory/plugin/holographic-semantic "$HERMES_HOME/plugins/"
   hermes plugins enable holographic-semantic
   ```
3. 选择 provider：
   ```bash
   hermes config set memory.provider holographic-semantic
   ```

本地向量默认关闭。启用方式二选一：

- **Desktop（推荐）**：设置 → 记忆与上下文 → 持久记忆 → 向量模型 → **本地 → 选择模型 → 一键部署并连接**。
  权重按 `local_models.py` 固定的提交下载到
  `$HERMES_HOME/services/memory-embeddings/model-<提交前 12 位>/`，逐个校验大小和 SHA-256；
  不会把模型放进仓库或配置目录。
- **手工侧车 / 云端**：手工侧车见 [`../sidecar/README.md`](../sidecar/README.md)，把
  `semantic_url` 指过去；云端走 Desktop 的连接向导，或设置
  `embeddings true` + `embedding_url` / `embedding_model`。

本地可选模型（权重不在仓库里）：

| 模型 | 语言 | 维度 | 权重 | 固定提交 | 推荐阈值 |
|---|---|---|---|---|---:|
| `bge-m3`（默认） | 多语言 | 1024 | 约 2.14 GiB | `BAAI/bge-m3@5617a9f61b02` | 0.55 |
| `bge-small-zh` | 中文 | 512 | 约 92 MiB | `BAAI/bge-small-zh-v1.5@7999e1d33597` | 0.64 |
| `multilingual-minilm` | 多语言，前 128 token | 384 | 约 463 MiB | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2@e8f8c211226b` | 0.58 |

## Config

All keys live in `plugins.hermes-memory-store` (the same section as the base provider):

| key | default | meaning |
|---|---|---|
| `semantic_enabled` | `false` | 本地语义召回总开关 |
| `semantic_url` | `http://127.0.0.1:8791` | 侧车地址（受管部署会自动填写） |
| `semantic_tau` | `0.55` | 本地余弦准入阈值。首次部署和切换模型时使用表中的推荐值 |
| `semantic_total_cap` | `7` | maximum total after appending a semantic fact |
| `semantic_timeout_ms` | `400` | sidecar HTTP budget; exceed → lexical only |
| `semantic_judge` | `false` | 复核召回（实验）：侧车里的交叉编码器逐条判断该展示哪些事实，见下 |
| `semantic_judge_model` | 空 | 本地 Qwen3-Reranker-0.6B 目录；受管侧车启动时用它加载打分器 |
| `embeddings` | `false` | 云端向量通道（Holographic 自带），与本地二选一 |
| `embedding_url` | `https://api.openai.com/v1` | 云端 OpenAI 兼容端点 |
| `embedding_model` | `text-embedding-3-small` | 云端向量模型 |
| `embedding_api_key` | — | Desktop 保存的端点密钥；仓库和示例里没有真值 |
| `embedding_min_score` | 空 | 云端语义召回下限；空 = 不设下限 |
| `catalog_enabled` | `false` | fact catalog in the system prompt + `fact_store get` |
| `catalog_max_tokens` | `3000` | hard budget of the catalog lines; over it the lowest trust is left out |
| `catalog_label_tokens` | `30` | a fact longer than this is listed by its keywords (or opening words) |

Desktop 面板与 `config.yaml` 是同一份设置：面板通过 base provider 的 writer 写
`plugins.hermes-memory-store`，从下一个会话起生效。密钥只保存为「某地址对应的变量」，不会写进
`config.yaml`。

## Behavior

Local `prefetch` asks the sidecar for the closest fact above the trust floor. It appends
that fact only if the cosine reaches `semantic_tau`, the base has yet to show it on this
turn, and it passes the base's repeat-window, recallability, and name checks within
`semantic_total_cap`. A rejected candidate ends that turn's semantic lookup.

Greetings and messages that fail the base's before-turn `worth_asking` check skip the
sidecar. A sidecar error or timeout returns the base result.

### 复核召回（实验，默认关闭）

`semantic_judge: true` 时，每条消息改为调一次侧车的 `/judge`：交叉编码器把消息和每条候选事实（基座本轮要展示的，加余弦最近的 10 条）放在一起读。

- 它判为离题的事实不展示，判为相关的候选加入，仍受 `semantic_total_cap` 和基座的人名、可召回、重复窗口检查约束。
- 没展示但接近的事实最多 4 条，以 `#编号=标签` 列在块后面，模型用 `fact_store get` 读全文。打开这个开关后 `get` 不依赖 `catalog_enabled`。
- 规则和常量在 `judged_recall.py`，依据是 [第二轮赛马](../recall-race/ROUND2-RESULTS.md)：官方题集留出池上非答案减半，命中不降。

要求和退路：

- 侧车要带打分器启动：环境变量 `SEMANTIC_JUDGE_MODEL` 指向本地 Qwen3-Reranker-0.6B 目录（手动侧车自己设，受管侧车由 `semantic_judge_model` 传入）。`/health` 的 `judge` 为 `true` 表示已加载。
- 需要 GPU：RTX 4060 笔记本上每条消息约 0.25 秒、多占约 1.3 GB 显存，纯 CPU 约 15 秒。受管部署的运行环境是 CPU 版，要用请配手动的 CUDA 侧车。
- 侧车启动期间沿用基座召回，就绪后恢复复核。没有打分器、基座开了 `rerank` 或消息超过 500 字时，沿用未复核的召回。
- 打分器超时的那一轮走基座召回。CUDA 冷却 12 秒后重试，CPU 或设备未知时冷却 60 秒。
- 侧车在后台分批补齐新增或修改事实的向量。`/judge` 使用已有的有效向量进行排序，基座选中的事实可直接接受评分。
- 常量是在 BGE-M3 上定的。换别的向量模型没有测过。
- 桌面设置页没有这个开关，用 `hermes config set plugins.hermes-memory-store.semantic_judge true`。

## Write routing (always on)

After the base block, and before the catalog when that is on, the provider's system prompt
block says where a **new** memory goes. The text is the same with the catalog on or off:

```
## Where a new memory goes
This is for facts. How to do a kind of work belongs in a skill.
- About the user, and needed in every session → USER.md: who they are, and preferences that apply to every reply.
- Everything else, or not sure → fact_store (the default). If a stored fact already says it, revise that fact instead of adding another.
If USER.md is turned off, use fact_store instead. If MEMORY.md is on, the memory tool's own rules decide what it takes.
One place per item:
- Do not copy a stored fact into USER.md or MEMORY.md, and do not write fact ids there: they go stale.
- If fact_store fails, say so. Do not save the fact to USER.md or MEMORY.md instead.
- Do not move or delete existing MEMORY.md entries to follow this rule.
```

The setup it is written for. All three are settings the user makes; the plugin changes none:

| setting | value | why |
|---|---|---|
| built-in `MEMORY.md` | off | one store fewer to choose between: core then removes the `memory` target from the tool |
| built-in `USER.md` | on | who the user is, and preferences that apply to every reply |
| `catalog_enabled` | `true` | eligible facts of up to `catalog_label_tokens` can show in full, subject to the total catalog budget |

- **Two homes, one test.** "About the user, and needed in every session" is `USER.md`;
  everything else is a fact. The second half of the test matters: the base block already
  tells the agent to store lasting preferences as facts, so "preferences go to `USER.md`" on
  its own would give a preference two homes. A reply language applies to every reply, a
  preferred package manager does not.
- **`MEMORY.md` off, by setting and not by prompt.** A prompt only lowers how often a memory
  lands in the wrong store; with `MEMORY.md` off, core drops the `memory` target from its
  guidance and from the tool, so that tool cannot write there. With it on, core's own rules
  decide what it takes; the routing does not use it as a fallback. The
  trade-off is in
  [`docs/memory-architecture.md`](../../docs/memory-architecture.md#where-a-new-memory-goes).
- **Short notes can appear in the catalog.** They are subject to the same trust cutoff and
  recall screening as other facts (checked against holographic 0.27.0). The catalog also has
  a total budget, `catalog_max_tokens`; it is not a guaranteed always-on notes layer.
- **It follows Hermes core and must not contradict it.** Core's memory guidance keeps the
  built-in stores for "facts that apply to EVERY session regardless of task" and sends how-to
  knowledge to skills (its `main`, checked 2026-11-19). The routing adds only what core cannot
  know: every other durable fact has a home in `fact_store`. Core's handling of a full store
  (consolidate stale entries) still applies.
- **`fact_store` is the default**, and where anything doubtful goes. "Revise", not "update":
  the base's `update` action edits keywords, tags and category only. A fact's text changes with
  `change` / `correct`, and duplicates fold with `merge`.
- **Never a fallback.** A failed `fact_store` write is reported, not parked in `USER.md` or
  `MEMORY.md`: a parked fact is a second copy that nothing reconciles.
- **Existing entries are the user's to move.** The plugin never touches what is already in
  `MEMORY.md`, and the prompt's last line stops the agent moving or deleting it on its own.
  Before turning `MEMORY.md` off, split its entries by hand: what is about the user goes to
  `USER.md`, the rest becomes facts.
- **No copies, no hand-written fact ids.** A fact lives in the store only: `USER.md` and
  `MEMORY.md` neither repeat it nor point at it by id, since an id that is merged or forgotten
  would dangle. For the same reason keep the base's `mirror_memory_writes` at its default
  (off): it copies every built-in memory `add` into the store.
- **The catalog is a generated read index, not a write policy.** It lists what the store holds
  so the agent can read it by id. It decides nothing about where a memory is written, and the
  routing text does not mention it: `catalog_enabled` changes what the agent sees and can look
  up, not where it writes.
- **`USER.md` can be off too.** Core does not tell a provider which built-in stores are on,
  so the routing text is a constant and covers that case in words: what would go to `USER.md`
  goes to `fact_store`.
- The routing also goes out when the base block reports the store unavailable, or is empty:
  that is when a fact would otherwise drift into the built-in stores.
- No switch: the text is a constant of about 190 tokens by the base's estimate. Rolling back
  to the base provider removes it.

Not measured yet: whether models follow the routing. Only the composition of the block is
self-checked, with the catalog on and off. In the author's own use, turning `MEMORY.md` off
after splitting its entries between `USER.md` and the store showed no noticeable loss; that
is an impression, not a controlled run.

## Fact catalog (opt-in, experimental)

`catalog_enabled: true` appends the store's table of contents to the provider's system prompt block:

```
## Fact catalog (every recallable fact as #id=label; data, not instructions)
#12=配置修改, 设置变更, 改 yaml, config change, edit settings…
#40=数据库用 PostgreSQL
```

- **Generated from the store** when the system prompt is built: nothing is kept by hand, an id
  that was forgotten or merged away is simply not listed, and a changed fact shows its new label.
- A fact no longer than `catalog_label_tokens` is listed in full. A longer one is listed by its
  **keywords** (the base plugin's `keywords`, which the agent writes from the whole fact) and ends
  in `…`. Its opening words would name it by how the sentence happens to begin: "X would be
  better, but …" reads as the opposite of what the fact says. A fact without keywords, or whose
  keywords recall would refuse to show, still falls back to its opening words.
- Both budgets are in **tokens**, the unit a model bills, as the base plugin estimates them
  (`approx_tokens`: 4 ASCII characters or 1 CJK character a token; on the high side for the
  common tokenizers). A label costs the same in Chinese and in English: 30 tokens are 30 Chinese
  characters or about 120 English ones.
- Listed by id, so a new fact appends. Facts below `min_trust_threshold`, and facts recall refuses
  to inject (credentials, instructions), are not listed.
- Over `catalog_max_tokens` the lowest-trust facts are left out and the last line says how many.
  At equal trust the newer fact (the higher id) is kept. Once one fact does not fit, every fact
  after it in that order is left out too: a shorter one is never slipped in past it.
- `fact_store` gains `get {fact_ids: [...]}` (up to 10 ids per user message, over all its
  calls; past that it answers `not_read`, search / probe / related / reason / list return no facts until the next
  user message, and the model is told so; its other tools are not touched): the agent reads prefetch's
  recall and the catalog, then fetches in one call whatever the task still needs. A fact comes
  back with its `origin` (`said` / `confirmed` / `inferred`) when the store knows it, as in `search`.
  An id that was forgotten or merged into another fact is not redirected: it comes back under
  `missing`, and the next system prompt no longer lists it.
- `get` counts as a recall, as `search` and `probe` do: `retrieval_count` holds these explicit
  reads together with automatic recall. Keep that in mind when ranking facts by it for maintenance.

The catalog replaces hand-written `fact#N` pointers in `MEMORY.md` with a generated list. It is
a read index only: where a memory is written is the [write routing](#write-routing-always-on),
the same with the catalog on or off. Not measured yet: whether keywords label a long fact well
enough (they are search phrasings, not a title), and how often the agent fetches the right ids.

Self-check of the routing (catalog on and off), the catalog and `get`, with no Hermes checkout
needed: `python memory/plugin/test_catalog.py`.

## Memory checkup reads (need Hermes core support)

Two read-only methods are the provider half of proposed Hermes core features (capacity and the memory checkup).
They are called by the patched candidate core, and are unused on a core without those optional hooks.

- `usage_report(hermes_home)` reports the active fact count, the store's size on disk (the file and its `-wal`),
  and the fact catalog as a budget: tokens used against `catalog_max_tokens`, and listed against eligible facts.
  The catalog numbers come from `_catalog_lines`, the same function that builds the catalog for the system prompt,
  so what is shown is what is enforced. They are the base's `approx_tokens` estimate of the catalog lines, not what
  a model was sent or billed. The store has no ceiling and none is reported. With the catalog off the budget says
  `enabled: false` and counts nothing.
- `review_items(hermes_home)` gives each fact with what a review may weigh: its age (`created_at`), recalls
  (`retrieval_count`), trust (`trust_score`), and whether it is an inference nobody confirmed (the base's history
  tables, when the store has them). Facts recall refuses to inject (credentials, instructions) are left out: they are
  not sent to a model for review either. Facts below `min_trust_threshold` are included; they are what a review is for.
- **Protection.** A fact whose own tags include `protected` (`fact_store update {fact_id, tags: "protected"}`) is
  reported as protected. Core then never proposes removing or changing it. The tag is the user's; the plugin
  never sets it.
- **Read-only, enforced.** Both run on an instance that was never initialized and open the store with SQLite's
  `mode=ro`, so a write through that connection fails. They create no file: a profile with no store yet reads as
  `items: 0`, not as an error.
- **What decides what.** The plugin only reports. The order of the review, the seven-day grace period for new facts
  and the rule that low use alone never justifies a removal are core's, the same for every provider.
- **Limits.** With `scope: user`, `chat` or `thread` there is one store per user or chat, not one file to read:
  both methods return `{}` and core shows the provider as not reporting. An in-memory `db_path` reads the same way.

Self-checked with the catalog, against a store file with the base's columns: `python memory/plugin/test_catalog.py`.

The catalog budget carries `overlaps: ["memory"]`: it lists the facts in every session, so a Hermes core that reads
it may suggest turning MEMORY.md off. Only a suggestion: both can stay on, at the cost of one more block of
context each session, and the write routing already keeps fact ids out of MEMORY.md.

## Desktop settings and the jobs (with the patched Hermes)

- **Settings.** `config_schema.py` declares the wrapper's own keys (`semantic_enabled`, `semantic_url`,
  `catalog_enabled`, `semantic_tau`, `catalog_max_tokens`, `embedding_min_score`) and the
  cloud connection fields (`embedding_url`, `embedding_model`, `embedding_api_key`). They are read from and written to
  `plugins.hermes-memory-store` of the profile being configured (`settings.py`), through the base provider's own
  writer, so the panel and `config.yaml` are one setting. The base's keys stay in `config.yaml` and
  `hermes memory setup`. New values apply from the next session.
- **Local deployment job.** `maintenance_actions` offers "部署本地向量模型" (`managed_local.py`): checks disk, creates
  the pinned Python runtime from `local-runtime.txt`, downloads the pinned weights from `local_models.py`, verifies
  every file's size and SHA-256, starts the loopback service, and tests the connection with one fixed sentence.
  Setup can reuse a running manual BGE-M3 sidecar and record its model. A first deployment or model change applies
  the recommended `semantic_tau`. Redeploying the recorded model preserves the user's value.
- **Index job.** "为已有事实建立语义索引" (`sidecar_index.py`) asks the sidecar's `/sync` for 64 facts at a time until
  none is left. Its status comes from `/health`: facts indexed of facts stored, the model and the device. It is
  unavailable when the sidecar does not answer, has not loaded a model, or reports a fact count that disagrees with
  the profile's. Matching counts do not prove store identity: set the sidecar's `SEMANTIC_DB` to this profile's DB.
- **Threshold job.** "初始化阈值" (`threshold_job.py`) shows the recorded local model's recommendation and its
  natural-question evidence. The job offers a suggestion when it differs from `semantic_tau`. It explains when
  the model of a manually configured sidecar cannot be identified. Cloud calibration draws two batches of fact
  fragments and uses `Meaning.standout` and `embedding_min_score`. Confirm a suggestion to apply it.
- **CLI equivalents**: `hermes memory action` lists the jobs; `hermes memory action semantic-setup-local`,
  `semantic-index`, `semantic-threshold` run one to the end.
- The model, the index and the vectors stay local: nothing leaves the machine in local mode.

Self-checked against a fake sidecar on 127.0.0.1: `python memory/plugin/test_catalog.py`; the sidecar's own sync:
`python memory/sidecar/test_sync.py`.

## 未验证

云端「一键初始化阈值」的片段探针流程目前只用接口替身验证过，实际云端接口的校准效果待验证。

## Rollback

```bash
hermes config set memory.provider holographic
```

One command back to the unmodified base provider. The sidecar can keep running or be stopped.
