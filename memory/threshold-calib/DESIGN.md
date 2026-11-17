# 嵌入阈值标定工具：设计

> 一句话：**把尺子交给用户。** 对任一 OpenAI 兼容嵌入模型 × 任一事实库，扫描语义准入规则的参数，输出
> 「阈值 → (recall@5, 噪声, 混淆, McNemar)」工作点曲线，每个点都按上游 PR #17 的四条件门禁对上游默认判一次。
> **不改默认、不自动套用、不替用户选点。**

本目录里没有任何真实结果。`dryrun/` 只来自 stub 嵌入器，用来证明管线接通了；数字只能来自真实 run。

---

## 1. 为什么要这个工具

- 维护者关闭 #95 时说 floor 阈值"跨模型不通用"。上游注释自己也写着：同一条改写，在 text-embedding-3-small
  上的余弦是 0.38–0.66，在 gemini-embedding-001 上是 0.68–0.84（`embeddings.py:63-66`）。
- 用锚点做跨模型移植已经证伪（Hermes 的实验，见 brief §一；那些数字是背景，不属于本工具）。所以阈值只能
  **逐模型、逐库实测**。
- 维护者的一贯做法是"收尺子、不改默认"（#31、#101、#102，以及 rerank 先例）。本工具因此定位为 opt-in 的测量工具
  加参考数据，不改变任何默认行为。

## 2. vendor 核对（锚点一致，不触发停止条件）

| 锚点 | 位置 | 本工具怎么用 |
|---|---|---|
| `RECALL_MARGIN = 1.0` | `embeddings.py:75` | 默认点；从加载后的模块实时读出，写进 manifest |
| `z_bar = sqrt(2 ln N) + margin` | `embeddings.py:89-91` | 通过 `Meaning.standout` 间接调用，不自己重写 |
| `Meaning.standout(fact_id, margin, min_score)` | `embeddings.py:753-761` | 三条规则全部走它（floor 走它的子类） |
| `Meaning(ids, matrix @ vector, ...)` | `retrieval.py:665-669` | 相似度用同一种方式算：float32 矩阵乘向量，ids 按 fact_id 排序 |
| `Retriever.by_meaning` 的循环 | `retrieval.py:708-714` | `walk()` 照抄：按 ranked 顺序走，遇到第一个不准入就停，跳过 trust 不够的事实（NULL 也不合格） |
| prefetch：`by_meaning(limit=recall_facts+3)`，再经 `_recallable` 等过滤后取 `recall_facts` 个 | `__init__.py:1362-1371`、`:1605-1609` | `walk()` 先取 `keep+3` 个候选，去掉 `_role_prompt` 事实（可发送的事实一定没有 `_recall_problem`），再取前 `keep` 个；`--keep` 默认 1、上限 3，与插件一致 |
| 消息先过 `_secret_in` 和 `worth_asking` 才会被嵌入 | `__init__.py:1522-1523` | 每个探针都过这两道 |
| 事实先过 `screen._sendable` 才会被发送 | `screen.py:1046` | 每条事实都过这一道 |
| `mcnemar()`、`_noise()`、#17 四条件 | `tools/mcnemar_gate.py:31,163,173-272` | 门禁直接调用这两个函数，四条件逐条照写 |

**需要知道的一个事实**：上游其实**已经有**一个绝对 floor，就是 `embedding_min_score`。但它是 **AND 型**的：
库里向量数 N ≥ 20 时，它只能在 z_bar 之上再收紧，从不放宽；N < 20 时，它是唯一能让事实准入的规则。brief 说
"原生没有绝对 cos floor 准入模式"，指的是**放宽型** floor（用 cos ≥ t 替换 z_bar），这个说法成立。于是：

- 轻路能标定的上游旋钮有**两个**：`RECALL_MARGIN`（margin）和 `embedding_min_score`（AND 型 floor）。
- 放宽型 floor 上游没有，属于重路。

锚点由 `tests/test_admission.py::test_the_vendored_anchors_are_where_the_brief_says` 固定住：vendor 一变，测试就红。

## 3. 架构：标定引擎与准入规则解耦

