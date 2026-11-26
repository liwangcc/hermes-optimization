# 记忆召回赛马：统一裁判台

2026-11-23。按 `recall-race-brief.md`（Hermes 整理）开跑三条路线。题目只用官方探针的公开题集，不碰真实库。裁判台和基线由主窗口搭建，各路线不能改。

## 测的是什么形状

日常版：基座关向量，只走词法，事实带冻结关键词；侧车按 `cos(正文 + " " + tags)` 取最近的 1 条，满足 ≥ 0.55、不在基座结果里、基座不满 7 条、names_fit 通过时，追加在末尾；catalog 在 system prompt 里，每条事实一行 `#id=标签`，按 3000 approx-token 预算截断（`catalog_max_tokens`）。

**D0** 指现状日常版（基座 + 侧车），是所有路线对比的基线。**C0** 指全量 catalog。

## 题池

| 池 | 内容 | 用途 |
|---|---|---|
| dev | household dev（三语）+ synthetic_zh | 调参 |
| test | multi（8 种语言，即冻结关键词覆盖的语言）+ contrast 英俄中 + household test（三语） | 判定 |
| all7 | 两者合计 | 汇总 |

big 探针（路线 B 的大库）：把同一语言的几个库并成一个库，例如 household/en + multi/en + contrast_en，这样 catalog 超出预算。召回仍然用各自库里的结果。

## 基线（D0，`results/D0_store.json`、`results/D0_big.json`）

| 池 | 命中@5 | 噪声行 | 混淆行 | 侧车追加（其中是目标） | C0 token/轮 | B1 覆盖 |
|---|---:|---:|---:|---:|---:|---:|
| dev | 121/135 | 64 | 19 | 43（14） | 2307 | 15/18 |
| test | 304/325 | 130 | 34 | 63（20） | 1196 | 22/26 |
| all7 | 425/460 | 194 | 53 | 106（34） | 1547 | 37/44 |
| all7，big 探针 | 325/360 | 192 | 52 | 104（32） | 2976 | 16/44 |

只用基座时 all7 是 393/460、噪声 152：侧车多救回 32 题，同时多出 42 行噪声。household 的 catalog 自己就会超出预算，所以 C0 在单库上的 B1 也不是 100%。

## 命令（在本目录下运行）

```
python -B referee.py --selfcheck                    # 重算的混淆、噪声与探针自己的字段逐行一致
python -B referee.py SUB.jsonl --name A_xxx          # 调参：只打印 dev
python -B referee.py SUB.jsonl --name A_xxx --final  # 冻结后每个变体跑一次：写 results/A_xxx.json
python -B referee.py SUB.jsonl --name B_xxx --final --catalog-scope big   # catalog 在 big 探针上
python -B referee.py --write-d0 d0.jsonl [--catalog-scope big]           # D0 行加 C0 catalog，作为起点
```

提交是 JSONL，每行一个 `{"set","lang","qid","keys":[按输出顺序排的事实 key]}`；路线 B 再加 `"catalog": [[库, key, 标签], ...]` 和 `"catalog_static": true/false`（是否每轮都相同，也就是能不能进 prompt cache）。每次调用都记入 `runs.log`。

`pack.py` 给出所有输入：`load()` 返回 `stores`（事实、关键词、标签、五种向量 `c / ct / tc / k / label`，以及每个关键词各自的向量）和 `rows`（题面、基座结果 `base`、`worth_asking`、`names_refuse`、题向量）；`daily_append()` 就是侧车规则。标签（目标、混淆项）在 `pack/labels.json` 里，只给裁判用。

## 门禁和指标

四条门禁（对 D0）：不丢目标（前五逐个目标比）、噪声行不增、混淆行不增、McNemar p < 0.05 且救回多于丢失。另外标出 `cleaner`：什么都不丢，噪声和混淆至少一项减少（官方门禁的另一支）。

catalog 指标：每轮 token（approx_tokens 和 cl100k）；`effective_tokens` 按缓存读的价格比例 r 折算，r = 1 表示没有缓存，每轮现算的 catalog 一律按 r = 1 算；B1 覆盖率指没进召回结果的目标里，指针还在 catalog 里的比例；label rank 是这个目标的标签在本轮 catalog 里按 `cos(题, 标签)` 排第几，用来近似「模型看得出它相关」。

## 没有测、测不了的

- fact_store 的调用次数、往返耗时：要真模型在环里跑，这里不跑。
- label rank 只是相似度的代理，不等于模型真的会去 get。
- big 探针的召回沿用单库结果，大库里的召回只会更差，B1 那一侧偏乐观。
