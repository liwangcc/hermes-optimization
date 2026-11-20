# Hermes 执行手册：holographic 插件库 HOLO-1

- **执行者**：Hermes Agent。**编写者**：Claude Code，2026-11-19（代码、补丁、测试、正文）。**对外批准人**：@liwangcc。
- 规则全部沿用 [`RUNBOOK-HERMES.md`](RUNBOOK-HERMES.md) 第 1 节：哪些动作要批准、永远不做的事、什么情况停下来报告、记录格式。本手册只写 HOLO-1 自己的步骤。
- 每个动作照样记进 [`SUBMISSION-LOG.md`](SUBMISSION-LOG.md)，步骤 ID 用本手册的 `H1.x`。

| 文件 | 作用 | Hermes 能不能改 |
|---|---|---|
| 本文件 | 执行依据，第 5 节是 PR 正文 | 不能 |
| `patches/holo-1-config-schema.patch` | HOLO-1 的代码，基于插件库 main `76689f9`（0.30.1） | 不能 |

[插件 Issue 草稿](issues/C-holographic-settings.md)先征询设置面板方向，**发 PR 用本手册第 5 节的正文**。

---

## 1. 什么时候做

- 前提：`RUNBOOK-HERMES.md` 的 A7（插件库 Issue）已经开出，且维护者明确愿意审这个设置面板 PR；沉默不算同意。
- 维护者已经表示要自己写：不提 PR，停下来报告用户，由用户决定是否在 issue 里贴出补丁作参考。

## 2. 环境（Windows，Git Bash）

```bash
ROOT="$PWD"                            # 先进入本仓库根目录
UP=$ROOT/vendor/upstream-hermes-pr       # 干净 core 测试克隆，不是旧投稿树
DOCS=$ROOT/docs/upstream-memory-review
PY=$UP/.venv/Scripts/python.exe
T=$ROOT/vendor/tools
FORK=$ROOT/vendor/holo-fork/plugin       # 目录名必须是合法的 Python 包名（CI 也检出到 plugin/），否则 pytest 导入失败
CORE=$T/tmp/hermes-main                  # 干净的 Hermes main，给插件测试当 core 用
DEPS=$T/tmp/holo-deps                    # 插件的两个依赖，不装进上游测试用的 venv
export PYTHONIOENCODING=utf-8
```

- `vendor/hermes-plugin-holographic` 是 Claude Code 的工作克隆，里面有未提交的改动。**不要在那里提交，也不要清理它。**

## 3. 准备（本地；H1.1 需要用户先在 GitHub 上操作）

### H1.1 fork（用户在 GitHub 上操作）

用户在 GitHub 上把 `itpartypattaya/hermes-plugin-holographic` fork 成 `liwangcc/hermes-plugin-holographic`，并同步到最新 main。Hermes 只记录「用户已 fork」。

### H1.2 克隆 fork，禁用向上游推送

```bash
mkdir -p $ROOT/vendor/holo-fork
git clone --depth=1 https://github.com/liwangcc/hermes-plugin-holographic.git $FORK
git -C $FORK remote add upstream https://github.com/itpartypattaya/hermes-plugin-holographic.git
git -C $FORK remote set-url --push upstream DISABLED
git -C $FORK config user.email        # 必须是绑定在 @liwangcc 上的邮箱，不是就停下来问
```

### H1.3 准备测试用的 core 和依赖

```bash
rm -rf $CORE && mkdir -p $CORE
git -C $UP fetch --depth=1 origin main
git -C $UP archive origin/main | tar -x -C $CORE
UV_CACHE_DIR=$T/uv-cache $T/uv/uv.exe pip install --target $DEPS --python $PY "numpy>=1.26,<3" "snowballstemmer>=2.2,<4"
```

## 4. 应用、验证、提交（本地）

### H1.4 应用补丁

```bash
cd $FORK
git fetch --depth=1 upstream main
git switch -c feat/desktop-config-schema upstream/main
git apply --3way $DOCS/patches/holo-1-config-schema.patch
```

打不上就按 `RUNBOOK-HERMES.md` 1.3 停下来报告（这个补丁里没有生成文件）。

### H1.5 验证

```bash
cd $FORK
HERMES_AGENT_REPO=$CORE PYTHONPATH=$DEPS $PY -m pytest -q -p no:cacheprovider \
  tests/test_holographic_config_schema.py tests/test_holographic_save_config.py     # 7 passed
$UP/.venv/Scripts/ruff.exe check .                                                    # All checks passed!
mkdir -p $T/tmp/validate-home
HERMES_HOME=$T/tmp/validate-home PYTHONPATH=$CORE $PY -c \
  "import sys; sys.argv=['hermes','plugins','validate','$FORK']; from hermes_cli.main import main; main()" </dev/null
                                                                                      # Validation passed.
```