```
facts: JSON 列表 | SQLite 库的只读副本 ──┐
probes: labelled 文件 | auto 自动生成 ───┤
                                         ▼
       插件自己的筛选: screen._sendable(事实)、_secret_in + worth_asking(探针)
                                         ▼
       插件自己的客户端: embeddings.Embedder（或 stub：覆盖 _request，从不开 socket）
                                         ▼
       sims = matrix @ vector （与 retrieval.meaning 相同；holdout 探针去掉它自己那条事实）
                                         ▼
       每个探针: vendor Meaning / FloorMeaning，ranked() 只算一次
                                         ▼
       准入规则 (rule, value) ──► walk() = by_meaning 的循环（trust 过滤，keep+3 个候选）+ _recallable + 取 keep 个
                                         ▼
       rows.jsonl: 每个 (rule, value, 探针) 一行，只记准入的 fact id
                                         ▼
       calib_gate: 每个点对默认点 → 工作点曲线 + #17 门禁 → summary.json / report.md
                                         ▼
       calib_opaque: 剥掉所有文本 + leak-scan → 唯一允许离开本机的形式
```

| 文件 | 管什么（一句话） |
|---|---|
| `calib_vendor.py` | 只读加载插件快照里准入要用的模块，提供三条规则的参数映射、floor 子类，以及 by_meaning 循环 |
| `calib_probes.py` | 读事实和探针：labelled 文件，或从库里自动生成的 fragment / holdout / chit |
| `calib_cost.py` | 跑之前估算 token 数和费用 |
| `calib_run.py` | 一次标定 run：嵌入一次，扫描所有规则的所有取值，写 rows，然后调用门禁 |
| `calib_gate.py` | 从 rows 算工作点曲线和 #17 门禁，写 summary.json / report.md |
| `calib_opaque.py` | opaque 导出：白名单字段 + token 正则 + 任一处有文本就整体拒绝 |

**适配器接口**：一条规则只回答一个问题——`Meaning.standout` 拿到什么参数，或者用哪个 `Meaning` 子类。新增规则时
只需要在 `standout_args` 里加一个分支，或者加一个子类；引擎、rows 格式和门禁都不用动。这就是 brief §四推荐的分层：
维护者可以只收引擎和两条上游规则（轻路），floor 规则作为可选的 experimental 件另外谈。

## 4. 准入规则

| rule | value 的含义 | 上游现状 | 路线 |
|---|---|---|---|
| `zbar` | margin：`z ≥ sqrt(2 ln N) + value` | 上游准入，默认 1.0 | 轻路 |
| `zbar_floor` | `embedding_min_score`：cos ≥ value，**并且**满足默认 z_bar | 上游可选配置键，默认不设 | 轻路 |
| `floor` | cos ≥ value 单独就能准入，不看 z_bar | 实验，不提议当默认 | 重路 |

- `zbar` 和 `zbar_floor` 直接调用 vendor 的 `Meaning.standout(fact_id, margin, min_score)`。
- `floor` 是 `vendor Meaning` 的子类 `FloorMeaning`，只覆盖 `standout` 一行：`s is not None and s >= floor`，
  语义逐字等于 KG-1 的 `patches/admission_floor.diff`。vendor 不需要原地修改。
- 默认点（`zbar` 取 `RECALL_MARGIN`）**每次 run 都会被扫描**，其它所有点都拿它作对照。

## 5. 探针：不调 LLM，一键，无需手工标注

- **labelled**：用户自己写的查询文件（`../eval/queries.json` 的格式，或 KG-1 的统一格式）。如果有真实改写，这种模式
  给出的曲线最可信。插件不会嵌入的探针（问候语、太短、像密钥）保留为 `skipped` 行，在所有点上都没有语义准入，
  与插件实际行为一致。
- **auto**（不给 `--queries` 时）：只从 prefetch 有可能准入的事实里抽（可发送、trust 合格、不是 role prompt；否则
  正例永远命中不了），按 `--seed` 打乱顺序，每条事实取正文的中间一半作为探针（CJK 按字计、其它文字按词计，
  切的是原文，保留原有空格和标点）。
  - `fragment`（占 3/4）：源事实留在库里，它就是目标（正例）；
  - `holdout`（占 1/4）：问的时候把源事实从库里去掉——问题仍在本领域，但库里没有答案，此时任何准入都算噪声；
  - `chit`：10 条内置闲聊（中英各 5 条），每条都能通过插件的 `worth_asking`。
  - 插件不会嵌入的片段直接丢弃，再往后抽下一条事实补上；默认 `--auto 40`，加上 chit 一共约 50 个探针（brief §五）。
- **设计理由**：fragment 和 holdout 出自**同一个生成过程**，唯一的区别是源事实在不在库里。所以曲线直接衡量的是
  "这个阈值能不能把有答案和没答案区分开"。
