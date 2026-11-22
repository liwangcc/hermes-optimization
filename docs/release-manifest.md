# 发布文件清单（日常版 2026-11）

发布分支：`release/daily-memory-2026-11`，基于 `liwangcc/hermes-optimization` 的
`main@637d357`。本页记录这次发布**带了什么、没带什么、怎么检查的**。

## 1. 本次改动（32 个文件）

### 安装与补丁

| 文件 | 作用 |
|---|---|
| `INSTALL.md` | 固定基线、补丁顺序、Desktop 构建、模型部署、验证、回滚 |
| `patches/README.md` | 补丁清单、校验和、许可与署名 |
| `patches/hermes-agent-40d1e95f-eccd37ae.patch` | Hermes 6 个提交的完整源码补丁（106 files, +7004/-157） |
| `patches/hermes-agent-ledger-fix.patch` | handler 账本重新生成（1 file, +3/-1） |
| `patches/holographic-ed73195f-4cbd5b79.patch` | Holographic 0.30.0 设置补丁（5 files, +262） |

Hermes 主补丁的覆盖面：核心 14 个文件（`agent/`、`hermes_cli/`、`tools/`、`plugins/memory/`）、
Desktop 81 个文件（含 `apps/desktop/src/i18n/` 的各语言文案）、`locales/` 1 个、测试 6 个、文档 4 个。

### `holographic-semantic` 0.6.1（16 个源文件）

`memory/plugin/holographic-semantic/`：

`__init__.py`、`cloud_setup.py`、`config_schema.py`、`local_artifacts.py`、`local_models.py`、
`local-runtime.in`、`local-runtime.txt`、`managed_local.py`、`managed_server.py`、`plugin.yaml`、
`README.md`、`settings.py`、`setup_common.py`、`sidecar_index.py`、`threshold_calib.py`、
`threshold_job.py`。

本地语义沿用方案二，只检查信任线以上余弦最高的候选，并采用基座的重复窗口、可召回性、人名和查询长度检查。
0.6.1 将本地「一键初始化阈值」改为按固定模型给推荐值。首次部署和切换模型时写入推荐值，重部署同一模型时保留当前值。
云端阈值任务仍用事实片段探针。

`local-runtime.in` / `local-runtime.txt` 记录 Windows 运行环境的依赖和校验值。
`local_models.py` 记录模型的固定提交、文件大小、SHA-256 和推荐阈值。权重在安装时下载。

### 文档与自检

| 文件 | 作用 |
|---|---|
| `README.md` | 默认入口指向 `INSTALL.md`，补上日常版基线与模型说明 |
| `memory/README.md` | 受管侧车 / 手工侧车的分工 |
| `memory/plugin/README.md` | 0.6.1 的安装、配置、本地推荐阈值、任务与回滚 |
| `memory/sidecar/README.md` | 标注为手工 / CLI 路径 |
| `memory/plugin/test_catalog.py` | 21 项包装插件自检，覆盖本地语义准入、旧配置加载、模型切换和阈值建议 |
| `config-patterns/README.md` | 云端 / 本地配置范式 |
| `docs/methodology.md` | 去掉已删除的 `skills/` 链接 |
| `NOTICE` | 补 Hermes MIT 许可与补丁归属 |
| `.gitignore` | 排除模型权重、运行环境、补丁残留 |
| `.gitattributes` | 补丁文件按字节检出（`*.patch -text`），避免 CRLF 改写上下文 |
| `docs/release-manifest.md` | 本文件：清单、排除项与扫描结果 |

## 2. 明确排除

下面这些**没有**进入发布分支：

- 模型权重（`*.safetensors`、`*.bin`、`*.pt`、`*.onnx`、`*.npz`、`*.npy`）与 HuggingFace 缓存；
- 事实库 / SQLite（`*.db`、`*.sqlite*`）；
- 个人 `config.yaml`、`.env`、API key、OAuth / 订阅凭据；
- 日志、`__pycache__`、`.pytest_cache`、测试临时目录；
- Python / Node 运行环境、`node_modules`、`services/`；
- 本机备份、`.orig` / `.rej` 补丁残留。

`.gitignore` 已覆盖这些模式；本次提交前也做了实际扫描。

## 3. 提交前扫描

在发布 worktree 上执行并确认：

```text
find . -type f \( -name '*.pyc' -o -name '*.db' -o -name '*.sqlite*' -o -name '*.log' \
  -o -name '*.env' -o -name '*.npz' -o -name '*.npy' -o -name '*.safetensors' \
  -o -name '*.bin' -o -name '*.pt' -o -name '*.onnx' -o -name '*.bak*' \) \
  -not -path './.git/*'
→ 0 个（清理 __pycache__ 后）

find . -type f -not -path './.git/*' -size +5M
→ 0 个

grep -rnE "<username>|C:[\\/]Users|D:[\\/]hermes|/home/[a-z]" --include='*.py' --include='*.md' \
  --include='*.yaml' --include='*.json' --include='*.txt' .
→ 0 个

grep -rnE "sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}" . --exclude-dir=.git
→ 0 个
```

补丁本身也单独扫过：无 `GIT binary patch`，无个人路径、邮箱、API key 或订阅凭据。

## 4. 补丁校验和

```text
5ab1e45258dd01d2a7d6b3cc56f4fb2f7f2f129a91011765aeb1d37d1557b8e1  hermes-agent-40d1e95f-eccd37ae.patch
30410b0eb39cdc1539f345fc0e0c2baa6732aaa636a188f5ec10ba599719540d  hermes-agent-ledger-fix.patch
c23b9673ee64e9eda2722cb877a2a8b2ff3d296354ca6f527eb045fe42b439a0  holographic-ed73195f-4cbd5b79.patch
```

## 5. 干净检出验证

见 [`INSTALL.md` §8](../INSTALL.md#8-验证干净克隆实测)：补丁 `--check` 通过，Hermes memory 相关
Python 测试 60 passed，Desktop UI 9 files / 50 tests、Electron 126 tests，插件自检 10 项、
侧车同步 4 项、阈值工具 20 passed / 55 skipped、Holographic 设置 5 passed。

0.6.1 包装插件自检 21 项通过，Ruff 0.15.22 检查通过。本地阈值建议和云端片段校准通过 Core 沙盒冒烟，云端使用本地接口替身。