- `validate` 会打印两条警告（`security scan caution`、`private core imports`），在 main 上本来就有，第 5 节正文也说明了，不算失败。
- 完整测试套件交给 PR 上的 CI 跑（Linux、macOS、Windows）。浅克隆里没有 tag，`tests/test_holographic_compat.py` 在本地跑不了，不要为此改成完整克隆。

### H1.6 提交

```bash
cd $FORK && git add -A
git commit -m "feat: configure search by meaning in the Desktop (config_schema.py)" -m "See #<A7 的编号>."
```

## 5. 推送和开 PR（需批准 → 对外）

1. 把下面的正文里的 `#HOLO-ISSUE` 换成 A7 的编号（同一个仓库，写 `#N` 即可），存为 `posted/H1.md`。
2. 正文和下面两条命令一起交给用户，等批准。
3. 批准后执行：

```bash
git -C $FORK push -u origin feat/desktop-config-schema
gh pr create -R itpartypattaya/hermes-plugin-holographic --base main --head liwangcc:feat/desktop-config-schema \
  --title "feat: configure search by meaning in the Desktop (config_schema.py)" --body-file $DOCS/posted/H1.md
```

4. 记录 PR 的 URL。插件 PR 的后续评审按 `RUNBOOK-HERMES.md` 第 8 节处理：Hermes 草拟回复交给用户；要改代码就停下来，交回 Claude Code。

**PR 正文**（英文，从下一行开始到本节末尾）：

---

The Hermes Desktop renders a memory provider's settings panel from a `config_schema.py` beside its `__init__.py`
(core's `plugins/memory/config_schema.py`, in the memory provider plugin guide). holographic has `get_config_schema()`
for `hermes memory setup`, which the web dashboard renders too, but no `config_schema.py`, so the Desktop shows no
settings for it. This adds one for search by meaning, so a Desktop user can turn it on and point it at a model without
editing `config.yaml`. Part of #HOLO-ISSUE.

- **`config_schema.py`**: `embeddings` and the ten `embedding_*` keys. `embeddings`, `embedding_url`,
  `embedding_model` and `embedding_key_env` are in the compact panel, the rest under "Search by meaning". A blank field
  is unset, so the plugin's own default applies; the placeholder shows it, and no default is written to `config.yaml`.
  `storage=provider`.
- **`read_config_fields` / `write_config_fields`** (`config_fields.py`, two forwarding methods on the provider): they
  read and write `plugins.hermes-memory-store` of the profile being configured, not the one the process runs, through
  the existing `save_config` (config lock, managed-mode refusal, atomic replace). A cleared field that is stored is
  written empty, which the plugin reads as unset, since the merging writer cannot drop a key; a blank field that was
  never stored is left out.
- **The key stays out of `config.yaml`.** It is still an environment variable named by `embedding_key_env`. A value
  that is not a variable name, or starts like a key (the checks `Embedder.unavailable()` already makes), is refused
  with a `ValueError`, which Hermes shows as a 400.
- Nothing changes on a Hermes without the panel: it never reads the file or calls the two methods, and the schema's
  import runs only when Hermes asks. `requires_hermes` unchanged; every other setting stays with `hermes memory setup`.

**Tests**: `tests/test_holographic_config_schema.py`, 5 cases, all failing on `main`.

- Hermes' own loader finds and loads the schema from where `hermes plugins install` puts the plugin.
- A save lands in that profile's `config.yaml`, keeps its other sections and keys, leaves the running profile alone,
  and a provider started on that profile runs search by meaning with exactly those settings.
- The panel reads only its own keys of that profile (`embeddings: on` reads as on), and a cleared field goes back to
  its default.
- A pasted key never reaches `config.yaml`.

**Checked** on Windows 11, Python 3.14, against Hermes `main` at `152fe189`:

- The new tests and `tests/test_holographic_save_config.py` pass, here and against the latest release, v0.23.2.
- Full suite: 3,698 passed, 16 skipped, 7 failed. The seven are in `tests/test_holographic_blas_threads.py` and fail
  the same way on `main` in this setup: numpy was on `PYTHONPATH`, which their subprocess does not inherit.
- `ruff check .` is clean, and `hermes plugins validate` passes.
- Through the functions behind core's panel routes (`GET` and `PUT /api/memory/providers/holographic/config?surface=declared`),
  with the plugin installed in a temp `HERMES_HOME`: a stored `embeddings: on` shows as on, and defaults show as
  placeholders. A save writes only what was filled in or cleared, and a pasted key is refused with `config.yaml`
  unchanged.
- `validate` lists the schema's imports of `plugins.memory.config_schema` under "private core imports". That is the
  module core's guide has `config_schema.py` import, but it is not in `plugin_api.json`. It is a warning, not a
  refusal.

I left the version and the CHANGELOG to you for the release. Not run on Linux or macOS; CI covers them.
