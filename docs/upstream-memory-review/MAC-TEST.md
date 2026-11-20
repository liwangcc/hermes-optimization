# Mac 复验：独立安装候选 Desktop 与记忆插件

这是开发版、合成数据测试，不是覆盖安装。**不需要登录或 API key**；生成式回复是本机固定夹具。`--work` 只给 testkit 使用，它会重置里面的两棵上游克隆。用新目录，不要指向 `~/.hermes` 或现有源码树。

## 1. 拿到候选版本

远端 `threshold-calib` 目前只是基线，不含本轮准备。收到 `hermes-memory-review-rc.bundle` 后，在 Terminal 执行（假定附件下载到 Downloads）：

```bash
REPO="$HOME/hermes-memory-review"
BUNDLE="$HOME/Downloads/hermes-memory-review-rc.bundle"
test -f "$BUNDLE" &&
  git clone --branch threshold-calib https://github.com/liwangcc/hermes-optimization.git "$REPO" &&
  cd "$REPO" &&
  git bundle verify "$BUNDLE" &&
  git fetch "$BUNDLE" refs/heads/memory-review-rc:refs/heads/memory-review-rc &&
  git switch memory-review-rc &&
  git rev-parse HEAD
```

这是增量 bundle，基线为 `60b05d05032be3295da7cc347bdc90501fa750df`（制作时已在远端分支）。不要用单独 `git clone <bundle>`；它没有重复打包公开基线。比较 `git rev-parse HEAD` 与发包回执中的 SHA。若以后发布了这个候选分支，再以经核对的远端 SHA 代替 bundle；不要直接拿远端默认分支试。

## 2. 先跑不需要模型权重的测试

准备有图形桌面的 macOS、Git / Xcode Command Line Tools（没有时 `xcode-select --install`）、Python 3.9+，以及 GitHub、PyPI、npm 等依赖源的正常联网。为独立运行预留约 15 GB，真模型步骤额外预留约 5 GB。候选 Hermes 自己的 PM 拉取工具、Python、锁定依赖和 Electron；不用改全局 Hermes 环境。

```bash
cd "$HOME/hermes-memory-review" &&
python3 docs/upstream-memory-review/testkit/run.py \
  --work "$HOME/hkit-memory-review" --jobs 2 --quick --only holo,adapter,pr3,pr7,all
```

首次下载和构建可能较久。用图形会话的 Terminal 启动，不要在无桌面的 SSH 会话中跑。`--quick` 只跳过 Holographic 完整测试套件，不跳过 HOLO-1 定向测试；`all` 是七份合体的状态，不等于逐份跑完。要跑七份独立测试，去掉 `--only …`。两条候选 Issue 的重点是 `pr3`（分层容量）与 `pr7`（一键任务）。合体 e2e 默认用替身侧车。

## 3. Apple Silicon：跑真实 BGE-M3

`uname -m` 确认 `arm64`，用原生 ARM 的 **Python 3.11**。以下单独装 PyTorch 与 Sentence Transformers；只读官方公开模型文件，运行时完全本地。`torch==2.11.0` 的 macOS CPython 3.11 wheel 是 arm64；Intel Mac **先跑第 2 节**，不要把无法安装这个 wheel 当成产品回归。此节命令尚未在 Mac 现场验收。

```bash
(
set -e
cd "$HOME/hermes-memory-review"
WORK="$HOME/hkit-memory-review"
mkdir -p "$WORK"
python3.11 -c 'import platform; assert platform.machine() == "arm64", "Use native arm64 Python 3.11"'
python3.11 -m venv "$WORK/sidecar-venv"
PY="$WORK/sidecar-venv/bin/python"
"$PY" -m pip install -r memory/sidecar/requirements.txt \
  'torch==2.11.0' 'sentence-transformers==5.5.0' 'transformers==5.8.1' 'numpy==1.26.4'
HF_HOME="$WORK/hf-download" HF_HUB_DISABLE_IMPLICIT_TOKEN=1 "$WORK/sidecar-venv/bin/hf" download BAAI/bge-m3 \
  --revision 5617a9f61b028005a4858fdac845db406aefb181 --local-dir "$WORK/bge-m3" \
  pytorch_model.bin config.json config_sentence_transformers.json modules.json \
  sentence_bert_config.json sentencepiece.bpe.model special_tokens_map.json \
  tokenizer.json tokenizer_config.json 1_Pooling/config.json
printf '%s  %s\n' b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38 \
  "$WORK/bge-m3/pytorch_model.bin" | shasum -a 256 -c
python3 docs/upstream-memory-review/testkit/run.py --work "$HOME/hkit-memory-review" \
  --only live --jobs 2 --sidecar-python "$PY" --bge-model-dir "$WORK/bge-m3"
)
```

公开模型约 2.3 GB，不在 bundle 里。校验不符会停止，不会启动测试。

这个模式构建并启动真实 Electron 和 Hermes 后端，夹具在独立临时 home 写入 12 条虚构事实、安装真实 `holographic-semantic`，自动进入记忆设置点击 **Run**。真实 BGE-M3 在 CPU 上运行，侧车只监听临时本机端口。预期：`0/12 → 12/12`、落盘 12 个 1024 维向量、第二次点击新增 0、重启侧车后仍能读到 12；测试结束退出独立进程。不验证真实聊天模型的判断质量，也不把这个小样本的运行时间当性能承诺。

## 4. 交回一份结果

标准模式 `docs/upstream-memory-review/testkit/results/macos-<arch>/report.md`；真模型模式为 `macos-<arch>-live/report.md`，其 `screenshots/real-sidecar.json` 与 `5-provider-job.png` 是真实索引证据。交回 **commit SHA + `sw_vers` 和 `uname -m` + 两份 `report.md`（如果都跑了）**，失败时只附对应步骤的日志和截图，先检查个人路径或凭据，不发整个 HOME、数据库或 `.env`。卡在依赖安装请报告阶段，不改代码和代理去把测试改绿。
