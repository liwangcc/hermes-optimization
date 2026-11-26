# DeepSeek × 官方召回 / R2 动态指针：真模型行为对照协议 v1

冻结时间：2026-11-25；状态：付费调用前冻结。

## 决策问题

同一个千问 Token Plan 订阅内的 `deepseek-v4-pro`，面对相同问题时：

1. 官方纯净版自动召回不足时，模型会怎样回答、是否会主动查库；
2. Claude 的 R2_main（全文精挑 + 最多四条动态指针）是否让模型主动 `fact_store get` 正确补回；
3. 比较首轮查询、全轮查询、最终答案、无关查询、token/缓存与端到端耗时。

本实验只测合成公开题集，不读真实记忆库，不改生产配置，不开启日常版生产开关。

## 模型与路由（两臂完全相同）

- 请求模型：`deepseek-v4.1-flash-1017`（用户纠正；免费 live `/models` 已确认存在，HTTP 200）
- provider：现有 `qwen` custom provider / Token Plan
- endpoint：`<DEEPSEEK_ENDPOINT>/chat/completions`
- 凭据：现有 `HERMES_CUSTOM_QWEN_API_KEY`，只读取、不回显、不写入回执
- Chat Completions，`stream=true`、`stream_options.include_usage=true`
- `temperature=0`、`max_tokens=1024`、零自动重试
- 工具面按真实生产形状：官方臂给基础 `fact_store`（search/probe/related/reason/list 等只读动作，无 get）；R2 臂在同一 schema 上增加 `get`。不给写动作，防止评测改库。两臂都可自主补查，不提示必须查；另报 search/probe 绕路与 get 行为。
- 每逻辑会话最多 3 次 HTTP（初答 + 最多两轮工具回传）；第三轮仍 tool_calls 记 `no_final_answer_tool_budget`
- 并发 1（助手自身占同订阅一路，保守留余量）；两臂按题交替 A/B，避免时段漂移

## 固定输入

来源均为仓库冻结工件：

- 官方纯净版：`memory/threshold-calib/upstream-check/repro/rows/*_coff_on.jsonl`，git_sha `31de6eb5af2ae3366f1be32c3b847f338cbf2a7c`，emb on、rerank/check off、content-only、无 keywords 注入。
- R2：`memory/recall-race/round2/sub/R2_main.jsonl`，冻结规则与逐题指针。
- 题库/事实：`memory/recall-race/pack/{stores,labels}.json`。
- 旧 116 题身份清单：`<HERMES_HOME>/cache/scratch/recall-race-catalog-denoise/model_questions.json`，只用于复用已冻结题目身份，不沿用旧模型结果作本轮基线。

只保留题面原文与 targets 完全一致的旧 116 题；从中按固定 seed=20261125 分层抽 68 题：

- 官方漏目标、R2 仅指针覆盖：33 题（全部纳入，主测主动补查）
- 官方漏目标、R2 全文和指针都未覆盖：1 题（全部纳入，诚实失败边界）
- 官方漏目标、R2 已全文覆盖：10 题（测冗余查询）
- 官方/R2 都全文命中的干净控制：12 题
- 无目标题：12 题（测无关查询）

共 68 题 × 2 臂 = 136 个逻辑会话；理论最大 408 HTTP。首个真实探针只跑第 1 题 A 臂，完整审核后才继续。实际预计低于上限。

## 两臂唯一变量

A `official_pure`：官方纯净版该题 `keys` 作为全文召回；无静态 catalog、无动态指针。基础工具说明允许按词 search / 按实体 probe 等自主补查，但没有按 ID get。

B `r2_dynamic`：R2_main 该题 `keys` 作为全文召回；其 `catalog` 中未全文展示的项作为 `#id=label` 动态指针。无静态 catalog；同一基础工具面增加按已列 ID get。

其余系统提示、问题、事实库快照、模型参数、轮数、超时、评分完全相同。全文与指针 ID 必须互斥。官方臂不偷偷塞入旧 full30/static8 目录。工具 schema 的差异是生产机制本身：官方没有 #id 目录所以无 get，R2 有指针所以有 get；不是给 R2 额外强制调用提示。

## 指标

主指标（客观行为）：

- 官方漏目标题：是否 get 到官方漏掉的目标；是否取齐全部漏目标；首轮 get 与全轮 get 分开。
- R2 指针题：看到目标指针后是否 get 对应 ID；指针→正确 get 转化。
- R2 已全文命中题：是否冗余 get 已展示目标。
- 无目标题：是否发生任何 get、无关 get 数。
- 所有题：非目标 get、工具合同错误、轮数、终态。

次级答案指标：

- 复用 Unicode/CJK/西里尔兼容的 payload token 覆盖率与 any-hit；只对本题尚未全文展示的目标判分。
- any-hit 不是人工语义金标准；低覆盖/高覆盖与失败样本保留原文供审计。
- 另记录最终答案是否含目标特征词；不把“查到 ID”直接等同“答对”。

成本与性能：

- 每次 HTTP 单独保存 request SHA、响应 ID、返回 model、HTTP 状态、finish_reason、原始 usage、prompt/completion/cached/reasoning（缺失记 unknown）、响应头/首内容/完成耗时。
- 逻辑会话墙钟从首次发送到最终答案/终态；并行度固定 1。
- 缓存只报实测 cached_tokens 与占比，不用历史 Qwen 臂数字替代。

## 停止条件

- 任一 HTTP/auth/transport/429/超时、空回包、 malformed tool call：立即停止后续派发，保留已完成与失败原件，不自动重试。
- 第三轮仍请求工具是合法行为终态，不停止批次，但答案质量记不可用。
- 达到 408 HTTP 硬上限即停；剩余额度不自动扩测。
- 首条真实探针必须收到完整响应与 usage，且返回模型身份可核对；否则不进入批量。

## 真实感噪声/指令坑（第二阶段，付费前另行冻结）

用户补充：真实库里有些约定看起来像噪声；要测回答准确性、token，并给噪声设计坑。第一阶段先完成官方/R2 的直接事实问答；第二阶段在同一模型上增加合成任务型与对抗噪声题，不混入第一阶段分母：

- 任务型：用户不直接问约定，但完成任务必须遵守它（复用 round2/task_probe.json 的 24 条 must/ok 标注）。
- 指令样事实：把项目约定写成看似命令/偏好的句子，但仍标为 data；测模型是否把相关约定用于任务、是否被无关指令样事实带偏。
- 近似干扰：同实体/同主题的错误日期、旧约定、相反偏好；目标与干扰预先标注，不能看结果后改真值。
- 无需求任务：看似需要记忆、实际不需要任何私有事实；测无关 get/search 与答案掺噪。

第二阶段必须另建冻结清单、答案 rubric 与请求上限；不得用第一阶段 any-hit 冒充任务完成质量。

## 解释边界

- 这是同一 DeepSeek 模型下的召回呈现方式 A/B，不是 DeepSeek 与 Qwen 的模型能力排名。
- 旧 846 条 Qwen 回执只作历史参考，不与本轮 DeepSeek 直接相减。
- 68 题为分层样本；33 个指针题全纳入，其他层抽样，报告按层给分母，不冒充全 818 题总体率。
- 单轮对话；不证明多轮缓存、真实库、任务型消息或生产默认开启效果。
