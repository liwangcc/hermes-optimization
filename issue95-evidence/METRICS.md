# KG-1 metrics glossary / 指标词典

Bilingual key for the rows and gate reports in this package. hit@5 is recall@5.

| term | 中文 | meaning |
|---|---|---|
| hit@5 / recall@5 | 召回率@5 | target fact appears in the returned top-5 (0/1 per query, averaged). 目标事实进前5名。 |
| labelled | 有答案题 | queries with a target (denominator); chit/no-answer rows counted separately as noise. |
| b (rescued) | 救回 | left arm missed top-5, right arm hit. 左格没中、右格中了。 |
| c (lost) | 丢失 | left arm hit, right arm missed. 左格中了、右格反而没中。 |
| exact McNemar p | 精确McNemar p值 | significance of b vs c; p<0.05 required. b=1,c=0 → p=1.0 (too few to attribute). |
| gate G1 | 门禁 | pass = p<0.05 AND b>c AND noise net≤0 AND confusion net≤0. 任一不满足即 FAIL。 |
| guard | 护栏 | right-vs-left noise added−removed ≤0; confusion added−removed ≤0. |
| noise | 噪声 | chit/no-answer rows that still got facts back (should stay silent). 本该闭嘴却返回。 |
| confused | 混淆 | labelled rows returning a non-target fact. 答非所问。 |
| by_meaning | 语义准入 | facts admitted purely by vector similarity (not lexical). 靠向量救进来的条数。 |
| full / half | 全覆盖/半覆盖 | keywords on all facts vs a fixed-seed half (queries unchanged). 关键词覆盖全部/一半事实。 |
| kw_n | 带关键词事实数 | facts carrying keywords in that run. |

## Cells / 五格（each adjacent pair changes ONE factor）

| cell | embeddings | vector text | admission | role |
|---|---|---|---|---|
| L0 | off | — | lexical only | baseline 词法基线 |
| ZC | on | content | upstream z_bar (margin 1.0) | +embeddings |
| ZK | on | content+keywords | upstream z_bar (margin 1.0) | **main pair ZC→ZK: keywords-in-vector** |
| FC | on | content | local floor cos≥0.55 | +admission change (supplementary) |
| FK | on | content+keywords | local floor cos≥0.55 | floor + keywords (supplementary) |

z_bar = statistical-outlier admission: similarity must exceed the store mean by ~sqrt(2 ln N)+1 standard deviations (strict, precision-first).
floor = absolute cos≥0.55 (loose; NOT calibrated across models; local experiment, not proposed upstream).