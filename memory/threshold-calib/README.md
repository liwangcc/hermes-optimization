# threshold-calib：为你的嵌入模型和你的库标定语义准入阈值

语义准入的阈值不能跨模型直接沿用（upstream #95）。这个工具在**你自己的库、你自己的模型**上扫描准入参数，
给出「阈值 → (recall@5, 噪声, 混淆, McNemar)」工作点曲线。每个点都按 upstream PR #17 的四条件门禁，对上游默认
（`RECALL_MARGIN` 1.0，不设 floor）判一次。默认值不变，工具也不会替你挑点。设计和取舍见 [DESIGN.md](DESIGN.md)。

**本目录里没有任何结果。** `dryrun/` 来自离线 stub 嵌入器，只证明管线接通了。

## 规则

| rule | 扫描的是 | 状态 |
|---|---|---|
| `zbar` | margin：`z ≥ sqrt(2 ln N) + value` | 上游准入；1.0 是默认 |
| `zbar_floor` | `embedding_min_score`：cos ≥ value，并且满足默认 z_bar | 上游可选配置键，默认不设 |
| `floor` | cos ≥ value 单独准入 | **实验**，不是上游默认，也不提议当默认 |

三条规则都运行插件自己的 `Meaning.standout`（`floor` 用它的一个子类），遍历方式照抄 `Retriever.by_meaning`。

## 准备

- Python 3.11+、`numpy`；测试另需 `pytest`。不需要 torch，测试不联网。
- 插件快照放在 `vendor/holographic-0.27.0/`（upstream commit `114cf5f`，本仓库不跟踪它）：
  `git clone https://github.com/itpartypattaya/hermes-plugin-holographic vendor/holographic-0.27.0 && git -C vendor/holographic-0.27.0 checkout 114cf5f`，
  也可以用 `--plugin-src` 指到别处。工具只读它：插件的 `__init__` 不会执行，也不会往里写 `__pycache__`。
- 真实 run 需要一个 **OpenAI 兼容**的 `/v1/embeddings` 端点（本地服务或云 API），因为用的是插件自己的客户端。
  本仓库的生产侧车只提供 `/embed`，请用和 KG-1 相同的兼容 shim。

## 运行

```bash
cd memory/threshold-calib

# 1. 离线管线检查：逐字节复现 dryrun/
python calib_run.py --stub --facts ../eval/facts.json --out dryrun/auto
python calib_run.py --stub --facts ../eval/facts.json --queries ../eval/queries.json --out dryrun/labelled

# 2. 测试
python -m pytest -q

# 3. 真实 run：一份库的副本，输出写在仓库外（输出里有原文）
export EMBED_URL=...        # /v1 基地址；明文 http 只允许 localhost 或内网地址
export EMBED_MODEL=...      # 例如 bge-m3、text-embedding-3-small
export EMBED_KEY_ENV=...    # 可选：存放密钥的环境变量**名字**（默认用插件自己的）
python calib_run.py --store /path/to/copy-of-store.db --out /outside/the/repo/run
#   发送前一定先打印预估：estimate: N texts, ~T tokens, ~ $X (...)
#   远程端点要加 --yes 才会真正发送；不在价目表里的模型用 --price-per-mtok 指定单价

# 4. 确认 run：挑出的单个值，换一批探针再判一次
python calib_run.py --store ... --rules floor --floor-values 0.55 --seed 7 --out /outside/the/repo/confirm

# 5. 唯一允许离开本机的形式，以及在导出目录上复算门禁
python calib_opaque.py /outside/the/repo/run export/run
python calib_gate.py export/run
```

常用参数：`--queries FILE`（用标注好的查询，不再自动生成探针）、`--auto 40`（自动探针个数，其中 1/4 是 holdout）、
`--keep 1`（每个探针最多准入几个事实，即插件的 `embedding_prefetch_facts`）、`--rules`、`--margins`、
`--floor-values`、`--embed-dimensions`（如果你的插件配置里设了 `embedding_dimensions`）。

## 分数导出与离线回放（实验）

