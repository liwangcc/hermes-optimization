# hermes-optimization

> 我如何优化我的 [Hermes Agent](https://github.com/NousResearch/hermes-agent)：本地语义记忆、配置范式，以及一套可复现的评测。
>
> *How I optimize my Hermes Agent: local semantic memory, config patterns — with a reproducible eval.*

这是一个 **power-user 设置指南 + 可运行组件**，不是 Hermes 本体。我把日常调优里真正有价值、且能通用化的部分抽出来分享：方法、代码、评测都能照着跑，但**不含任何个人配置、密钥或私有数据**——所有示例值都是占位符。

## 怎么选：日常版 / 纯净版

语义召回先选取舍，再决定装哪套：

| 版本 | 取舍 | 适合谁 | 在哪 |
|---|---|---|---|
| **日常版（主推）** | **召回优先 ＋ 复核精挑**。宽候选 → 本地 Qwen3-Reranker-0.6B 精挑全文 → 宽裕动态指针兜底，再加每条消息 `get` 预算闸（防吸库）。官方探针 test 池命中@5 **304→307**、展示精度 **27%→44%**、非答案 **−52%**，库越大差距越大。**代价**：有 CUDA 显卡时约 +1.3 GB 显存、每条消息 +0.2 s；没有 CUDA 时侧车自动改用精简读法（只读块内事实和最近的一条），纯 CPU 约 1～3 s、要调大等待时间，苹果芯片见 [platforms.md](docs/platforms.md#复核召回在没有-cuda-的机器上)。复核会丢少数基座原有答案（见局限） | 用强模型、更怕漏召回不怕噪声的开发者；有 CUDA 显卡最快 | 本仓库 [`memory/plugin/holographic-semantic/`](memory/plugin/holographic-semantic/)，安装见 [INSTALL.md](INSTALL.md)；赛马证据 [`memory/recall-race/`](memory/recall-race/README.md) |
| **上游纯净版** | 精度优先。holographic 默认统计离群门（zbar，margin 1.0），噪声极低；小库上按意思召回很少 | 怕噪声、要稳的多数用户 | [holographic 上游](https://github.com/itpartypattaya/hermes-plugin-holographic)，开箱即用 |

**主推日常版（召回优先）。** 这是我日常在用的那套，面向**有显卡、用强模型、更怕漏召回**的开发者。它不靠「放宽阈值多塞事实」，而是**先放宽找全候选，再用本地交叉编码器（Qwen3-Reranker-0.6B）精挑**：官方探针 test 池命中@5 304→307、展示精度 27%→44%、非答案减少 52%，噪声行 130→88、混淆行 34→24；把库并到 262–298 条后差距更大（命中@5 262→272、非答案 1239→595）。自动召回没命中的答案，绝大多数能从每轮最多 4 条动态指针里 `fact_store get` 补回（38 个漏答案里 37 个在指针中），每条消息还有 `get` 预算闸防止模型反复吸库。代价诚实写在下方「局限」：有 CUDA 显卡最快，且复核会丢少数基座原有答案——它**没有**通过上游完整四条门禁，走的是「召回优先」这条与上游默认不同的路。想直接用我日常这套，从 [INSTALL.md](INSTALL.md) 开始。

**有没有 CUDA 是同一个版本。** 插件和侧车是同一份，侧车按设备自动选读法：有 CUDA 时复核读块内事实和最近 10 条；没有时只读块内事实和最近的一条。在同一批题上两种读法的命中和降噪基本相同（命中@5 433 对 433，展示的非答案 564 对 549），数字和耗时见 [platforms.md](docs/platforms.md#复核召回在没有-cuda-的机器上)。

**原先单列的「纯净增强版」不再单列。** 它的做法是低余量候选经同一个小模型确认才放行，一个答案都不丢，但也不降噪。这个开关已合进上游（[PR #135](https://github.com/itpartypattaya/hermes-plugin-holographic/pull/135)，2026-11-26），在上游是探针用的测量开关，默认不启用。补丁和门禁证据仍在 [`memory/threshold-calib/upstream-check/`](memory/threshold-calib/upstream-check/README.md)，投稿记录在 [`docs/upstream-memory-review/`](docs/upstream-memory-review/SUBMISSION.md)。**更怕噪声、一个答案都不想丢，选上游纯净版。**

## 完整安装（日常版，主推）

这是召回优先 ＋ 复核精挑的个人日常版（取舍见上表）。想直接装上和我日常一致的版本，从 **[INSTALL.md](INSTALL.md)** 开始。它给出固定基线、补丁应用顺序、Desktop 构建、插件安装、模型部署、验证和回滚步骤。

| 组件 | 固定版本 | 本仓库位置 |
|---|---|---|
| Hermes Agent | `40d1e95f` → `eccd37ae`（`v0.23.2+canary` + 6 commits） | [`patches/`](patches/README.md) |
| Holographic | 0.30.0（`ed73195f` → `4cbd5b7`） | [`patches/`](patches/README.md) |
| `holographic-semantic` | 0.6.1（16 个源文件，含依赖锁和模型清单） | [`memory/plugin/holographic-semantic/`](memory/plugin/holographic-semantic/) |

**模型权重不随仓库分发**：bge-m3 约 2.14 GiB，BGE-small-zh 约 92 MiB，MiniLM 约 463 MiB，由安装程序按固定
提交下载并逐文件校验 SHA-256。详见 [INSTALL.md §6](INSTALL.md#6-本地向量模型权重不在仓库里)。

### 使用前清单（日常版）

装好只是第一步。下面四件事漏掉任何一件，召回都会变差，而且对话里看不出来。每一项的做法、检查命令和修法见 **[使用手册](docs/user-guide.md)**。

1. **每条事实都有关键词。** 让你的主模型用 `fact_store enrich` 补齐，直到 `fact_store stats` 里的 `without_keywords` 为 0。关键词是最大的杠杆，批量导入的事实通常没有。→ [做法](docs/user-guide.md#1-每条事实都有关键词)
2. **把 MEMORY.md 的内容搬进事实库，再关掉 MEMORY.md。** 先搬再关：关于你本人的进 USER.md，其余存成事实。→ [步骤](docs/user-guide.md#2-事实目录和-memorymd)
3. **确认语义通道在起作用。** Windows x64 用设置页一键部署并建索引；macOS 和 Linux 要手工启动侧车，并确认词干包在。→ [检查](docs/user-guide.md#3-保证语义通道生效)、[macOS / Linux 的准备](docs/platforms.md)
4. **跑一遍自检。** 合成库上只走词法是 29/36，带语义追加是 33/36；得到 26/36 说明没装词干包。→ [验证和问题修复](docs/user-guide.md#4-验证方法和问题修复)、[测试标准](docs/test-standard.md)

## 这是什么 / 不是什么

- ✅ **是**：一套建立在现有开源项目之上的**集成 + 调优 + 评测**层。旗舰是「本地 bge-m3 语义记忆增强」，配可复现评测。
- ✅ **是**：诚实的署名——借来的部分（holographic、bge-m3、Hermes）都在 [NOTICE](NOTICE) 里标清。
- ❌ **不是**：一个从零写的记忆系统。事实库、词法检索、trust/feedback 仍由 [holographic](https://github.com/itpartypattaya/hermes-plugin-holographic) 提供；嵌入模型是 BAAI 的 bge-m3。
- ❌ **不是**：我的真实环境快照。没有密钥、没有个人记忆、没有网络/账号细节。

## 亮点：主杠杆是写入时的关键词，语义侧车是兜底和联想

下面是早期多候选版本在真实个人事实库上的结果。39 条有效查询中，recall@5 是标准答案进前 5 的查询占比。

1. **写入时的中英双语 + 口语关键词是主杠杆。** 只用词法召回（FTS，无 GPU），把关键词从「原始」换成「双语口语」，recall@5 从 **24/39 → 32/39**。这一步不花显存。
2. **语义侧车是兜底和联想。** 在双语关键词之上再挂本地 bge-m3 侧车，到 **34/39**，代价约 **3G 显存**。侧车不可用 / 超时 → **自动退回纯词法**，绝不阻塞对话。
3. **只留专有名词反而更差。** 通用词 + 双语 + 口语才匹配大多数查询；专名只锚「问名字」那一类。

### 三套关键词 × 两种配置（真实库，39 条有效查询）

| 关键词集 | 纯词法 recall@5 | 词法 + 语义侧车 recall@5 |
|---|---|---|
| 原始 | 24/39（0.615） | 32/39（0.821） |
| **双语口语** | **32/39（0.821）** | **34/39（0.872）** |
| 只留专有名词 | 23/39（0.590） | 29/39（0.744） |

*三套的负例误报都是 0；但「非目标事实」是另一回事，见下方局限。*

### 规模实验：灌合成干扰到 3000 条

往库里加同领域合成干扰事实到 3000 条：**三套排序不变**（双语 > 原始 > 专名），**纯词法召回基本不动**，**语义通道的非目标事实随规模上升**。没有观察到「库一大、专名就反超」的交叉。

### 局限（务必读）

- 只有 **39 条有效查询**，1–2 条的差距在误差范围内，别把小差距当结论。
- 查询和关键词都由模型根据**同一批事实**生成，纯词法的数字**偏乐观**。
- 标注是**单一答案**：按意思找回来的相关事实一律被记成「非目标」，所以非目标数高估了真实噪声。
- 规模实验的干扰事实各带**独立的假专名**，是最容易的一种噪声；**同一实体的近似事实没有测**。

**日常版 R2（复核精挑）另有的代价**（数字见 [`memory/recall-race/ROUND2-RESULTS.md`](memory/recall-race/ROUND2-RESULTS.md)，与上面 39 条早期实验是不同题集，不互减）：

- **有 CUDA 显卡最快**：复核模型 Qwen3-Reranker-0.6B 约 +1.3 GB 显存、每条消息 +0.2 s（RTX 4060 笔记本）；没有 CUDA 时复核只读块内事实和最近的一条，纯 CPU 约 1～3 s/条（中位 1.1 s，要把 `semantic_timeout_ms` 调到 3000）；苹果芯片精简后还没有复测，见 [platforms.md](docs/platforms.md#复核召回在没有-cuda-的机器上)。
- **会丢少数基座原有答案**：test 池救回 4 题、丢 1 题；全题集救回 10、丢 2（p=0.039），丢了 4 个 D0 原有答案（其中 3 个是「孩子们/父母」这类一问多人的第二个答案）。**没有通过上游完整四条门禁**（零丢失门没过）。只加不删的变体不丢答案（p=0.002），但噪声行与混淆行各多 1 行。
- 规则在 dev 池定好后冻结、test 池只判一次；**真实个人库、多轮对话、第二模型尚未验证**。

### 精度：收回「精度没丢」的说法

早先版本写过「精度没丢（负例误报 0）」，这个说法**收回**。合成评测里 `cos ≥ 0.55` + keywords 在 36 条正例上召回 75 条事实，**只有 26 条是目标**（精度约 0.35）——语义通道会带回不少非目标事实。负例只有闲聊类、**没有同领域的难负例**，所以「负例误报 0」推不出真实场景精度无损。可复现的合成对照见 [`memory/eval/`](memory/eval/README.md)。

> 使用体感（**主观感受，不是测量结果**）：开了侧车之后联想更多。

## 目录

| 路径 | 内容 |
|---|---|
| [`INSTALL.md`](INSTALL.md) | **完整安装**：固定基线、补丁顺序、Desktop 构建、模型部署、验证与回滚 |
| [`docs/user-guide.md`](docs/user-guide.md) | **使用手册**：使用前清单的四件事，每件怎么做、怎么查、出问题怎么修 |
| [`docs/platforms.md`](docs/platforms.md) | macOS 和 Linux 的事前准备、自检命令、各环境的验证状态 |
| [`docs/test-standard.md`](docs/test-standard.md) | **测试标准**：固定的题和命令、要交的报告文件、参考结果、一条核验命令 |
| [`patches/`](patches/README.md) | Hermes 与 Holographic 的日常版补丁、校验和、应用顺序 |
| [`docs/release-manifest.md`](docs/release-manifest.md) | 本次发布的文件清单、排除项与提交前扫描结果 |
| [`memory/`](memory/README.md) | **旗舰**：语义记忆增强（受管侧车 / 手工侧车 + wrapper + 评测） |
| [`memory/sidecar/`](memory/sidecar/README.md) | 手工 bge-m3 HTTP 服务（GPU fp16、离线、缓存、fail-safe） |
| [`memory/plugin/`](memory/plugin/README.md) | `holographic-semantic` 0.6.1 支持云端和本地向量、连接向导、事实目录、按模型推荐本地阈值和索引任务 |
| [`memory/eval/`](memory/eval/README.md) | 自包含合成中文评测，可复现（`results.json` 为实测输出） |
| [`memory/recall-race/`](memory/recall-race/README.md) | 召回赛马：宽候选→交叉编码器精挑（R2）的合成 pack、协议、结果表与干净 harness（原始脚手架不公开） |
| [`memory/threshold-calib/`](memory/threshold-calib/README.md) | 准入阈值校准工具 + 干跑证据（不透明行，可复算） |
| [`config-patterns/`](config-patterns/README.md) | 配置范式（占位示例，无真值） |
| [`docs/memory-architecture.md`](docs/memory-architecture.md) | 记忆架构：两层分工、生成目录、满了怎么办、清理规程 |
| [`docs/methodology.md`](docs/methodology.md) | 方法论与踩坑：先评测、wrap 不 fork、fail-open、抗更新 |
| [`docs/tiered-compression.md`](docs/tiered-compression.md) | 分层密度压缩提案（未实现） |
| [`issue95-evidence/`](issue95-evidence/METRICS.md) | 关键词进向量门禁证据：公开合成集 + 真实库不透明行（零文本） |
| [`docs/upstream-memory-review/`](docs/upstream-memory-review/SUBMISSION.md) | 上游投稿：记忆容量 / provider 维护任务 / 桌面设置的补丁与验证 |

## 快速开始

完整安装走 [INSTALL.md](INSTALL.md)。最短路径：

```bash
# 1. Hermes 固定基线 + 补丁
git clone https://github.com/NousResearch/hermes-agent.git
cd hermes-agent && git checkout 40d1e95f37e409f9f618f32c170661c66b86a4f4
git apply /path/to/hermes-optimization/patches/hermes-agent-40d1e95f-eccd37ae.patch
git apply /path/to/hermes-optimization/patches/hermes-agent-ledger-fix.patch

# 2. Holographic 0.30.0 + 设置补丁，放进插件目录
#    （见 INSTALL.md §4；补丁文件 patches/holographic-ed73195f-4cbd5b79.patch）

# 3. wrapper + 启用
cp -R memory/plugin/holographic-semantic "$HERMES_HOME/plugins/"
hermes plugins enable holographic-semantic
hermes config set memory.provider holographic-semantic
hermes config set plugins.hermes-memory-store.semantic_enabled true

# 4. Desktop 设置 → 记忆 → 向量模型 → 本地 → 选择模型 → 一键部署
#    权重由安装程序下载，仓库不含模型

# 回滚（一条命令回到未改动的上游 provider）
hermes config set memory.provider holographic
```

不用 Desktop、想手工起侧车：见 [`memory/sidecar/README.md`](memory/sidecar/README.md)。
只想看评测、不装插件：`cd memory/eval && BGE_MODEL=/path/to/bge-m3 python run_eval.py`。

## 设计原则

- **先评测再调参**：每个参数都有评测依据，负例和正例一样重要。
- **wrap 不 fork**：增强层在加载时继承上游 provider，上游更新自动继承，回滚是改配置不是改代码。
- **fail-open**：侧车挂了/超时 → 退回词法召回，绝不阻塞对话。
- **三不动**：常驻 USER/MEMORY 层不向量化、专有名词硬锚点保留、trust/feedback 与矛盾检测保留。
- **动态指针按需读，不常驻全量目录**：日常版每轮最多列 4 条 `#id=label` 指针，模型用 `fact_store get` 读全文；第二轮赛马在测试大库上，受预算截断的静态目录覆盖 30/38 个未展示答案，动态指针覆盖 37/38，每轮 token 1546→28。可选事实目录（`catalog_enabled`）仍保留，给需要全量索引的场景。详见 [memory-architecture.md](docs/memory-architecture.md)。

详见 [`docs/methodology.md`](docs/methodology.md)。

## 许可与致谢

本仓库原创部分采用 [MIT](LICENSE)。借用的项目及其许可见 [NOTICE](NOTICE)：
holographic（MIT）、bge-m3（MIT）、Hermes Agent（MIT）。模型权重与上游插件**不在此 redistribute**，请自行获取。

[`patches/`](patches/README.md) 是 Hermes Agent 与 Holographic 固定基线的修改版补丁，分发时保留原版权与
MIT 许可声明；补丁的起点、终点和校验和都写在补丁清单里。

---

*欢迎拍砖。这套东西的取舍是「召回优先，精度有代价」——语义通道会带回非目标事实；如果你的场景更怕噪声，上游默认的精度门可能更适合你。评测脚本就是用来帮你自己量的。*
