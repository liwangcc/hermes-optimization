# WSL2 日常版验证数据（Linux）

日期：2026-11-22。对应 `docs/platforms.md`「验证状态」表「Linux（WSL2）」行。
范围：日常版（Hermes 固定提交 + 两个补丁 + Holographic 固定提交 + 补丁 + holographic-semantic 包装插件 0.6.1）的记忆检索自检与测试套件。Desktop 构建未做（WSL2 只用命令行）。

## 环境

- Ubuntu 26.04 LTS（Resolute Raccoon），WSL2，内核 6.6.114.1-microsoft-standard-WSL2 x86_64，glibc 2.43
- GPU：NVIDIA GeForce RTX 4060 Laptop GPU（8 GB），驱动 591.74，CUDA 13.1；侧车 device=cuda
- Hermes 运行时 Python 3.14.9（托管），snowballstemmer 在位，numpy 在位
- 侧车 venv：Python 3.11.15，numpy 2.4.6，torch 2.15.0+cu132，sentence-transformers 6.3.0
- 模型：本机已有的一份 BGE-M3（`vendor/models/bge-m3`，权重未入库；本次未下载）
- HERMES_HOME：全新空目录（WSL ext4），与任何正在运行的安装无关
- 明细见 `environment.txt`

## 标准报告（daily-check-1）

按 [测试标准](../docs/test-standard.md) 用 `--out` 产出，`--verify` 核验通过：

```bash
python memory/threshold-calib/check_daily_install.py \
  --core-src <Hermes 检出> --base-src <Holographic 检出> \
  --sidecar-python <侧车 venv>/bin/python --model-dir vendor/models/bge-m3 \
  --out daily-check-linux.json
python memory/threshold-calib/check_daily_install.py --verify daily-check-linux.json
```

核验输出（系统 Python 3.14.4，仓库根目录）：

```json
{
 "standard_result": true,
 "problems": [],
 "to_fix": []
}
```

报告要点（全文见 `daily-check-linux.json`）：standard.name=daily-check-1，data=d9380874dad3；words_only 29/36，没命中 P5 P7 P10 C1 C5 C6 C10；closest_fact 33/36，没命中 P5 P10 C6，device=cuda，耗时中位/最大 15.5 / 19.6 ms，gave_up=0，to_fix=[]。没命中的题与参考逐题相同。

## 早期测量（早于 daily-check-1 标准，无没命中题号，保留作历史数据）

在 `source ./activate` 之后的环境里执行（运行时 venv 解释器，Python 3.14.9）：

| 运行 | stemmer | words_only.hit5 | closest_fact.hit5 | device | 耗时中位/最大 | gave_up | to_fix |
|---|---|---|---|---|---|---|---|
| 第一遍（仅词法） | true | 29/36 | — | — | — | — | 提示补跑语义步 |
| 第二遍（带侧车） | true | 29/36 | 33/36 | cuda | 15.9 / 21.8 ms | 0 | [] |
| 独立重复（第二遍） | true | 29/36 | 33/36 | cuda | 18.4 / 27.7 ms | 0 | [] |

与参考预期一致：stemmer=true、words_only.hit5=29、closest_fact.hit5=33、gave_up=0、to_fix 为空。侧车预算 400 ms，facts_indexed=30，requests=47，appended=7。

原始 JSON：`check1-words-only.json`、`check2-with-sidecar.json`、`check2-replicate.json`。

### 首位命中的差别来自 numpy，不是哈希种子

有 numpy 时上游插件多用一路结构排序：前五不变，首位差一题（见 platforms.md「前五命中率对照」）。本机有 numpy，只走词法连跑 10 遍——5 遍随机哈希种子、5 遍固定 PYTHONHASHSEED=0——全部 numpy=true、hit5=29、first=25，种子无影响：

```
random-1..5: numpy=True hit5=29 first=25
seed0-1..5:  numpy=True hit5=29 first=25
```

早期一次 first=26 的运行用的是没有 numpy 的旧运行时环境，差别与种子无关。

## 测试套件

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=<Hermes 检出> \
  <侧车 venv>/bin/python -m pytest \
  memory/threshold-calib/tests memory/sidecar/test_sync.py memory/plugin/test_catalog.py \
  -p no:cacheprovider -v
```

**132 passed**（逐条清单见 `pytest-results.txt`）。解释器要求：除 numpy/torch 外还需 pytest 与 ruamel.yaml；PYTHONPATH 需指向 Hermes 检出（包装插件 import 核心的 `utils`/`hermes_yaml`）。

## 真实侧车 + 空库行为

手工侧车（`memory/sidecar/server.py`，端口 8791，模型 cuda 加载约 9 s）：

- HERMES_HOME 全空（memory_store.db 文件不存在）：`/health` 的 facts=null；`/sync` 返回 `unable to open database file`（侧车只读，不能建库）；`hermes memory status` 也不建库，显示 provider=holographic-semantic、available。
- 空库文件存在（0 条事实）：`/health` facts=0、facts_indexed=0；`/sync` embedded=0、remaining=0、ms=0.5。

原始输出：`sidecar-empty-store.txt`。

## 文件清单

| 文件 | 内容 |
|---|---|
| daily-check-linux.json | daily-check-1 标准报告（--verify 通过） |
| check1-words-only.json | 早期第一遍自检原始 JSON |
| check2-with-sidecar.json | 早期第二遍自检原始 JSON |
| check2-replicate.json | 早期独立重复运行原始 JSON |
| pytest-results.txt | 132 项测试逐条结果 |
| environment.txt | 环境快照（主机名已泛化） |
| sidecar-empty-store.txt | /health 与 /sync 原始输出 |