`calib_run.py` 只测语义通道。要在完整链路上比较多条准入规则，先导出分数，再离线回放：

```bash
# 1. 导出：每个探针对每条事实的余弦，四种向量文本各一份（只有 id 和数字，没有文本）
BGE_MODEL=/path/to/bge-m3 python calib_dump.py --facts F.json --keywords K.json --queries Q.json --out D.json
#   真实库：--store 库的副本（输出必须在仓库外）；端点方式和 calib_run.py 一样用 EMBED_URL / EMBED_MODEL

# 2. 回放：在词法已展示的内容之上，每条规则最多追加 1 条；每格对 content/zbar（上游默认）判四条件
python calib_replay.py --dump D.json --lexical rows_ZC.jsonl \
    --check content/zbar=rows_ZC.jsonl content/floor=rows_FC.jsonl --out summary.json
```

- 向量文本：`content`、`content+keywords`（上游 `vector_text` 的拼法）、`keywords`（全部关键词一个向量）、
  `keyword-max`（每个关键词一个向量，事实取最高分）。没有关键词的事实在四种里都用原句。
- `--lexical` 是 KG-1 某一格的行（`qid, keys, by_meaning, targets`），`keys` 去掉 `by_meaning` 就是词法展示的内容。
- `--check` 用已测过的格子核对回放：`names_fit` 和重复窗口没有回放，复现率低说明它们在这个库上起作用。
- 规则和参数写死在 `calib_replay.ARMS`，回放不挑点。输出只有计数，真实库的 summary 可以带出本机，dump 不可以。

## 探针

- **labelled**：`../eval/queries.json` 的格式（`id, category, query, expected`；`category: negative` 视为 chit），
  或 KG-1 的统一格式（`qid, kind, category, lang, q, targets`）。
- **auto**（一键，不调 LLM，无需标注）：按 seed 抽事实，取正文中间一半作为探针。
  `fragment`：源事实留在库里，它就是目标；`holdout`：问的时候把源事实拿掉，库里没有答案，任何准入都算噪声；
  再加 10 条内置闲聊 `chit`。fragment 和目标字面重叠，**recall 偏乐观**；噪声和混淆那一侧是可信的。
- 事实要先过插件的 `screen._sendable` 才会被嵌入，探针要先过 `_secret_in` 和 `worth_asking`，与插件的实际
  发送集合一致。

## 输出（一个 run 目录）

| 文件 | 内容 |
|---|---|
| `manifest.json` | run 的 stamp：模型、端点类别（从不记地址，连哈希也不记）、探针来源、seed、keep、事实计数（不可发送 / trust 不够 / role prompt）、各规则的取值网格、预估 token 和费用 |
| `probes.jsonl` | 每个探针一行：`qid, kind, category, lang, q, targets, holdout, meaning_call`（`q` 是文本，opaque 导出时会剥掉） |
| `rows.jsonl` | 每个 rule × value × 探针一行：`rule, value, qid, keys`（语义准入的 fact id，按距离从近到远） |
| `summary.json` | 每个点的 recall@5、噪声、混淆（基线值、该点值、增加的、去掉的、净增）、extra（多准入的非目标，只展示）、b / c / p、丢失和新增的目标、#17 四条件、按类别的 recall |
| `report.md` | 上面内容的可读表格，附 summary.json 的 sha256、免责说明和指标定义 |

混淆的定义：有标注的探针，语义准入的第一个事实不是目标。`--keep` 大于 1 时，排在正确事实之后的多余事实只计入
`extra`，不进门禁。

`calib_opaque.py` 导出时会剥掉 `q` 和所有文本字段，qid 改成 `q0001…`，不在内置词表里的 category 改成 `cat1…`。
只要还有任何可能是文本的字符串，整个导出就被拒绝。

读报告时请注意：每个点的门禁都是**探索性**的（同一批探针上扫了很多个点）。一个值要成为参考阈值，必须经过单点
确认 run；而且只测了语义通道，完整链路要在选定的点上另外复核。
