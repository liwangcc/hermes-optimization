# KG-1 gate report — synthetic · bge-m3 · full coverage

run: set=kg1_synthetic, group=synthetic, emb=bge-m3, coverage=full, seed=20261116, split=all, git_sha=114cf5f, scale=none, endpoint=ep-e008d95f4681, core=shim, stemmer=snowballstemmer-3.1.1, harness_version=kg1-1, fact_n=30, kw_n=30, tags_sha=1f9a232431047b58

**Gate (ZC->ZK, keywords in the vector text under the upstream admission): DOES NOT PASS**

## Cells

| cell | labelled | hit@5 | target anywhere | confused | noise | by meaning (rows/facts) | search hit | vectors |
|---|---|---|---|---|---|---|---|---|
| L0 | 36 | 29 | 29 | 10 | 3/12 (no_answer_ext 3) | 0/0 | 33 | 0/30 |
| ZC | 36 | 29 | 29 | 10 | 3/12 (no_answer_ext 3) | 0/0 | 33 | 30/30 |
| ZK | 36 | 30 | 30 | 10 | 3/12 (no_answer_ext 3) | 1/1 | 33 | 30/30 |
| FC | 36 | 31 | 31 | 25 | 5/12 (no_answer_ext 5) | 26/26 | 34 | 30/30 |
| FK | 36 | 33 | 33 | 21 | 4/12 (no_answer_ext 4) | 22/22 | 34 | 30/30 |

## What the words already answer (L0, hit@5 per category)

| category | n | hit@5 | fraction |
|---|---|---|---|
| colloquial | 10 | 6 | 0.6 |
| crosslingual | 8 | 8 | 1.0 |
| direct | 8 | 8 | 1.0 |
| paraphrase | 10 | 7 | 0.7 |

## Pairs

### L0->ZC — one factor: embeddings (supplementary)

- hit@5 29/36 -> 29/36 (+0.0 points; +5 points reached: no, shown only)
- rescued b=0, lost c=0, exact McNemar p=1.0000 -> FAIL (p < 0.05 and b > c)
- on the 7 questions L0 misses: 0 -> 0, b=0, c=0, p=1.0000
- guard paired: PASS (unpaired 0)
- guard noise not higher: PASS (3 -> 3, added 0, removed 0, net +0)
- guard confusion not higher: PASS (10 -> 10, added 0, removed 0, net +0)
- lost targets in the top five (0): -
- gained targets in the top five (0): -
- => DOES NOT PASS

### ZC->ZK — one factor: vector_variant (gate)

- hit@5 29/36 -> 30/36 (+2.8 points; +5 points reached: no, shown only)
- rescued b=1, lost c=0, exact McNemar p=1.0000 -> FAIL (p < 0.05 and b > c)
- on the 7 questions L0 misses: 0 -> 1, b=1, c=0, p=1.0000
- guard paired: PASS (unpaired 0)
- guard noise not higher: PASS (3 -> 3, added 0, removed 0, net +0)
- guard confusion not higher: PASS (10 -> 10, added 0, removed 0, net +0)
- lost targets in the top five (0): -
- gained targets in the top five (1): C10:19, zh
- => DOES NOT PASS

### ZC->FC — one factor: admission (supplementary)

- hit@5 29/36 -> 31/36 (+5.6 points; +5 points reached: yes, shown only)
- rescued b=2, lost c=0, exact McNemar p=0.5000 -> FAIL (p < 0.05 and b > c)
- on the 7 questions L0 misses: 0 -> 2, b=2, c=0, p=0.5000
- guard paired: PASS (unpaired 0)
- guard noise not higher: FAIL (3 -> 5, added 2, removed 0, net +2)
- guard confusion not higher: FAIL (10 -> 25, added 15, removed 0, net +15)
- lost targets in the top five (0): -
- gained targets in the top five (2): C1:1, zh; C10:19, zh
- => DOES NOT PASS
- caveat: floor cell: 0.55 is a local experimental admission rule, not proposed upstream, and is not calibrated across models (upstream calibration: a paraphrase scores 0.38-0.66 on text-embedding-3-small against 0.68-0.84 on gemini-embedding-001)

### FC->FK — one factor: vector_variant (supplementary)

- hit@5 31/36 -> 33/36 (+5.6 points; +5 points reached: yes, shown only)
- rescued b=2, lost c=0, exact McNemar p=0.5000 -> FAIL (p < 0.05 and b > c)
- on the 7 questions L0 misses: 2 -> 4, b=2, c=0, p=0.5000
- guard paired: PASS (unpaired 0)
- guard noise not higher: PASS (5 -> 4, added 0, removed 1, net -1)
- guard confusion not higher: PASS (25 -> 21, added 0, removed 4, net -4)
- lost targets in the top five (0): -
- gained targets in the top five (2): C5:5, zh; P7:8, zh
- => DOES NOT PASS
- caveat: floor cell: 0.55 is a local experimental admission rule, not proposed upstream, and is not calibrated across models (upstream calibration: a paraphrase scores 0.38-0.66 on text-embedding-3-small against 0.68-0.84 on gemini-embedding-001)

### ZK->FK — one factor: admission (supplementary)

- hit@5 30/36 -> 33/36 (+8.3 points; +5 points reached: yes, shown only)
- rescued b=3, lost c=0, exact McNemar p=0.2500 -> FAIL (p < 0.05 and b > c)
- on the 7 questions L0 misses: 1 -> 4, b=3, c=0, p=0.2500
- guard paired: PASS (unpaired 0)
- guard noise not higher: FAIL (3 -> 4, added 1, removed 0, net +1)
- guard confusion not higher: FAIL (10 -> 21, added 11, removed 0, net +11)
- lost targets in the top five (0): -
- gained targets in the top five (3): C1:1, zh; C5:5, zh; P7:8, zh
- => DOES NOT PASS
- caveat: floor cell: 0.55 is a local experimental admission rule, not proposed upstream, and is not calibrated across models (upstream calibration: a paraphrase scores 0.38-0.66 on text-embedding-3-small against 0.68-0.84 on gemini-embedding-001)
