# 完整安装说明（日常版 2026-11）

这套东西把 **Hermes Agent 日常版补丁 + Holographic 0.30.0 设置补丁 + `holographic-semantic` 0.6.1**
装到一台机器上。目标是可复现：固定基线、固定补丁、固定验证命令；升级或回滚都不靠记忆。

**不包含**：模型权重、事实库、个人 `config.yaml`、凭据、日志、缓存、Python/Node 运行环境。
模型权重由安装程序按固定提交下载并校验，见 [§6](#6-本地向量模型权重不在仓库里)。

> **macOS 和 Linux**：§6 的「一键部署并连接」只能在 Windows x64 上从零部署，侧车要手工启动；词干包
> `snowballstemmer` 也要确认在。漏掉任何一件，召回会静默变差。准备步骤和一条自检命令见
> [`docs/platforms.md`](docs/platforms.md)。

---

## 0. 固定基线

| 组件 | 上游 | 固定提交 | 版本 |
|---|---|---|---|
| Hermes Agent | https://github.com/NousResearch/hermes-agent | `40d1e95f37e409f9f618f32c170661c66b86a4f4` | `v0.23.2+canary.20261117T064624Z` |
| Holographic | https://github.com/itpartypattaya/hermes-plugin-holographic | `ed73195df846913d34f4aea54335718e56d841fb` | `0.30.0` |
| `holographic-semantic` | 本仓库 `memory/plugin/holographic-semantic/` | 随本仓库发布 | `0.6.1` |

补丁、校验和与应用顺序见 [`patches/README.md`](patches/README.md)。本次发布带了什么、排除了什么，
见 [`docs/release-manifest.md`](docs/release-manifest.md)。

> 这些版本是配套的，不要只升其中一个。Hermes 的 Desktop 面板、`plugins.memory.config_schema`
> 与 wrapper 的 `config_schema.py` 是一组契约；Holographic 的设置 schema 与 wrapper 的字段也是一组。

---

## 1. 准备 Hermes 源码检出

```bash
git clone https://github.com/NousResearch/hermes-agent.git
cd hermes-agent
git checkout 40d1e95f37e409f9f618f32c170661c66b86a4f4
```

确认起点：

```bash
git rev-parse HEAD
# 40d1e95f37e409f9f618f32c170661c66b86a4f4
```

## 2. 应用 Hermes 补丁

把本仓库的 `patches/` 放在可访问的位置（下面用 `$PATCHES` 表示）：

```bash
PATCHES=/path/to/hermes-optimization/patches

git apply --check "$PATCHES/hermes-agent-40d1e95f-eccd37ae.patch"
git apply         "$PATCHES/hermes-agent-40d1e95f-eccd37ae.patch"

git apply --check "$PATCHES/hermes-agent-ledger-fix.patch"
git apply         "$PATCHES/hermes-agent-ledger-fix.patch"
```

第二个补丁只重新生成 `tests/hermes_cli/serve_handler_ledger.json`：日常版新增了两个
memory handler，却没有同步账本，干净检出上 `test_serve_handler_ledger.py` 会失败。它不改业务代码。

补丁覆盖：核心 `agent/`、`hermes_cli/`、`tools/`，Desktop（`apps/desktop/`），多语言本地化
（英、简中、繁中、日、德、法、西、俄、阿），测试与 `website/docs/`。

## 3. 准备 Python 运行环境并构建 Desktop

Hermes 源码检出用自己的 PM 工具链：

```bash
export HERMES_HOME="$HOME/hermes-dev-data"   # 换成你的日常 home；不要指向正在运行的安装
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
source ./activate
```

Windows PowerShell：

```powershell
$env:HERMES_HOME = Join-Path $HOME 'hermes-dev-data'
$env:HERMES_RUNTIME_DIR = Join-Path $env:HERMES_HOME 'tools'
. .\activate.ps1
```

`activate` 会同步 Python 依赖。补丁改了 Desktop 的 TypeScript，首次构建：

```bash
pnpm install
cd apps/desktop && pnpm run build && cd ../..
```

之后用 `hermes desktop` 启动；它会基于这个源码检出构建并运行 GUI。只用 CLI 可以跳过 Desktop 构建，
但本地模型部署、连接向导和阈值初始化都在 Desktop 面板里，CLI-only 场景请走 [§6 的手工侧车](#手工侧车cli-或不用-desktop)。

## 4. 安装 Holographic 0.30.0 并打补丁

在固定提交上克隆，应用设置补丁，再放进 Hermes 的插件目录：

```bash
git clone https://github.com/itpartypattaya/hermes-plugin-holographic.git "$HOME/holographic-src"
git -C "$HOME/holographic-src" checkout ed73195df846913d34f4aea54335718e56d841fb
git -C "$HOME/holographic-src" apply --check "$PATCHES/holographic-ed73195f-4cbd5b79.patch"
git -C "$HOME/holographic-src" apply         "$PATCHES/holographic-ed73195f-4cbd5b79.patch"

rm -rf "$HERMES_HOME/plugins/holographic"
cp -R "$HOME/holographic-src" "$HERMES_HOME/plugins/holographic"
hermes plugins enable holographic
```

补丁给 Holographic 增加了 Desktop 设置面板用的 `config_schema.py` / `config_fields.py`、
向量连接字段和简体中文本地化；不改变事实库 schema，也不迁移数据。

## 5. 安装 `holographic-semantic` 包装插件

```bash
cp -R /path/to/hermes-optimization/memory/plugin/holographic-semantic \
      "$HERMES_HOME/plugins/holographic-semantic"

hermes plugins enable holographic-semantic

hermes config set memory.provider holographic-semantic
hermes config set plugins.hermes-memory-store.semantic_enabled true
# 日常版默认不开静态目录：每轮动态指针 + fact_store get 已覆盖补查；
# 需要全量 #id=label 索引时再改为 true。
hermes config set plugins.hermes-memory-store.catalog_enabled false
```

包装插件继承 Holographic 的 provider。本地向量只检查信任线以上余弦最高的一条事实，问候和短消息跳过侧车。
侧车失败就退回词法召回。回滚时把 `memory.provider` 设回 `holographic`。

日常版默认 `catalog_enabled: false`。第二轮赛马在测试用的大库上：受预算截断的静态目录覆盖 30/38 个未展示答案，每轮 ≤4 条动态指针覆盖 37/38，每轮目录 token 1546→28。所以日常版用动态指针 + `get`，目录只作可选的全量索引。

> `semantic_enabled` 只控制本地向量通道。用云端 embedding 时，改设
> `plugins.hermes-memory-store.embeddings true`（以及 `embedding_url` / `embedding_model`），
> 两条通道二选一。

## 6. 本地向量模型：权重不在仓库里

推荐路径（Desktop）：

1. 打开 **设置 → 记忆与上下文 → 持久记忆 → 向量模型**。
2. 选 **本地 → 选择模型 → 一键部署并连接**。
3. 安装程序按 `local_models.py` 固定的提交下载文件，逐个校验大小和 SHA-256，然后启动
   `127.0.0.1` 上的本机服务。

| 模型 | 语言 | 维度 | 权重 | 推荐阈值 |
|---|---|---|---|---:|
| BGE-M3（默认） | 多语言 | 1024 | 约 2.14 GiB | 0.55 |
| BGE-small-zh v1.5 | 中文 | 512 | 约 92 MiB | 0.64 |
| Multilingual MiniLM-L12 v2 | 多语言，每条事实前 128 token | 384 | 约 463 MiB | 0.58 |

首次部署或切换本地模型时会自动采用表中的推荐阈值。重新部署已记录的同一模型时保留用户保存的值。

固定提交：

- `BAAI/bge-m3` @ `5617a9f61b028005a4858fdac845db406aefb181`
- `BAAI/bge-small-zh-v1.5` @ `7999e1d3359715c523056ef9478215996d62a620`
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` @ `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`

权重落在 `$HERMES_HOME/services/memory-embeddings/model-<提交前 12 位>/`，索引在
`vectors/<模型>-<提交前 12 位>/`；换模型不会混用向量。首次本地部署还要建一个隔离运行环境，
预留约 1.4 GiB 磁盘。**仓库和 Release 都不含这些权重**，不要尝试把模型目录提交进来。

手工下载 bge-m3（只在需要离线部署或手工侧车时）：

```bash
huggingface-cli download BAAI/bge-m3 \
  --revision 5617a9f61b028005a4858fdac845db406aefb181 \
  --local-dir "$HERMES_HOME/services/memory-embeddings/model-5617a9f61b02"
```

### 手工侧车（CLI 或不用 Desktop）

`memory/sidecar/` 是原来的手工 bge-m3 服务，协议与受管服务相同：

```bash
cd memory/sidecar
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
huggingface-cli download BAAI/bge-m3 --local-dir models/bge-m3
SEMANTIC_DB="$HERMES_HOME/memory_store.db" python server.py
```

然后把 `plugins.hermes-memory-store.semantic_url` 指到 `http://127.0.0.1:8791`。
受管服务与手工侧车二选一；受管服务会优先复用已经存在的 BGE-M3 侧车。

## 7. 启用后要做的一次性任务

1. **为已有事实建立语义索引**：设置面板里的「为已有事实建立语义索引 → 运行」。
   状态会显示已索引 / 总事实数、模型和设备。
2. 可在设置面板通过 **相似度阈值 → 一键初始化阈值** 查看本地模型的推荐 `semantic_tau`。
   手工侧车的模型无法识别时会显示原因。云端仍用事实片段校准 `embedding_min_score`。
   面板上有建议值时，可点「确认写入」应用。
3. 检查：

```bash
hermes memory status
hermes plugins list | grep -i holo
```

## 8. 验证（干净克隆实测）

下面是 0.5.0 在固定基线的干净 worktree 上的实测结果。

环境：Windows 11，Python 3.12.13（测试 venv），Node/pnpm 12.15.0，2026-11-20。

| 检查 | 命令 | 结果 |
|---|---|---|
| Hermes 补丁可应用 | `git apply --check patches/hermes-agent-40d1e95f-eccd37ae.patch` | 通过 |
| Holographic 补丁可应用 | `git apply --check patches/holographic-ed73195f-4cbd5b79.patch` | 通过 |
| Hermes memory 相关 Python 测试 | `pytest tests/agent/test_memory_checkup.py tests/hermes_cli/test_memory_actions.py tests/hermes_cli/test_web_memory_checkup.py tests/hermes_cli/test_web_memory_layers.py tests/hermes_cli/test_web_memory_provider_storage.py` | 58 passed |
| handler 账本 | `pytest tests/hermes_cli/test_serve_handler_ledger.py`（应用 ledger fix 后） | 2 passed |
| 上述 6 个文件一起跑（最终补丁序列） | 同上的 5 个文件 + `test_serve_handler_ledger.py` | 60 passed |
| Desktop UI 测试 | `vitest run --project ui` 覆盖 9 个 memory 相关文件 | 9 files / 50 tests passed |
| Desktop Electron 测试 | `vitest run --project electron electron/connection-config.test.ts` | 1 file / 126 tests passed |
| 包装插件自检 | `python memory/plugin/test_catalog.py` | 10 项全部 ok |
| 手工侧车同步 | `python memory/sidecar/test_sync.py` | 4 项全部 ok |
| 阈值校准工具 | `cd memory/threshold-calib && pytest -q` | 20 passed, 55 skipped（缺 vendored 快照的用例按设计跳过） |
| 旧投稿 testkit 自检 | `cd docs/upstream-memory-review/testkit && python -m unittest -v test_run` | 6 tests OK |
| Holographic 设置补丁测试 | 见下方命令 | 5 passed |

0.6.1 的 `memory/plugin/test_catalog.py` 共 21 项通过，覆盖本地语义准入、旧配置加载、模型切换和阈值建议。
脚本使用标准库和 Hermes 的 `utils`，侧车使用测试替身。

Holographic 的 5 个用例需要把 Hermes 检出和插件测试环境放在一起。Windows + pytest 9 还要避开一个
测试收集器的坑：仓库根目录本身是包（有 `__init__.py`），直接 `pytest tests/...` 会把根 `__init__.py`
当测试模块导入。从 `tests/` 目录用一个空的本地配置运行即可：

```bash
cd /path/to/hermes-plugin-holographic/tests
printf '[pytest]\n' > pytest.ini
HERMES_AGENT_REPO=/path/to/hermes-agent pytest -q -c pytest.ini test_holographic_config_schema.py
# 5 passed
```

这是测试运行方式的问题，不是补丁或插件行为的问题；Linux CI 上直接 `pytest` 不受影响。

## 9. 回滚

按影响面从小到大：

```bash
# 1) 回到上游 Holographic，语义层立即失效；事实库不动
hermes config set memory.provider holographic
hermes config set plugins.hermes-memory-store.semantic_enabled false
```

```bash
# 2) 移除包装插件（可选）
hermes plugins disable holographic-semantic
rm -rf "$HERMES_HOME/plugins/holographic-semantic"
```

```bash
# 3) 还原 Holographic 设置补丁
git -C "$HERMES_HOME/plugins/holographic" apply -R "$PATCHES/holographic-ed73195f-4cbd5b79.patch"
```

```bash
# 4) 还原 Hermes：先退账本补丁，再退主补丁（顺序不能反）
cd /path/to/hermes-agent
git apply -R "$PATCHES/hermes-agent-ledger-fix.patch"
git apply -R "$PATCHES/hermes-agent-40d1e95f-eccd37ae.patch"
source ./activate
cd apps/desktop && pnpm run build && cd ../..
```

模型权重和运行环境不在补丁里。想彻底清掉本地向量资源：

```bash
rm -rf "$HERMES_HOME/services/memory-embeddings"
```

（这会删权重、索引和受管运行环境；下次部署会重新下载。手工侧车在 `memory/sidecar/` 下，按它的
启动方式停掉即可。）

## 10. 许可与署名

- **Hermes Agent**：MIT，Copyright (c) 2025 Nous Research。
- **Holographic**：MIT，Copyright (c) 2025 Nous Research；现由 itpartypattaya 维护。
- **本仓库原创部分**：MIT，见 [`LICENSE`](LICENSE)；完整致谢见 [`NOTICE`](NOTICE)。
- 补丁是上述 MIT 项目的修改版；再分发时保留原版权、许可与署名。
- 模型权重不随本仓库分发；BGE-M3 与 BGE-small-zh 由 BAAI 发布（MIT），MiniLM 由
  sentence-transformers 发布，使用前请核对各自模型卡。
