# macOS 和 Linux 上使用日常版：事前准备与自检

2026-11-22。[INSTALL.md](../INSTALL.md) 的命令是在 Windows 上验证的。这一页写 macOS 和 Linux 上不同的地方，以及一条自检命令：跑完就知道这台机器上的日常版有没有在正常工作。装好之后要做的全部四件事见[使用手册](user-guide.md)。

**先说结论：macOS 和 Linux 上有两件事不会自动完成，漏掉任何一件，召回都会静默变差，对话里看不出来。**

1. 本地向量服务（侧车）要手工启动。设置页的「一键部署并连接」只能在 Windows x64 上从零部署。
2. 词干包 `snowballstemmer` 必须在跑 Hermes 的那个 Python 里。Hermes 只在 Python 3.14 及以上安装它。

## 各平台支持什么

| 功能 | Windows x64 | macOS | Linux |
|---|---|---|---|
| Hermes 和两个补丁、两个插件（INSTALL 第 1 到 5 步） | 支持 | 命令相同 | 命令相同 |
| 「一键部署并连接」从零部署本地模型 | 支持 | 不支持，按钮会报「首次本地部署需要 Windows x64 和 Hermes Python 3.14」 | 不支持，同左 |
| 手工侧车（`memory/sidecar/`，BGE-M3） | 支持 | 支持，在 CPU 上运行 | 支持，有 CUDA 显卡时用显卡，否则用 CPU |
| 「一键部署并连接」连接已经在运行的手工侧车 | 支持 | 代码支持，没有在 Mac 上验证过 | 代码支持，没有验证过 |
| 「一键初始化阈值」 | 三个内置模型给固定推荐值 | 在设置页连接过侧车后显示 BGE-M3 的 0.55；只用命令行配置时显示「无法识别」 | 同左 |
| BGE-M3 以外的本地模型 | 见[最后一节](#bge-m3-以外的本地模型) | 同左 | 同左 |

- 侧车只认 CUDA 显卡，不会用苹果芯片的显卡。BGE-M3 的权重约 2.3 GB，16 GB 内存的机器够用。
- 阈值的默认值 0.55 就是 BGE-M3 的推荐值。「一键初始化阈值」显示「无法识别」时不用改它。

## 事前准备

第 1 到 5 步照 [INSTALL.md](../INSTALL.md) 做，那里的命令本来就是 POSIX 写法。下面是 macOS 和 Linux 上要多做的。

### 1. 确认 Hermes 的 Python 和词干包

```bash
cd /path/to/hermes-agent
source ./activate
python -c "import sys, snowballstemmer; print(sys.version.split()[0], 'stemmer ok')"
```

- 应该打印 `3.14.x stemmer ok`。
- 报 `ModuleNotFoundError`：这个 Python 里没有词干包。执行 `python -m pip install snowballstemmer==3.1.1`。
- 用别的 Python 跑测试脚本时同样要装。让 agent 代跑测试时最容易漏这一步：agent 常用系统自带的 Python。

没有词干包时，英文词只能按原样匹配，跨语言的问题会丢。合成库上是 29 题变成 26 题。

### 2. 准备侧车的运行环境和模型

侧车用自己的环境，不要装进 Hermes 的 Python 里。

```bash
cd /path/to/hermes-optimization/memory/sidecar
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install "huggingface_hub[cli]"
.venv/bin/huggingface-cli download BAAI/bge-m3 \
  --revision 5617a9f61b028005a4858fdac845db406aefb181 --local-dir models/bge-m3
```

- 这个环境用 Python 3.10 到 3.13 来建。系统的 `python3` 不在这个范围时，把第一条命令换成 `python3.11 -m venv .venv`：Ubuntu 26.04 自带的是 3.14，WSL2 上实测用的是 3.11，3.14 没有试过。
- 模型约 2.3 GB。PyTorch 的安装包从几十 MB 到几 GB 不等，取决于平台和是否带 CUDA。
- Linux 上要用显卡，按 pytorch.org 的说明装和驱动匹配的 CUDA 版本。

### 3. 启动侧车

```bash
cd /path/to/hermes-optimization/memory/sidecar
SEMANTIC_DB="$HERMES_HOME/memory_store.db" .venv/bin/python server.py
```

另开一个终端确认：

```bash
curl -s http://127.0.0.1:8791/health
curl -s -X POST http://127.0.0.1:8791/sync -d '{}'
```

- `/health` 里 `ok` 为 `true`，`device` 是 `cpu` 或 `cuda`，`facts` 是一个数字。
- `/sync` 给已有的事实建索引。跑完后 `/health` 里的 `facts_indexed` 应该等于 `facts`。
- 侧车要一直开着。关掉以后召回退回纯词法，不会报错。

`facts` 是 `null`，或者 `/sync` 返回 `unable to open database file`：侧车没找到事实库文件。这时 `ok` 仍然是 `true`，它只表示模型加载好了。两种原因：

- 启动侧车的那个终端里没有设 `HERMES_HOME`，路径变成了 `/memory_store.db`。设好后重启侧车。
- 全新安装，事实库还没建。侧车只读库，不会建库；`hermes memory status` 也不会建。插件在第一个会话里初始化时才建库。建好之后侧车不用重启，它每次请求都重新打开库。

### 4. 打开语义通道

```bash
hermes config set plugins.hermes-memory-store.semantic_enabled true
hermes config set plugins.hermes-memory-store.semantic_url http://127.0.0.1:8791
```

用 Desktop 的话，侧车启动后在「向量模型 → 本地 → BGE-M3 → 一键部署并连接」里点一次，它会连接已经在运行的侧车，效果相同。

## 自检

在 Hermes 的 Python 里运行（先 `source ./activate`）。它在临时目录里把 30 条公开的合成事实和 48 道题过一遍已安装的插件，不读你的事实库和配置。

```bash
python /path/to/hermes-optimization/memory/threshold-calib/check_daily_install.py \
  --core-src /path/to/hermes-agent \
  --base-src "$HOME/holographic-src" \
  --sidecar-python /path/to/hermes-optimization/memory/sidecar/.venv/bin/python \
  --model-dir /path/to/hermes-optimization/memory/sidecar/models/bge-m3
```

去掉后两个参数就只查词法这一半，不需要侧车和模型。脚本会自己起一个临时的侧车，和第 3 步那个互不影响。

要把结果报给别人，或者核验别人报来的结果，按[测试标准](test-standard.md)做：加 `--out daily-check.json` 交报告文件，收到的人用 `--verify` 核验。

### 怎么读结果

| 输出里的字段 | 正常值 | 不正常时说明什么 |
|---|---|---|
| `stemmer` | `true` | `false`：词干包没装，见上面第 1 步 |
| `numpy` | `true` 或 `false` 都正常 | 只影响首位命中，见下面的对照表 |
| `words_only.hit5` | 29（共 36） | 26：词干包没装 |
| `closest_fact.hit5` | 33（共 36） | 和 `words_only` 一样：侧车没有起作用 |
| `closest_fact.gave_up` | 0 | 大于 0：侧车答得比插件的预算慢，这些题退回了词法 |
| `closest_fact.ms_median` / `ms_max` | 远小于 `budget_ms`（400） | 接近或超过 400：调大 `semantic_timeout_ms` |
| `to_fix` | 空 | 列出要修的东西，按顺序修 |

`ms_max` 超过预算时：

```bash
hermes config set plugins.hermes-memory-store.semantic_timeout_ms 1500
```

### 前五命中率对照

别人报给你一个命中率时，先对这张表。都是合成库 36 道有答案的题。

| 前五命中 | 是什么情形 |
|---:|---|
| 33/36 | 日常版正常工作 |
| 32/36 | 语义追加起作用了，但没装词干包 |
| 29/36 | 只走了词法：侧车没开、没连上，或者 `semantic_enabled` 没打开 |
| 26/36 | 只走了词法，而且没装词干包 |

不在表里的数（比如 30、31）：语义追加只在一部分题上起了作用。先看自检输出里的 `gave_up`，大于 0 就是侧车对一部分题答得比预算慢。

每道题要在新的会话里问。同一个会话里连着问，最近展示过的事实不会再展示，命中率会偏低。

只对前五命中，不要对首位命中。首位命中还取决于跑 Hermes 的 Python 里有没有 numpy：有 numpy 时上游插件多用一路结构排序，前五不变，首位差一题。只走词法时的首位命中：

| | 有 numpy | 没有 numpy |
|---|---:|---:|
| 有词干包 | 25/36 | 26/36 |
| 没有词干包 | 22/36 | 23/36 |

Hermes 本身不依赖 numpy，默认安装里没有它。上表在 Windows 上换 12 个哈希种子结果都不变。WSL2 上有 numpy 时跑了 10 遍（5 遍随机种子、5 遍固定种子），都是前五 29、首位 25，和上表一致。

## 验证状态

| 环境 | 词干包 | 只走词法 | 带语义追加 | 侧车单次耗时（中位数 / 最大） | 状态 |
|---|---|---:|---:|---|---|
| Windows 11 x64，CUDA 显卡 | 有 | 29/36 | 33/36 | 30 / 46 毫秒 | 已测 |
| Windows 11 x64，侧车强制用 CPU | 有 | 29/36 | 33/36 | 69 / 98 毫秒 | 已测 |
| Windows 11 x64，屏蔽词干包 | 无 | 26/36 | 32/36 | 41 / 67 毫秒 | 已测 |
| macOS，16 GB | 未知 | 26/36（用户报告） | 未知 | 未知 | 和「没装词干包、侧车没起作用」的数相同；按本页准备后还没有复测 |
| Linux（WSL2） | 有 | 29/36 | 33/36 | 15.9 / 21.8 毫秒 | 已测（Ubuntu 26.04 LTS，cuda），重复一次结果相同 |

- CPU 和显卡上的命中数相同，所以 Mac 上准备齐全后预期也是 33/36，这一点还没有实测。
- Linux 这一行只测了命令行和 CUDA 显卡。没有测的：Desktop 构建、侧车在 CPU 上运行、「事前准备」第 2 步的模型下载命令（测试用的是机器上已有的一份 BGE-M3）。
- 同一环境里测试套件 132 项全部通过。原始输出在 [wsl2-evidence/](../wsl2-evidence/METRICS.md)。

## BGE-M3 以外的本地模型

手工侧车只支持 BGE-M3。别的本地模型不要走侧车这条通道：

- 把它当作向量接口接入：用任意提供 OpenAI 兼容 `/v1/embeddings` 的本机服务，在设置页「向量模型 → 云端」的连接向导里填本机地址。本机回环地址允许用 HTTP，也可以不填密钥。
- 这条通道走上游的准入，不需要按模型定阈值。在冻结真实库上用四个本地模型测过：命中都不降，噪声题和混淆题不变。数字见 [CLOUD-FLOOR-RESULTS.md](../memory/threshold-calib/CLOUD-FLOOR-RESULTS.md)。
- 两条通道二选一：接了向量接口，就把 `semantic_enabled` 关掉。
- 只用命令行、不经过连接向导来配置这条通道的写法没有验证过，这里不给命令。
