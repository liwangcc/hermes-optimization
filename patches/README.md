# 补丁清单（日常版 2026-11）

这里放的是**本机日常版**相对两个上游固定基线的完整源码补丁。补丁只含代码、测试、文档和本地化文案；
不含模型权重、数据库、个人配置、凭据、日志、缓存或运行环境。

> 不要和 [`../docs/upstream-memory-review/patches/`](../docs/upstream-memory-review/patches/) 混用：
> 那里是上游投稿用的拆分补丁，对应的基线与这里不同。装日常版只用本目录的三个补丁。

Holographic 的两份补丁不是同一基线：本目录是日常版 0.30.0（`ed73195f`）→ `4cbd5b7`，含简体中文标签；
上游 HOLO-1 投稿补丁基于插件 main 0.30.1（`76689f9`），核心 diff 相同但不含中文标签。不要互相替换；
上游 PR 需要中文时，从本目录补丁取 `config_schema.py` 的 `_ZH` 段。

## 固定基线

| 项目 | 上游 | 基线提交 | 终点提交 | 补丁 | 规模 |
|---|---|---|---|---|---|
| Hermes Agent | https://github.com/NousResearch/hermes-agent | `40d1e95f37e409f9f618f32c170661c66b86a4f4`（`v0.23.2+canary.20261117T064624Z`） | `eccd37ae5217e1268cccb22ca81889b7c7edbbc8`（+6 commits） | `hermes-agent-40d1e95f-eccd37ae.patch` | 106 files, +7004 / -157 |
| Holographic | https://github.com/itpartypattaya/hermes-plugin-holographic | `ed73195df846913d34f4aea54335718e56d841fb`（0.30.0） | `4cbd5b79a7134d7c6f44c25654f1ad4f541e8759`（+2 commits） | `holographic-ed73195f-4cbd5b79.patch` | 5 files, +262 |
| Hermes Agent 测试账本 | 同上 | 应用完上面的 Hermes 补丁之后 | `tests/hermes_cli/serve_handler_ledger.json` 重新生成 | `hermes-agent-ledger-fix.patch` | 1 file, +3 / -1 |

`hermes-agent-ledger-fix.patch` 是必要的：日常版 HEAD 自己新增了
`GET /api/memory/actions/status` 和 `POST /api/memory/providers/{name}/connect`
两个 handler，但没有重新生成 handler 账本，导致 `tests/hermes_cli/test_serve_handler_ledger.py`
在干净检出上失败。这个补丁只重新生成账本，不改任何业务代码。

## 校验和

```text
5ab1e45258dd01d2a7d6b3cc56f4fb2f7f2f129a91011765aeb1d37d1557b8e1  hermes-agent-40d1e95f-eccd37ae.patch
30410b0eb39cdc1539f345fc0e0c2baa6732aaa636a188f5ec10ba599719540d  hermes-agent-ledger-fix.patch
c23b9673ee64e9eda2722cb877a2a8b2ff3d296354ca6f527eb045fe42b439a0  holographic-ed73195f-4cbd5b79.patch
```

## 应用顺序

在固定基线检出上按顺序应用；每个补丁都先用 `--check` 验证：

```bash
git apply --check patches/hermes-agent-40d1e95f-eccd37ae.patch
git apply         patches/hermes-agent-40d1e95f-eccd37ae.patch
git apply --check patches/hermes-agent-ledger-fix.patch
git apply         patches/hermes-agent-ledger-fix.patch
```

Holographic：

```bash
git apply --check patches/holographic-ed73195f-4cbd5b79.patch
git apply         patches/holographic-ed73195f-4cbd5b79.patch
```

补丁由 `git diff --binary --full-index <base> <head>` 生成，换行符与文件模式随补丁保留；
用 `git apply`（不是 `patch`）应用。完整安装、构建、启用、验证和回滚步骤见
[`../INSTALL.md`](../INSTALL.md)。

## 许可与署名

- Hermes Agent：MIT，Copyright (c) 2025 Nous Research。
- Holographic：MIT，Copyright (c) 2025 Nous Research；现由 itpartypattaya 维护。
- 本仓库原创部分：MIT，见 [`../LICENSE`](../LICENSE)；完整致谢见 [`../NOTICE`](../NOTICE)。

补丁是上述 MIT 项目的修改版，分发时保留原版权与许可声明。