- **偏差（必须披露，报告里自动写明）**：fragment 和源事实在字面上有重叠，因此 auto 模式的 **recall 偏乐观**，
  真实改写的 recall 会更低；**噪声侧**（holdout、chit）和**混淆**是可信的一侧。建议 Hermes 在合成集上用同一个模型
  分别跑 auto 和 labelled，把这个偏差量化出来。

## 6. 工作点曲线与门禁口径

每个点的指标（rows 里只有准入的 id，指标都由 `calib_gate` 从 id 和 targets 推出，信息只有一个来源）：

| 指标 | 定义 |
|---|---|
| recall@5 | 有标注的探针中，目标出现在准入列表前五位的比例（只看语义通道：准入列表就是全部输出） |
| noise | vendor `_noise()`：chit 有输出，或者无答案的 real 探针（holdout）有输出 |
| confusion | 有标注的探针，语义准入的**第一个**事实不是目标（没有对的，或者错的排在对的前面）。keep=1 时就是"准入的那条是错的"。无答案探针的输出只算噪声，不重复算混淆（与 KG-1、`two_topics_set.py` 一致） |
| extra（只展示，不进门禁） | 有标注的探针上准入的所有非目标事实条数。keep>1 时，排在正确事实之后的多余事实只计入这里：它是精度代价，但 #17 的 confusion 只算错实体，不算多出来的条目 |
| b / c / p | 相对默认点：b = 救回的，c = 丢掉的；p 用 vendor `mcnemar()`（精确双侧二项检验） |
| lost / gained | 按 #17 的定义：目标在默认点的前五里、不在该点的前五里，记为 lost；反过来记为 gained |

**门禁**：#17 四条件，与 `mcnemar_gate.py report_margins` 同一口径——不丢目标、噪声不增、混淆不增、
McNemar p < 0.05。没有直接跑 `report_margins`，原因是它的 `_confused` 只认 household / multi / contrast_* 三种 set，
标定 rows 不属于其中任何一种，冒用 set 名不诚实。所以本工具调用它的 `mcnemar` 和 `_noise`，四条件逐条照写。
KG-1 额外要求 "b > c" 的方向；在"不丢目标 + p < 0.05"同时成立时，这一条自动成立（c = 0 且 b ≥ 6）。

**探索性与确认性**：在同一批探针上扫很多个点，再挑最好的，会抬高显著性。所以报告里每个点的门禁都标为
"exploratory"。一个值要成为**参考阈值**，必须先用 `--margins X` 或 `--floor-values X` 单点、在**另一批探针**上
（换一个 `--seed`，或者用 labelled 集）跑一次确认 run，这一次的判定才算数。工具本身不选点。

## 7. 费用预估

- 每条文本的估算：CJK 字符约 1 token，其它字符每 4 个约 1 token。没有打包分词器（依赖只有 numpy + stdlib），
  这个估算是用来决定跑不跑的，不是账单。
- 价目（USD / 百万 token，2026-11 核实）：text-embedding-3-small 0.02，text-embedding-3-large 0.13；其它模型用
  `--price-per-mtok` 指定，没指定时明确写"价格未知"。本地端点按 $0 计。
- 发送前一定先打印 `estimate: N texts, ~T tokens, ~ $X (...)`。远程端点不加 `--yes` 就只打印、不发送。
  所有发送之前就能做的检查（地址格式、qid 重复、探针全被跳过）都放在打印预估之前。
- 地址和密钥永不打印。manifest 只记 `endpoint` 类别（stub / local / remote），连地址的哈希也不记：常见端点的
  地址可以猜出来，再算一遍哈希就能对上。
- 请求：事实按插件的批大小（32）发送，探针一条一个请求（与 `Embedder.query` 相同；服务端做带 padding 的批推理时，
  向量可能略有不同）。每个请求最多等 120 s（插件注释里有本地服务器 32 条要 7.7 s 的记录），端点死掉时也能在
  有限时间内失败退出。
- 规模参考见 brief §五（Hermes 实测的背景数据，不是本工具的结果）。

## 8. 隐私与 opaque

- **输入**：`--store` 以 `mode=ro` 打开**副本**。run 目录里有原文（`probes.jsonl` 的 `q` 就是事实片段），所以
  对 `--store` run，工具**拒绝把输出写进本仓库**。
- **发送**：事实过 `_sendable`，探针过 `_secret_in`，和插件实际发送的集合完全一致。用云端模型时，事实本来就会
  发给它（这是用户打开 `embeddings: on` 后的既有行为），工具不会多发任何东西。
