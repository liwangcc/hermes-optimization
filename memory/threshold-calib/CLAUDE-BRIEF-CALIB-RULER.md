# Claude 任务书：每模型标定尺子（公开测试集 ＋ 方法）

> Hermes 写需求与验收，Claude 做设计/实现。落未提交状态给用户过目，不自行 commit/push、不自行无头派发。

## 1. 这是什么 / 为什么

上游插件库 `itpartypattaya/hermes-plugin-holographic` 的 **#110** 已关闭，维护者在关闭评论里明确邀请：
**「publish in your own repo, we'll gladly link it」**——把每模型标定的测试集＋方法发在自己仓库，官方愿意挂链接。

本任务就是做这把「尺子」。**关键区分**：不是去找一个通吃所有嵌入模型的通用阈值（那常无解），而是给一套
**「在自己的库上跑、画曲线、冻阈值」的可复现标定测试集 ＋ 方法**。这正是上游邀请的方向，也是自己公开仓库
`liwangcc/hermes-optimization` 该放的东西。

## 2. 仓库与现有家底（先读懂，别重造轮子）

- 仓库根：`C:/aiprojects/hermes-optimization`（公开，MIT）。
- 标定脚本已在 `memory/threshold-calib/`，先读再扩展：
  - `calib_model_tau.py`（每模型 tau 标定）、`calib_cloud_floor.py`（云模型 floor）、
    `calib_gate.py`（门禁）、`calib_replay.py`（回放）、`calib_probes.py`、`calib_consensus.py`、
    `calib_margin_gate.py`、`calib_verify_gate.py` 等。
  - 冻结样例：`cloud-floor-freeze.json`、`cloud-floor-models.json`、`cloud-floor-results.json`、`consensus-results.json`。
- **门禁口径（`calib_gate.py:108`，务必照此，别改成逐行）**：
  ```python
  "no_target_lost": not lost,                 # 零丢失
  "noise_not_higher": noise["point"] <= noise["base"],   # 噪声净总数不增
  "confusion_not_higher": ...,                # 混淆净总数不增
  # ＋ McNemar p < 0.05
  ```
  是**净总数比较**，不是逐行集合差。
- **锚点校准（anchor calibration）**：跨模型阈值迁移靠 cosine floor 锚点，不是把一个模型的阈值直接搬给另一个。
  方法文档要把这条讲清楚（嵌入模型几何不同，阈值不可直接迁移）。
- **上游测试集格式**：七集（multi 18 语、contrast 英俄中、household dev/test）＋ `synthetic_zh`。
  镜像其 `FACTS / QUERIES / CHITCHAT / self_check` 形状；关键词约束 3–8 个、每个 ≤40 字符、无逗号。

## 3. 要交付的（四件）

1. **公开可复现的每模型标定测试集**：合成、多语多类、留出目标、每条事实带关键词。陌生人建 venv 装依赖即可跑。
2. **标定方法文档**：怎么在自己库上画 `threshold vs recall / noise / precision` 曲线；怎么用锚点校准 ＋ McNemar 门禁
   冻一个阈值（冻结值协议：冻什么、怎么冻、怎么验、怎么随模型/库变化重冻）。
3. **可跑 harness**：镜像上游集格式，把新集注册进工具链**每一处**按集名分派的地方——探针 runner ＋ `--set` 分发，
   以及 gate 的行形状白名单（漏注册 gate 会报 `unknown row shape — unsupported set`）。
4. **曲线 ＋ 冻结协议的可复现输出**（JSON ＋ 图），数字按基线分栏。

## 4. 红线（违反即停）

- **只用合成数据**。绝不读/写真实记忆库 `<HERMES_HOME>/memory_store.db`，不改生产配置、不开日常版生产开关。
  评测只动副本（`mode=ro` ＋ backup）。
- **不自行 commit/push**；新增公开内容落工作区未提交状态给用户过目，提交与推送各等一次明确指令。
- 门禁口径用**净总数**，不逐行；不同题集/版本的数字**不互减**，口径显式标注。
- **先提交接线、再跑会往行里戳 `git_sha` 的探针**：未提交工作树戳成 `<sha>-dirty`，gate 拒 dirty 行。
- 自动锚点评分是透明启发式，保留原文供人工复核，**不得冒充语义金标准**。
- 公开前扫公网 IP / 私有路径（`<HERMES_HOME>`、`<USER_HOME>`）/ 个人信息 / 凭据；合成集确认零真实文本。

## 5. 验收（Hermes 会逐条核）

- 陌生人按 README 建 venv、只装仓库声明的依赖，能跑通全量（不缺 `pytest-asyncio` 这类测试插件）。
- gate 在合成集上**用上游自己的工具原生跑通**（收敛 ＋ 原生接受 ＝ 信誉门槛），复现独立 harness 的数字。
- 曲线 ＋ 冻结协议可复算；行/混淆定义沿用上游口径，无现成标注处的泛化在文档写明。
- 交回：测试集 ＋ 方法文档 ＋ harness ＋ 复现输出 ＋ 环境命令输出 ＋ 逐步成败 ＋ 改过的设置。
- 报告固定题集 ＋ 标准名 ＋ 数据指纹 ＋ 逐题没命中清单（不只报百分比）。

## 6. 建议起步

1. 读 `memory/threshold-calib/calib_model_tau.py`、`calib_cloud_floor.py`、`calib_gate.py`、`calib_replay.py`，
   弄清现有标定/门禁/回放怎么跑。
2. 读上游七集 ＋ `synthetic_zh` 的集模块形状（在 `vendor/` 或上游克隆里），照模板生成新集，别手抄。
3. 先接线（注册新集进 runner/--set/gate 白名单）→ 提交 → 再跑探针戳干净 `git_sha`。
4. 画曲线、跑锚点校准、按门禁冻阈值，产出可复现 JSON＋图。
5. 写方法文档（含「阈值不可跨模型直接搬、靠锚点」这条），落未提交状态。