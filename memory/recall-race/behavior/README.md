# catalog 补漏行为评测（真模型在环）

2026-11-24 Hermes 搭建。**尚未运行模型臂——花费接口额度，须用户批准。** 冻结与干跑已完成。

## 测什么

第一轮赛马的 B1 只量了「漏掉的目标指针看得见」；这里量「模型看到指针后会不会 fact_store get、get 对没有、答对没有」。

- 形状用**生产配置实际值**：semantic_total_cap=9、catalog_max_tokens=3500（赛马用的是插件默认 7/3000）。
  生产形状下漏目标题 43 道（cap7 口径是 44，cap9 多救回 1），对照题 43 道（D0 前五全中，按 set×lang 与漏题分布 1:1 匹配，种子 20261124）。
- 三个臂：catalog_label_tokens 30 / 12 / 8，全部静态、同一预算。单库 scope（与真实库形状一致：真实库 92 条全列不截断）。
- 每题注入 D0 的真实召回输出（生产格式 `- #id [trust] 正文`）+ 生产 routing 块 + catalog 块（头部逐字取自已安装插件）。
- 工具面只给 fact_store get（catalog 指定的读路径），隔离 catalog 通道；temperature 0，最多 3 轮工具往返，4 并发，断点续跑。
- 端点/模型：<HERMES_HOME>/config.yaml 的 qwen Token Plan（qwen4-max-preview），密钥 HERMES_CUSTOM_QWEN_API_KEY（<HERMES_HOME>/.env）。
  预估 258 次对话（约 500 次请求）、~1.5M 输入 token。

## 判分两层

1. **客观主指标（get 行为）**：漏题 got_missed_target（取到漏掉的目标 id）、nontarget_gets；对照题 redundant_target_get（已注入还重复取）、nontarget_gets（被无关指针诱导）。
2. **次指标（答案质量，透明启发式）**：payload = 目标事实 token − 问句回声 − 停用词（en/ru/zh），
   payload_score = 答案覆盖 payload 的比例（短正确答案会偏低），payload_any_hit = 至少命中一个特征词。
   已离线验证 en/ru/zh 全文回声=1.0、短正确答案 any_hit=True、错误/空答案=0。多目标题只对漏掉的目标判分。
   聚合时另抽查低分但 get 成功的样本校准。

## 命令

```
python -B behavior/freeze.py            # 重建冻结集（无 API）
python -B behavior/run_eval.py --dry-run
python -B behavior/run_eval.py --limit 2   # 冒烟：2 题 x 3 臂（批准后）
python -B behavior/run_eval.py             # 全量，可断点续跑
python -B behavior/run_eval.py --aggregate
```

冻结集与输出在 <HERMES_HOME>/cache/scratch/recall-race-behavior/（questions.json / runs.jsonl / aggregate.json）。
代码只读合成官方 pack，不碰真实库；catalog 逻辑从已安装插件 AST 逐字提取（与生产一致）。

## 已知限制

- 工具面只有 get，模型不能 search/probe 绕路——测的是 catalog 通道本身，不是完整 fact_store 表面。
- 官方合成事实 trust 全相等，测不了 trust 排序效应。
- 答案启发式对短答案偏严，跨臂比较用同一判分器，偏差一致；主结论以 get 行为为准。
