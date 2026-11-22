# hermes-optimization

> 我如何优化我的 [Hermes Agent](https://github.com/NousResearch/hermes-agent)：本地语义记忆、配置范式，以及一套可复现的评测。
>
> *How I optimize my Hermes Agent: local semantic memory, config patterns — with a reproducible eval.*

这是一个 **power-user 设置指南 + 可运行组件**，不是 Hermes 本体。我把日常调优里真正有价值、且能通用化的部分抽出来分享：方法、代码、评测都能照着跑，但**不含任何个人配置、密钥或私有数据**——所有示例值都是占位符。

## 完整安装（日常版 2026-11）

想直接装上和我日常一致的版本，从 **[INSTALL.md](INSTALL.md)** 开始。它给出固定基线、补丁应用顺序、Desktop 构建、插件安装、模型部署、验证和回滚步骤。

| 组件 | 固定版本 | 本仓库位置 |
|---|---|---|
| Hermes Agent | `40d1e95f` → `eccd37ae`（`v0.23.2+canary` + 6 commits） | [`patches/`](patches/README.md) |
| Holographic | 0.30.0（`ed73195f` → `4cbd5b7`） | [`patches/`](patches/README.md) |
| `holographic-semantic` | 0.6.0（16 个源文件，含依赖锁和模型清单） | [`memory/plugin/holographic-semantic/`](memory/plugin/holographic-semantic/) |

**模型权重不随仓库分发**：bge-m3 约 2.14 GiB，BGE-small-zh 约 92 MiB，MiniLM 约 463 MiB，由安装程序按固定
提交下载并逐文件校验 SHA-256。详见 [INSTALL.md §6](INSTALL.md#6-本地向量模型权重不在仓库里)。

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

### 精度：收回「精度没丢」的说法

早先版本写过「精度没丢（负例误报 0）」，这个说法**收回**。合成评测里 `cos ≥ 0.55` + keywords 在 36 条正例上召回 75 条事实，**只有 26 条是目标**（精度约 0.35）——语义通道会带回不少非目标事实。负例只有闲聊类、**没有同领域的难负例**，所以「负例误报 0」推不出真实场景精度无损。可复现的合成对照见 [`memory/eval/`](memory/eval/README.md)。

> 使用体感（**主观感受，不是测量结果**）：开了侧车之后联想更多。

## 目录

| 路径 | 内容 |
|---|---|
| [`INSTALL.md`](INSTALL.md) | **完整安装**：固定基线、补丁顺序、Desktop 构建、模型部署、验证与回滚 |
| [`patches/`](patches/README.md) | Hermes 与 Holographic 的日常版补丁、校验和、应用顺序 |
| [`docs/release-manifest.md`](docs/release-manifest.md) | 本次发布的文件清单、排除项与提交前扫描结果 |
| [`memory/`](memory/README.md) | **旗舰**：语义记忆增强（受管侧车 / 手工侧车 + wrapper + 评测） |
| [`memory/sidecar/`](memory/sidecar/README.md) | 手工 bge-m3 HTTP 服务（GPU fp16、离线、缓存、fail-safe） |
| [`memory/plugin/`](memory/plugin/README.md) | `holographic-semantic` 0.6.0：云端/本地向量、连接向导、目录、阈值初始化、索引任务 |
| [`memory/eval/`](memory/eval/README.md) | 自包含合成中文评测，可复现（`results.json` 为实测输出） |
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
- **生成目录供主动查询**：可选事实目录由库自动生成 `#id=label` 放进系统提示，给模型一张「有什么」的地图，想到相关词时能主动 `fact_store get`，不必等自动召回命中；它是生成的读索引，不是手写指针（手写 `fact#N` 会随事实合并/遗忘悬空）。详见 [memory-architecture.md](docs/memory-architecture.md)。

详见 [`docs/methodology.md`](docs/methodology.md)。

## 许可与致谢

本仓库原创部分采用 [MIT](LICENSE)。借用的项目及其许可见 [NOTICE](NOTICE)：
holographic（MIT）、bge-m3（MIT）、Hermes Agent（MIT）。模型权重与上游插件**不在此 redistribute**，请自行获取。

[`patches/`](patches/README.md) 是 Hermes Agent 与 Holographic 固定基线的修改版补丁，分发时保留原版权与
MIT 许可声明；补丁的起点、终点和校验和都写在补丁清单里。

---

*欢迎拍砖。这套东西的取舍是「召回优先，精度有代价」——语义通道会带回非目标事实；如果你的场景更怕噪声，上游默认的精度门可能更适合你。评测脚本就是用来帮你自己量的。*
