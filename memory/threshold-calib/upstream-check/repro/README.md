# H5 复现包：RECALL_CHECK_MARGIN（#121）

2026-11-25，Claude Code 按 `../CLAUDE-BRIEF-H5-REWORK.md` 重做后产出。全部是本地文件，没有提交，也没有发出去。

- 插件分支：`vendor/holo-check/plugin` 的 `feat/recall-check-margin`，基于上游 main `ceb802be781e9e31cd9509755ad18ea46194a774`（v0.31.4）。代码 6 个提交，到 `31de6eb5af2ae3366f1be32c3b847f338cbf2a7c`；第 7 个提交 `67229de5886bf802887cf88c4ef53162d2400a1f` 只把 `rows/` 的 14 个文件、`instruction.txt`、4 份门禁回执（命令行改成仓库内路径）和一个 README 加到 `results/issue121/`。
- 行文件全部出自 `31de6eb`，`git_sha` 不带 `-dirty`。本地 `rows/` 是 Windows 文本模式写的 CRLF，提交进分支时 git 归一成 LF，逐行内容相同。

## 结论

门禁用的是分支自带的 `tools/mcnemar_gate.py --pair check_margin`，两池结果与 A11 公开的数字逐项一致：

| 题池 | 命中@5 | 救回 / 丢失 | p | 噪声 | 混淆 | 门禁 | 回执 |
|---|---:|---:|---:|---:|---:|---|---|
| 决定池：multi（18 种语言）、contrast 英俄中、household test，540 道 | 480 → 486 | 6 / 0 | 0.031 | 93 → 93 | 34 → 34 | 通过 | `gate-540-decisive.txt` |
| 并列：再加 household dev 和 `synthetic_zh`，696 道 | 565 → 573 | 8 / 0 | 0.008 | 142 → 142 | 46 → 46 | 通过 | `gate-696-published.txt` |
| 并列：只有 household dev，120 道 | 74 → 76 | 2 / 0 | 0.5 | 48 → 48 | 7 → 7 | p 不够 | `gate-dev-beside.txt` |
| 并列：只有 `synthetic_zh`，36 道 | 11 → 11 | 0 / 0 | 1 | 1 → 1 | 5 → 5 | p 不够 | `gate-synthetic_zh-beside.txt` |

- 540 池救回的 6 个目标和旧回执 `../gate-five-sets.txt` 逐条相同。
- 和 A11 的旧行逐题比（`compare-with-a11.txt`）：只有 multi 的 3 行不同，原因是上游 0.31.3、0.31.4 把语料里的人名换了，门禁计数都没变。`hi` q7 两臂都少展示一条事实；`it`、`ko` q14（「该怎么回复 Leon？」）复核对目标说了 yes，这个目标两臂本来都靠人名展示出来了。
- 复核在决定池里被问了 29 次：9 个 yes（6 个救回、`it`/`ko` q14 的目标、household zh q051 上同一个人的另一条事实，这道题的目标本来就在），20 个 no（其中 7 个是闲聊轮，包括方案 A 放进来的 `contrast_ru` c17、c31），没有未答。
- 696 池两臂各 1,068 轮。关闭臂 0 次调用；复核臂 46 次，其中 22 次在什么都没展示的轮上；11 yes、35 no、0 未答。复核耗时中位 101 ms、最长 171 ms；最慢的一轮 232 ms，关闭臂是 81 ms（`row-stats.txt`）。

## 文件

| 文件 | 内容 |
|---|---|
| `rows/` | 14 个文件：7 个题集 × 两臂（`_coff`、`_c0.5`），每臂 1,068 行，共 2,136 行，只含上游公开题集 |
| `run-probe.sh` | 跑两臂的脚本。先起两个本机接口，见 `../README.md`「复现端到端」 |
| `rows.log` | 产出 `rows/` 的 14 次运行的日志。那时脚本还没设 `PYTHONIOENCODING`，控制台编码是 GBK，探针摘要里的俄文分类标签成了乱码；行文件本身是 UTF-8，不受影响。脚本现在已设好 |
| `rows-rerun/`、`rows-rerun.log`、`rerun-compare.txt` | 同一提交、同一脚本再跑一遍，查结果是否稳定：两臂逐题的门禁字段 0 处不同，复核臂 1,068 行的调用数、结果、原始分数和展示的事实全部相同，只有耗时不同 |
| `run-gate.sh` | 门禁脚本，产出上表 4 个回执，每个回执第一行是执行的命令 |
| `compare_rows.py`、`compare-with-a11.txt` | 新行与 A11 旧行（`../rows/`）逐题对比 |
| `row_stats.py`、`row-stats.txt` | 行戳、调用数、结果、耗时 |
| `budget/` | `--set budget`（token 预算集，不开嵌入、不开重排）在 main 和分支上各跑一遍：除耗时和 `git_sha` 外 160 行完全一致（`budget/compare.txt`）。分支拒绝在这个集上开复核：复核需要嵌入 |
| `instruction.txt`、`prefix.txt`、`suffix.txt` | 复核用的指令、模型卡的前后缀，逐字节从 `../../calib_answerability.py` 读出（ast，不执行），没有末尾换行 |
| `synthetic_check.py`、`synthetic-request-response.txt` | 两条合成请求和响应，以及插件默认复核读出的 yes / no |
| `main-red.txt`、`main-red.xml`、`main-red-reasons.txt` | 提交里的新测试文件（blob `7607a6fd`）在干净 main `ceb802b` 上的原始输出和逐条失败原因：28 红，10 个红在断言，18 个红在测的东西不存在 |
| `targeted-branch.txt` | 分支上新测试 28 个逐条通过，加 5 个已有文件共 96 通过；`ruff check .` 干净 |
| `suite-branch.txt`、`suite-main.txt`（及 `.xml`） | 全量套件，分支和干净 main 各一遍 |

