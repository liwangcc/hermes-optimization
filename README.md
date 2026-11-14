# hermes-optimization

> 我如何优化我的 [Hermes Agent](https://github.com/NousResearch/hermes-agent)：本地语义记忆、精简工作流 skill、配置范式，以及一套可复现的评测。
>
> *How I optimize my Hermes Agent: local semantic memory, lean workflow skills, config patterns — with a reproducible eval.*

这是一个 **power-user 设置指南 + 可运行组件**，不是 Hermes 本体。我把日常调优里真正有价值、且能通用化的部分抽出来分享：方法、代码、评测都能照着跑，但**不含任何个人配置、密钥或私有数据**——所有示例值都是占位符。

## 这是什么 / 不是什么

- ✅ **是**：一套建立在现有开源项目之上的**集成 + 调优 + 评测**层。旗舰是「本地 bge-m3 语义记忆增强」，配可复现评测。
- ✅ **是**：诚实的署名——借来的部分（holographic、bge-m3、Hermes）都在 [NOTICE](NOTICE) 里标清。
- ❌ **不是**：一个从零写的记忆系统。事实库、词法检索、trust/feedback 仍由 [holographic](https://github.com/itpartypattaya/hermes-plugin-holographic) 提供；嵌入模型是 BAAI 的 bge-m3。
- ❌ **不是**：我的真实环境快照。没有密钥、没有个人记忆、没有网络/账号细节。

## 亮点：语义召回怎么「准入」才是关键

同一个 bge-m3 模型，**事实如何被准入**决定了召回质量。上游默认用统计离群门（`z ≥ √(2·ln N) + 1.0`，精度优先），在小型中文库上对口语/改写/跨语言查询几乎不召回；改成**余弦阈值 + 把 keywords 一起嵌入**，召回大幅上升且**负例零误报**：

| 准入方式 | 事实文本 | recall@5 | 口语 | 跨语言 | 负例误报 |
|---|---|---|---|---|---|
| z-bar（上游默认） | 仅正文 | 0.083 | 0.00 | 0.125 | 0.0 |
| z-bar | 正文+keywords | 0.194 | 0.20 | 0.125 | 0.0 |
| cos ≥ 0.55 | 仅正文 | 0.556 | 0.50 | 0.375 | 0.0 |
| **cos ≥ 0.55** | **正文+keywords** | **0.722** | **0.90** | **0.50** | **0.0** |

*合成 30 事实中文库 / 42 查询，bge-m3 CUDA fp16。自己跑：[`memory/eval/`](memory/eval/README.md)。*

两个要点：**keywords 是有用信号**（不靠降低门槛提召回），且**精度没丢**（负例误报始终 0.0）。

## 目录

| 路径 | 内容 |
|---|---|
| [`memory/`](memory/README.md) | **旗舰**：语义记忆增强（侧车 + wrapper + 评测） |
| [`memory/sidecar/`](memory/sidecar/README.md) | 本地 bge-m3 HTTP 服务（GPU fp16、离线、缓存、fail-safe） |
| [`memory/plugin/`](memory/plugin/README.md) | `holographic-semantic` provider（零改动继承上游，一键回滚） |
| [`memory/eval/`](memory/eval/README.md) | 自包含合成中文评测，可复现 |
| [`skills/`](skills/README.md) | 精简工作流 skill（确认决策，而非复核事实） |
| [`config-patterns/`](config-patterns/README.md) | 配置范式（占位示例，无真值） |
| [`docs/memory-architecture.md`](docs/memory-architecture.md) | 记忆架构：两层分工、指针、满了怎么办、清理规程 |
| [`docs/methodology.md`](docs/methodology.md) | 方法论与踩坑：先评测、wrap 不 fork、fail-open、抗更新 |

## 快速开始（语义记忆）

```bash
# 1. 装基础 holographic 插件（见其仓库），下载 bge-m3 权重
huggingface-cli download BAAI/bge-m3 --local-dir memory/sidecar/models/bge-m3

# 2. 起侧车（指向你的 holographic 事实库）
cd memory/sidecar && pip install -r requirements.txt
SEMANTIC_DB=/path/to/memory_store.db python server.py

# 3. 装 wrapper 插件并启用
cp -r memory/plugin/holographic-semantic "$HERMES_HOME/plugins/"
hermes config set memory.provider holographic-semantic
hermes config set plugins.hermes-memory-store.semantic_enabled true

# 回滚（一条命令回到未改动的上游）
hermes config set memory.provider holographic
```

只想看评测、不装插件：`cd memory/eval && BGE_MODEL=/path/to/bge-m3 python run_eval.py`。

## 设计原则

- **先评测再调参**：每个参数都有评测依据，负例和正例一样重要。
- **wrap 不 fork**：增强层在加载时继承上游 provider，上游更新自动继承，回滚是改配置不是改代码。
- **fail-open**：侧车挂了/超时 → 退回词法召回，绝不阻塞对话。
- **三不动**：常驻 USER/MEMORY 层不向量化、专有名词硬锚点保留、trust/feedback 与矛盾检测保留。
- **精简 skill**：确认决策而非复核事实，仪式不是安全。

详见 [`docs/methodology.md`](docs/methodology.md)。

## 许可与致谢

本仓库原创部分采用 [MIT](LICENSE)。借用的项目及其许可见 [NOTICE](NOTICE)：
holographic（MIT）、bge-m3（MIT）、Hermes Agent。模型权重与上游插件**不在此 redistribute**，请自行获取。

---

*欢迎拍砖。这套东西的取舍是「召回优先但守住精度」，如果你的场景更怕噪声，上游默认的精度门可能更适合你——评测脚本就是用来帮你自己量的。*