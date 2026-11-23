# 日常版测试标准（daily-check-1）

**只有用这一页的命令、这一套题跑出来的报告才算标准结果。交回来的是报告文件，不是一个百分比。**

自己出题、换分母、只报百分比的结果都没法核验，也没法和别人的结果比。

## 标准是什么

| 项目 | 固定值 |
|---|---|
| 事实 | 30 条公开的合成事实，带冻结的关键词（`issue95-evidence/synthetic/`） |
| 题目 | 48 道：36 道有答案，12 道没有答案 |
| 指标 | 前五命中：36 道有答案的题里，前五条出现了目标事实的题数。分母固定是 36 |
| 问法 | 每道题一个新会话 |
| 两步 | 只走词法；再加上语义追加（BGE-M3，阈值 0.55） |
| 运行位置 | 临时目录。不读你的事实库和配置 |

## 怎么跑

先按 [platforms.md](platforms.md#事前准备) 准备好。然后在 Hermes 的 Python 里运行（先在 Hermes 检出目录执行 `source ./activate`）：

```bash
python /path/to/hermes-optimization/memory/threshold-calib/check_daily_install.py \
  --core-src /path/to/hermes-agent \
  --base-src "$HOME/holographic-src" \
  --sidecar-python /path/to/hermes-optimization/memory/sidecar/.venv/bin/python \
  --model-dir /path/to/hermes-optimization/memory/sidecar/models/bge-m3 \
  --out daily-check.json
```

- 把 `daily-check.json` 原样交回来。不要改写，不要只摘其中的数字。
- 去掉 `--sidecar-python` 和 `--model-dir` 只跑词法这一步。这样的报告也能核验，但只说明了一半。
- 每个字段的读法见 [platforms.md](platforms.md#怎么读结果)。

## 参考结果

没命中的题只取决于有没有词干包，和 numpy、显卡还是 CPU 都无关。

| 词干包 | 只走词法 | 没命中的题 | 带语义追加 | 没命中的题 |
|---|---:|---|---:|---|
| 有 | 29/36 | P5 P7 P10 C1 C5 C6 C10 | 33/36 | P5 P10 C6 |
| 没有 | 26/36 | 上面 7 道，加 X4 X5 X7 | 32/36 | P5 P10 X4 C6 |

- 第一行是日常版正常工作的结果。
- 第二行说明这台机器要装词干包，报告本身仍然是有效的标准结果。
- 首位命中不在核验范围内：有没有 numpy 会让它差一题。见 [platforms.md](platforms.md#前五命中率对照)。

这些数在 Windows 11（显卡和 CPU）上测过，有无 numpy 各测一遍。WSL2（Ubuntu 26.04，显卡）上的命中数相同；那几份报告早于这个标准，没有记录没命中的题。

## 怎么核验

收到别人的 `daily-check.json` 后，在本仓库里运行。任何 Python 3.10 以上都行，不需要 Hermes：

```bash
python memory/threshold-calib/check_daily_install.py --verify daily-check.json
```

| 输出 | 含义 |
|---|---|
| `standard_result: true` | 是这一版标准的报告，数对得上，没命中的题和参考完全相同 |
| `problems` | 不算标准结果的原因：不是这一版标准、数对不上，或者列出和参考不同的题 |
| `to_fix` | 那台机器要修什么。空表示环境没有问题 |

三种读法：

- `standard_result` 为 `true`，`to_fix` 为空：那台机器上日常版正常工作。
- `standard_result` 为 `true`，`to_fix` 不为空：报告有效，但那台机器要按 `to_fix` 修，常见的是装词干包。
- `standard_result` 为 `false`：看 `problems`。和参考不同的题加上 `to_fix` 里的超时提示，说明侧车对一部分题答得比预算慢。

核验能发现的：换了题、换了脚本版本、数字抄错或算错、结果和参考不一致。它防不了故意伪造的报告。

## 不算标准结果的

- 自己出的题，或者让 agent 出的题。例子：25/30 是 83.3%，但和 36 道题的参考数不能比。
- 别的分母：把 48 道题全算进去，或者只算其中一部分。
- 在同一个会话里连着问。最近展示过的事实不会再展示，命中会偏低。
- 在自己的真实库上测。这有用，但它回答的是另一个问题，不能和参考数比。
- 只有百分比，没有报告文件。

## 让 agent 代跑时发给它的话

```text
在 Hermes 的 Python 里运行下面这条命令（先在 Hermes 检出目录执行 source ./activate），路径换成本机的：

python <本仓库>/memory/threshold-calib/check_daily_install.py --core-src <Hermes 检出> --base-src <Holographic 检出> --sidecar-python <侧车环境的 Python> --model-dir <BGE-M3 目录> --out daily-check.json

不要自己出题，不要自己算命中率，不要修改脚本。
跑完把 daily-check.json 的全文原样贴回来。命令报错就把报错原样贴回来。
```

## 版本

- 标准的名字是 `daily-check-1`，写在报告的 `standard.name` 里。事实、关键词、题目或参考结果变了，就换名字。
- `standard.data` 是事实、关键词和两个题目文件内容的指纹。核验时和本地的文件比对，不一致就不算这一版的结果。