## 版本

- 插件分支和基线见文首。测量时用的核心是提交 `e8a31a1` 里的 `memory/keyword-gate/core_shim`，已解到 `vendor/holo-check/core-e8a31a1/`。跑测试时用的是 `vendor/hermes-agent`（Hermes main `152fe189`）。这个检出带着别的工作留下的未提交改动（比如 `agent/memory_provider.py` 里新加的默认方法），分支和 main 两遍用的是同一份。
- 两个接口脚本在本仓库：`memory/threshold-calib/embed_endpoint.py`（最后改动 `dc749ab0`，blob `88ae749c`）、`rerank_endpoint.py`（`dc749ab0`，blob `7a700279`）。打分逻辑和指令在 `calib_answerability.py`（`7ed52b2b`，blob `e77c3175`）。三个文件在工作区都没有改动。
- Python 3.11.4、torch 2.11.0+cu128（CUDA 12.8）、transformers 5.8.1、sentence-transformers 5.5.0、numpy 1.26.4。显卡 RTX 4060 Laptop，驱动 591.74。
- 模型（`vendor/models/`，文件的 sha256）：
  - bge-m3：`pytorch_model.bin` `b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38`，`tokenizer.json` `21106b6d7dab2952c1d496fb21d5dc9db75c28ed361a05f5020bbba27810dd08`，`config.json` `26159e7ad065073448460117eb24b7a4572f6f4e78eadff65dc0a11c052449fa`
  - Qwen3-Reranker-0.6B：`model.safetensors` `27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b`，`tokenizer.json` `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4`，`config.json` `d479c427a9ca5295218063d4f9aca4f297ab4ac27487cca7af42c84643d51ef0`
  - Hugging Face 的 revision 没有记录。brief 提到的 HF 缓存在项目目录外，按全局约定没有去读。上面的 sha256 可以和 HF 文件页上的 LFS 哈希对照。
- 指令，186 字节，sha256 `5336bc93ae7c30960c4f5940de5a98826fe2ecee05c549a846897344d7b73b72`：

  > Decide whether the document alone supplies a concrete answer to the query, including the requested entity and attribute. A shared topic without the requested information is insufficient.

- 配对格式（以 `calib_answerability.AnswerVerifier.score` 为准）：`PREFIX + "<Instruct>: {指令}\n<Query>: {消息}\n<Document>: {事实}" + SUFFIX`，取最后一个位置上 "yes" 的 logit 减 "no" 的 logit。消息是插件交给召回的那段（本人的话，最多 4,000 字），事实是召回展示的那一行（`_one_line`：合并空白，最多 300 字）。超出模型上下文的一对在接口里返回 -100，当作 no。
- 分数到判断：`rerank_scale: logit`，中点是 0，大于 0 是 yes。合成例子：「Where is the spare key?」对「The spare key hangs behind the blue flowerpot on the balcony.」是 5.25，yes；对「The spare bulb lies behind the green bucket in the cellar.」是 -0.9375，no。

## 重跑

```bash
# 两个本机接口（各开一个终端，等到打印 ready）
python -E -B memory/threshold-calib/embed_endpoint.py vendor/models/bge-m3 12371
cd memory/threshold-calib && python -B rerank_endpoint.py ../../vendor/models/qwen3-reranker-0.6b 12372
# 两臂、门禁（参数是仓库根目录，用 C:/ 形式）
bash memory/threshold-calib/upstream-check/repro/run-probe.sh C:/aiprojects/hermes-optimization
PYTHONIOENCODING=utf-8 bash memory/threshold-calib/upstream-check/repro/run-gate.sh C:/aiprojects/hermes-optimization
```

`run-probe.sh` 发现插件检出有未提交改动就停下，不写 `-dirty` 的行。
