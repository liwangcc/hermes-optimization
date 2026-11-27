# 日常版使用手册

装好之后（[INSTALL.md](../INSTALL.md)），把下面四件事做一遍。前三件决定召回好不好，第四件告诉你有没有做对。

## 清单

- [ ] 1. [每条事实都有关键词](#1-每条事实都有关键词)：`fact_store stats` 里的 `without_keywords` 是 0。
- [ ] 2. [把 MEMORY.md 的内容搬进事实库，再关掉 MEMORY.md](#2-事实目录和-memorymd)。
- [ ] 3. [语义通道确实在起作用](#3-保证语义通道生效)：侧车在运行，索引数等于事实数。
- [ ] 4. [跑一遍自检](#4-验证方法和问题修复)：只走词法 29/36，带语义追加 33/36。

## 1. 每条事实都有关键词

**为什么：** 命中主要靠词法，语义每轮最多补一条。关键词是最大的杠杆：真实库上只换关键词、不开侧车，前五命中从 24/39 到 32/39。没有关键词的事实只能靠原文里的词被找到，换个说法就问不到。

**怎么查。** 对 agent 说：

```text
用 fact_store 的 stats 看一下 without_keywords 是多少。
```

**怎么补。** 让你日常用的主模型来补，对 agent 说：

```text
用 fact_store 的 enrich 列出没有关键词的事实（limit 设 100），按工具说明给每一条补关键词，
用 update {fact_id, keywords}。一批做完再列下一批，直到 stats 里 without_keywords 为 0。
```

**关键词该怎么写。** 工具说明里已经写了，模型照着写就行，不用另外规定格式：

- 别人问到这条事实时可能用、但原文里没有的词：同义词、换一个词根的说法、更宽泛的上位词。
- 用户使用的其他语言里的对应说法也要有。中英文混着用，就两种都写。
- 每条 3 到 8 个，最多 12 个，每个不超过 40 个字符。

**不要做的：**

- 不要只留专有名词。真实库上这样写比原始关键词还差（23/39）。
- 不要自己另定一套「更干净」的写法。试过「双语、不带口语和问法词、每条不超过 8 个」，合成库上只走词法的命中从 29 题掉到 21 题。数字见 [LEXICAL-LEVERS-RESULTS.md](../memory/threshold-calib/LEXICAL-LEVERS-RESULTS.md)。

**以后要留意的：**

- 新事实写入时，模型会按工具说明带上关键词。
- 用 `change` 改一条事实的内容时，旧关键词会被清掉，要重新给。隔一段时间再看一次 `stats`。
- 批量导入的事实通常没有关键词，导入后要补一遍。

## 2. 事实目录（可选）和 MEMORY.md

**日常版默认：** MEMORY.md 关、USER.md 开、事实目录关。补查靠每轮最多 4 条动态指针 + `fact_store get`，不需要常驻一份全量目录。第二轮赛马在测试大库上，受预算截断的静态目录覆盖 30/38 个未展示答案，每轮 ≤4 条动态指针覆盖 37/38，每轮目录 token 1546→28。

**事实目录是什么：** 打开 `catalog_enabled` 后，系统提示里多一份由事实库自动生成的目录（每条事实一个编号和标签）。agent 想到相关的词时，可以用 `fact_store get` 按编号取，不必等自动召回命中。它是可选的：库小、或你就是想让模型每轮都看到全量清单时再开。

**为什么要关 MEMORY.md：**

- MEMORY.md 每轮注入；日常版已经有 USER.md + 事实库两处，留它只会让模型多一个写错的地方。
- 新记忆有两个去处时，模型会写错地方或者两边各写一份。关掉 MEMORY.md 后，Hermes 会把这个写入目标从工具里去掉，写不进去。
- 插件的写入规则按这个组合设计：MEMORY.md 关，USER.md 开；事实目录开不开都不影响写入路由。

**步骤，先搬再关：**

1. 把 MEMORY.md 的内容分两类搬走。插件不会替你搬，也不让 agent 自作主张地搬；你可以手工搬，也可以明确让 agent 做：

   ```text
   把 MEMORY.md 里的每一条过一遍：关于我本人、每次对话都用得上的，写进 USER.md；
   其余的用 fact_store add 存成事实并带上关键词；事实库里已经有同样内容的不要重复加。
   做完列出每一条去了哪里。先不要删 MEMORY.md 里的内容。
   ```

2. 核对 agent 列出的去向，然后关掉 MEMORY.md。文件本身不会被删，留作备份：

   ```bash
   hermes config set memory.memory_enabled false
   ```

3. USER.md 保持打开（`memory.user_profile_enabled` 默认就是开）。它只放「关于用户本人、每次对话都用得上」的内容，比如回复语言。
4. （可选）打开事实目录，从下一个会话起生效。日常版不需要，默认就是关：

   ```bash
   hermes config set plugins.hermes-memory-store.catalog_enabled true   # 需要全量索引时再开
   ```

**怎么确认（开了目录时）：** 开一个新会话，问 agent「系统提示里的 Fact catalog 列了多少条事实」。

**要知道的：**

- 目录有预算（`catalog_max_tokens`，默认 3000）。超出时信任度最低的事实不列出，目录最后一行会说漏了几条。
- 短事实在目录里显示全文，长事实用关键词当标签。没有关键词的长事实只能显示开头几个字，所以第 1 件事也影响目录。
- 不要在 USER.md 或 MEMORY.md 里手写事实编号。事实合并或遗忘后，编号会失效。
- 没有测过的：模型是否严格按写入规则走。关掉 MEMORY.md 后没有明显损失，这是作者自己使用的印象，不是对照测试。

## 3. 保证语义通道生效

语义通道出问题时不报错，召回会静默退回纯词法。下面三条要同时成立：

1. `semantic_enabled` 是 `true`。
2. 侧车在运行，连的是这份事实库，索引数等于事实数。
3. 侧车单次回答的耗时小于 `semantic_timeout_ms`（默认 400 毫秒）。

**按平台做：**

| 平台 | 做法 |
|---|---|
| Windows x64 | 设置 → 记忆与上下文 → 持久记忆 → 向量模型 → 本地 → BGE-M3 → 一键部署并连接。然后运行「为已有事实建立语义索引」。重启电脑后，插件会在新会话开始时把服务拉起来 |
| macOS、Linux | 侧车要手工启动，每次开机后都要重新启动。四个步骤见 [platforms.md](platforms.md#事前准备) |
| BGE-M3 以外的本地模型 | 不走侧车，按向量接口接入，不需要阈值。见 [platforms.md](platforms.md#bge-m3-以外的本地模型) |

**怎么查：**

- 设置页的索引任务会显示「已索引 N/M 条事实」、模型和设备。N 应该等于 M。
- 命令行：`hermes memory action` 列出任务，`hermes memory action semantic-index` 运行索引任务。
- 手工侧车：`curl -s http://127.0.0.1:8791/health`，`ok` 为 `true`，`facts_indexed` 等于 `facts`。`facts` 是 `null` 说明侧车没找到事实库文件，这时 `ok` 仍然是 `true`。
- 日志里出现 `holographic-semantic: sidecar unavailable, lexical-only recall`，说明侧车没连上或超时。这一行在恢复之前只报一次。

**这些情况不补事实是正常的，不是故障：**

- 问候和很短的消息不问侧车。
- 这一轮已经展示了 7 条事实。
- 最接近的那条事实的相似度低于阈值，或者最近几轮已经展示过。

## 4. 验证方法和问题修复

**自检。** 在 Hermes 的 Python 里运行。它用 30 条公开的合成事实和 48 道题，在临时目录里走一遍已安装的插件，不读你的事实库和配置。命令和每个字段的读法见 [platforms.md](platforms.md#自检)。

```bash
python /path/to/hermes-optimization/memory/threshold-calib/check_daily_install.py \
  --core-src <Hermes 检出> --base-src <Holographic 检出> \
  --sidecar-python <装了 torch 的 Python> --model-dir <BGE-M3 目录>
```

去掉后两个参数只查词法这一半，不需要侧车和模型。

要把结果报给别人，或者核验别人报来的结果，按[测试标准](test-standard.md)做。自己出题或只报一个百分比的结果没法核验。

**前五命中对照**（合成库 36 道有答案的题）：

| 前五命中 | 是什么情形 |
|---:|---|
| 33/36 | 日常版正常工作 |
| 32/36 | 语义追加起作用了，但没装词干包 |
| 29/36 | 只走了词法：侧车没开、没连上，或者开关没打开 |
| 26/36 | 只走了词法，而且没装词干包 |

不在表里的数（比如 30、31）：语义追加只在一部分题上起了作用，先看自检输出里的 `gave_up`。

只对前五命中。首位命中会随环境里有没有 numpy 差一题，不作为对照数。

**问题和修法：**

| 现象 | 最可能的原因 | 怎么修 |
|---|---|---|
| 自检的 `words_only` 是 26 | 跑 Hermes 的 Python 里没有 `snowballstemmer` | `python -m pip install snowballstemmer==3.1.1`，或者改用 Hermes 自己的 Python |
| 自检的 `closest_fact` 和 `words_only` 相同 | 侧车没有起作用 | 按第 3 节逐条查 |
| 侧车 `/health` 里 `facts` 是 `null`，或 `/sync` 报 `unable to open database file` | 侧车没找到事实库文件：启动它的终端里没设 `HERMES_HOME`，或者全新安装还没建库 | 见 [platforms.md](platforms.md#3-启动侧车) |
| 自检的 `gave_up` 大于 0 | 侧车回答比预算慢 | `hermes config set plugins.hermes-memory-store.semantic_timeout_ms 1500` |
| 自检正常，自己的库上还是问不到 | 事实没有关键词，或关键词不是别人会用的说法 | 第 1 节 |
| 同一个会话里连着问，后面的问题不中 | 最近展示过的事实不会重复展示 | 测试时每道题开一个新会话 |
| 换了向量模型后几乎不补，或者乱补 | 阈值和模型不匹配 | 用三个内置模型之一，或者按向量接口接入 |
| 目录里找不到某条事实 | 信任度低于门槛、超出目录预算，或内容像凭据或指令 | 调大 `catalog_max_tokens`；后两种是有意不列 |
| agent 还在往 MEMORY.md 写 | MEMORY.md 还开着 | 第 2 节的第 2 步 |

**自检管的范围：** 它确认安装和环境是对的，不能说明你自己的库上命中率是多少。自己的库上最该看的是第 1 节的 `without_keywords`。

**回滚：** 一条命令回到未改动的上游插件，事实库不动。

```bash
hermes config set memory.provider holographic
```
