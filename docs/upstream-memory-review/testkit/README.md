# 测试工具：一条命令验证全部改动

在本机把这次要提交的改动全部验证一遍，并生成一份报告。要验证的改动包括：Hermes 主库的 7 个 PR（`../patches/01–07`）、holographic 插件的 HOLO-1（`../patches/holo-1-config-schema.patch`），以及本仓库的适配器 `memory/plugin/holographic-semantic`。

**测试者不需要打补丁，也不需要自己准备 Hermes 的开发环境。** `run.py` 会自动完成下面这些事：

1. 拉取 Hermes（固定在 `152fe189`）和 holographic 插件（固定在 `76689f9`）。
2. 调用 Hermes 自己的 `setup-hermes.sh` 下载 Python 3.14、Node、pnpm 和测试环境，全部放在工作目录里。
3. 对每个 PR，在干净的基线上按顺序打上它的补丁，再跑这个 PR 的测试（见 `plan.py`，和 `../RUNBOOK-HERMES.md` 第 5 节一致）。
4. 跑 HOLO-1 的测试、插件的完整测试套件、ruff、`hermes plugins validate`，以及适配器的自检。
5. 把 7 个补丁合在一起，在真实桌面端里跑真实适配器的 e2e，顺便生成截图。默认用替身侧车；真模型另跑 `--only live`。

## 1. 准备（每台机器一次）

| 平台 | 需要装的 |
|---|---|
| 全部 | Git；Python 3.9 或更高（只用来启动 `run.py`）；能访问 GitHub、PyPI、npm 的网络；约 15 GB 空闲磁盘 |
| Windows 10/11 | [Git for Windows](https://git-scm.com/download/win)，它自带 Git Bash，`run.py` 会自己找到 |
| macOS | Xcode Command Line Tools：`xcode-select --install` |
| Linux（Debian/Ubuntu） | `sudo apt install build-essential xvfb libgtk-3-0 libnotify4 libnss3 libxss1 libxtst6 xdg-utils libatspi2.0-0 libdrm2 libgbm1 libasound2t64`（22.04 及更早版本把 `libasound2t64` 换成 `libasound2`）。有图形桌面就不需要 xvfb |

不需要预先安装 Node、pnpm、Python 3.14 或 uv。

## 2. 运行

在本仓库根目录执行：

```bash
python docs/upstream-memory-review/testkit/run.py --work ~/hkit --jobs 4
```

- `--work`：放工作克隆和隔离安装的目录，默认 `~/hkit`。首次用新目录，重复运行会重置其中的 Hermes / Holographic 测试克隆。不要指向已有安装。Windows 上用短路径，例如 `--work C:\hkit`。
- 第一次运行要 1–2 小时，大部分时间在下载和安装。再次运行会复用工作目录，快很多。
- 只跑一部分：`--only pr3,pr4`。可选的名字：`holo, adapter, pr1, pr2, pr3, pr4, pr5, pr6, pr7, all`。
- `--jobs N`（也可写 `-j N`）：限制 Vitest 和 Hermes 后端测试的并行 worker，默认 4；内存紧张时设为 2 或 1。
- `--skip-e2e`：不构建桌面端，也不跑 Electron 测试。`--quick`：跳过插件的完整测试套件（约 10 分钟）。

**隔离**：Hermes 的运行数据在 `--work` 内，Electron 使用单独的 userData，报告在本目录的 `results/`。下载工具可能复用机器上的普通软件包缓存；测试不需要你的模型登录。运行环境剔除常见凭据变量，合成 home 禁止借用外部 CLI 登录。

**真模型（可选）**：用 `--only live --sidecar-python PATH --bge-model-dir DIR` 构建合体候选并运行真实 BGE-M3（CPU），只做两项适配器 E2E，不重跑全套。`PATH` 是装好 `memory/sidecar/requirements.txt` 的独立 Python，`DIR` 是本机的 BGE-M3 模型目录。报告落在 `results/<平台>-live/`，不会替换标准报告。详细依赖与验收见 [Mac 测试说明](../MAC-TEST.md#3-apple-silicon跑真实-bge-m3)。

## 3. 结果

结果在 `results/<平台>/` 下，例如 `results/macos-arm64/`：

| 文件 | 内容 |
|---|---|
| `report.md` | 每一步的状态、结果摘要和参考值，失败项列在最后 |
| `report.json` | 同样的内容，机器可读 |
| `logs/<步骤>.log` | 每一步的完整输出 |
| `screenshots/` | 真实适配器 e2e 拍的 6 张截图 |

每一步的状态有三种：

- `passed`：通过。
- `known`：失败，但和未改动的基线上的失败完全一样，不算回归。已知失败列在 `plan.py` 的 `KNOWN` 里：
  - Windows：`TestMemoryFileLockPermissions`，以及 `scripts/check` 的 `shims`、`line-endings`。
  - Windows：ByteRover 子进程测试仅在 `PATH` 首项正确但使用 Windows 反斜杠、触发 POSIX 路径断言时记为 `known`。同一个用例的凭据、profile 或其他断言失败仍计为 `failed`。
  - 所有平台：`scripts/check` 的 `no-tmp`，由 main 上的 `plugin-catalog/layersift.yaml` 触发。
- `failed`：需要看日志。

「Expected」一列是固定基线的 Windows 参考值。若换基线导致覆盖范围变化，请在回执中说明。

## 4. 测试者要交回什么

交回 `report.md` 和测试的 commit SHA；失败再附对应步骤的日志和截图，先检查敏感路径或真实凭据。`results/` 不进 Git。**不要修改补丁或代码去让测试通过**，失败本身就是要交回的结果。

## 5. 遇到问题

- 卡在 `env-setup`：这是 Hermes 自己的 `setup-hermes.sh` 在下载，看 `logs/env-setup.log`。网络出错时，交回对应日志的脱敏片段，不为试跑更改系统代理。
- Electron e2e 会使用工作目录内 PM 已装好依赖的测试解释器，不要求额外创建 `.venv`，也不使用测试者的 Hermes 安装。
- Linux 上 e2e 报 `no display and no xvfb-run`：按第 1 节安装 xvfb。
- 想从头再来：用一个新的 `--work` 目录；每次运行会覆盖同模式下的旧报告，需要留档请先复制报告。