- **外发**：`calib_opaque.py` 采用 KG-1 `kg_opaque.py` 的模式——字符串字段只允许白名单里的 stamp，而且必须是
  标识符字符；其余只留数字、布尔、数字列表。此外，labelled 文件里用户自己起的 qid 和 category 名也是人写的字，
  所以导出时 qid 一律改成 `q0001…`，不在内置词表里的 category 改成 `cat1…`（probes 和 rows 两个文件保持一致）。
  任何一处可能带文本，整个导出就被拒绝（错误信息只说字段名，不引用内容）；所有文件都扫描通过后才写盘。
  `calib_gate.py` 可以在导出目录上原样复算，测试证明除了被重命名的 id 之外，所有数字完全相同。

## 9. 两条路的 PR 切分建议

**轻路：只收工具，零行为变更**

- PR-L1：`tools/threshold_calib.py`，包含引擎、`zbar` 和 `zbar_floor` 两条规则、#17 门禁、费用估算、opaque 导出
  和测试；README 加一节"为你的模型标定 margin / embedding_min_score"。不改任何默认值。
- 如果维护者希望更小，可以再拆：L1a 只有 `zbar`（相当于 #31 `--recall-margin` 的扫描版），L1b 再加 `zbar_floor`。
- 参考阈值表作为文档附上（第 12 节模板），每一行都要有确认 run。

**重路：实验性准入模式**

- PR-H1：`embedding_admission: zbar | floor`（默认 `zbar`）加 `embedding_floor`。改动只在 `Meaning.standout` 的
  一个分支（即 `admission_floor.diff` 的配置化版本），附上 experimental 说明和代价披露（参照 rerank 先例）。
- PR-H2：标定引擎加上 `floor` 规则。本仓库已经实现了，用的是子类，上游不改代码也能跑。
- 依赖关系：H 线需要 L 线工具产出的证据（确认 run + 门禁）才能谈；H 线可以永远不合，L 线依然独立成立。

## 10. 局限（不隐藏）

- **只测语义通道**：词法、实体流、`names_fit`、重复窗口都不在内（trust 过滤和 `_recallable` 已经照插件实现）。在选定的点上，完整链路要用 KG-1 harness 或上游
  `provenance_probe` 复核（这是 Hermes 的事）。实际链路里 `names_fit` 还会再筛掉一些语义准入，所以真实的噪声和
  混淆只会 ≤ 这里的数，recall 也只会 ≤。
- auto 探针的 recall 偏乐观（见第 5 节）。
- token 是估算值，没有用分词器。
- 数值计算与插件相同（float32 的 `matrix @ vector`；holdout 用去掉那一行之后的矩阵）。不同机器的 BLAS 末位
  可能有差异，理论上会翻转恰好落在阈值上的判定；dry-run 的字节复现是在同一台机器、两个 hash seed 下验证的。
- floor 的网格是 11 个分位点，不是全部断点；要精确值请用 `--floor-values`。
- 库里向量数少于 20 时，z 不起作用，只有 floor 类规则能准入，与插件一致。
- 默认 `--keep 1`，与插件默认的 `embedding_prefetch_facts` 一致。Hermes 生产 wrapper 用的是 `semantic_max_extra 3`，
  比较时请用 `--keep 3`。

## 11. 交给 Hermes 的后续步骤

1. 起 KG-1 用过的那个 OpenAI 兼容 `/v1/embeddings` shim（生产侧车只提供 `/embed`，工具不改它）。
2. 拷贝一份真实库，在**仓库外**跑：`EMBED_URL=... EMBED_MODEL=bge-m3 python calib_run.py --store <副本> --out <仓库外目录>`。
3. 看 `report.md`，选一个候选点；然后换 `--seed`，用 `--floor-values X`（或 `--margins X`）跑单点确认 run。
4. `python calib_opaque.py <run> <export>`，再 `python calib_gate.py <export>`，确认 summary 不变后才外发。
5. 在合成集上用同一模型分别跑 auto 和 `--queries ../eval/queries.json`，量化 auto 探针的偏差。
6. 再挑一两个本地模型重复以上步骤，填第 12 节的表。

## 12. 参考阈值表（模板，目前没有数据）

| 模型 | 库 | 探针 | keep | 规则 | 值 | recall@5 | 噪声净增 | 混淆净增 | p | 确认 run | 来源 run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | |

只填确认 run 的数字。每行都要能用 opaque 导出 + `calib_gate.py` 复算。
