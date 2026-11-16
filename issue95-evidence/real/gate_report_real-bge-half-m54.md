# KG-1 gate report — real · bge-m3 · half coverage

run: set=kg1_real, group=real, emb=bge-m3, coverage=half, seed=20261116, split=all, git_sha=114cf5f, scale=none, endpoint=ep-e008d95f4681, core=shim, stemmer=snowballstemmer-3.1.1, harness_version=kg1-1, fact_n=54, kw_n=15, tags_sha=2f65dd4db403b71f

**Gate (ZC->ZK, keywords in the vector text under the upstream admission): DOES NOT PASS**

## Cells

| cell | labelled | hit@5 | target anywhere | confused | noise | by meaning (rows/facts) | search hit | vectors |
|---|---|---|---|---|---|---|---|---|
| L0 | 44 | 30 | 30 | 31 | 3/10 (no_answer_ext 3) | 0/0 | 40 | 0/54 |
| ZC | 44 | 34 | 34 | 31 | 3/10 (no_answer_ext 3) | 2/2 | 41 | 54/54 |
| ZK | 44 | 35 | 35 | 31 | 3/10 (no_answer_ext 3) | 3/3 | 41 | 54/54 |
| FC | 44 | 36 | 36 | 32 | 3/10 (no_answer_ext 3) | 19/19 | 41 | 54/54 |
| FK | 44 | 37 | 37 | 32 | 3/10 (no_answer_ext 3) | 20/20 | 41 | 54/54 |

## What the words already answer (L0, hit@5 per category)

| category | n | hit@5 | fraction |
|---|---|---|---|
| colloquial | 14 | 11 | 0.786 |
| crosslingual | 8 | 2 | 0.25 |
| direct | 8 | 8 | 1.0 |
| paraphrase | 14 | 9 | 0.643 |

## Pairs

### L0->ZC — one factor: embeddings (supplementary)

- hit@5 30/44 -> 34/44 (+9.1 points; +5 points reached: yes, shown only)
- rescued b=4, lost c=0, exact McNemar p=0.1250 -> FAIL (p < 0.05 and b > c)
- on the 14 questions L0 misses: 0 -> 4, b=4, c=0, p=0.1250
- guard paired: PASS (unpaired 0)
- guard noise not higher: PASS (3 -> 3, added 0, removed 0, net +0)
- guard confusion not higher: PASS (31 -> 31, added 0, removed 0, net +0)
- lost targets in the top five (0): -
- gained targets in the top five (4): B5:114, zh; C1:186, zh; C7:214, zh; D10:193, zh
- => DOES NOT PASS

### ZC->ZK — one factor: vector_variant (gate)

- hit@5 34/44 -> 35/44 (+2.3 points; +5 points reached: no, shown only)
- rescued b=1, lost c=0, exact McNemar p=1.0000 -> FAIL (p < 0.05 and b > c)
- on the 14 questions L0 misses: 4 -> 5, b=1, c=0, p=1.0000
- guard paired: PASS (unpaired 0)
- guard noise not higher: PASS (3 -> 3, added 0, removed 0, net +0)
- guard confusion not higher: PASS (31 -> 31, added 0, removed 0, net +0)
- lost targets in the top five (0): -
- gained targets in the top five (1): B14:183, zh
- => DOES NOT PASS

### ZC->FC — one factor: admission (supplementary)

- hit@5 34/44 -> 36/44 (+4.5 points; +5 points reached: no, shown only)
- rescued b=2, lost c=0, exact McNemar p=0.5000 -> FAIL (p < 0.05 and b > c)
- on the 14 questions L0 misses: 4 -> 6, b=2, c=0, p=0.5000
- guard paired: PASS (unpaired 0)
- guard noise not higher: PASS (3 -> 3, added 0, removed 0, net +0)
- guard confusion not higher: FAIL (31 -> 32, added 1, removed 0, net +1)
- lost targets in the top five (0): -
- gained targets in the top five (2): B14:183, zh; D8:181, zh
- => DOES NOT PASS
- caveat: floor cell: 0.55 is a local experimental admission rule, not proposed upstream, and is not calibrated across models (upstream calibration: a paraphrase scores 0.38-0.66 on text-embedding-3-small against 0.68-0.84 on gemini-embedding-001)

### FC->FK — one factor: vector_variant (supplementary)

- hit@5 36/44 -> 37/44 (+2.3 points; +5 points reached: no, shown only)
- rescued b=1, lost c=0, exact McNemar p=1.0000 -> FAIL (p < 0.05 and b > c)
- on the 14 questions L0 misses: 6 -> 7, b=1, c=0, p=1.0000
- guard paired: PASS (unpaired 0)
- guard noise not higher: PASS (3 -> 3, added 0, removed 0, net +0)
- guard confusion not higher: PASS (32 -> 32, added 0, removed 0, net +0)
- lost targets in the top five (0): -
- gained targets in the top five (1): C5:215, zh
- => DOES NOT PASS
- caveat: floor cell: 0.55 is a local experimental admission rule, not proposed upstream, and is not calibrated across models (upstream calibration: a paraphrase scores 0.38-0.66 on text-embedding-3-small against 0.68-0.84 on gemini-embedding-001)

### ZK->FK — one factor: admission (supplementary)

- hit@5 35/44 -> 37/44 (+4.5 points; +5 points reached: no, shown only)
- rescued b=2, lost c=0, exact McNemar p=0.5000 -> FAIL (p < 0.05 and b > c)
- on the 14 questions L0 misses: 5 -> 7, b=2, c=0, p=0.5000
- guard paired: PASS (unpaired 0)
- guard noise not higher: PASS (3 -> 3, added 0, removed 0, net +0)
- guard confusion not higher: FAIL (31 -> 32, added 1, removed 0, net +1)
- lost targets in the top five (0): -
- gained targets in the top five (2): C5:215, zh; D8:181, zh
- => DOES NOT PASS
- caveat: floor cell: 0.55 is a local experimental admission rule, not proposed upstream, and is not calibrated across models (upstream calibration: a paraphrase scores 0.38-0.66 on text-embedding-3-small against 0.68-0.84 on gemini-embedding-001)
