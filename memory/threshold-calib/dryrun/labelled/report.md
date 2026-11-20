# Threshold calibration: stub-charbigram-256, labelled probes, keep 1

run: auto_n=None, below_trust_n=0, emb=stub-charbigram-256, endpoint=stub, est_texts=71, est_tokens=722, est_usd=0.0, fact_n=30, harness_version=tc-1, keep=1, min_trust=0.3, min_vectors_for_z=20, plugin_version=0.27.0, probe_source=labelled, probes_n=42, probes_skipped_n=1, recall_margin=1.0, role_prompt_n=0, seed=None, tool=threshold-calib, unsendable_n=0, vec_n=30

summary.json sha256: `cd22c74ca9ae6a7aa5980dd6517d63a8164953c7d39d066d673ebf4244fd9ad9`

probes: colloquial 10, crosslingual 8, direct 8, negative 6, paraphrase 10

- Every point is judged on the probes the sweep ran on: choosing the best of many points inflates significance. A value becomes a reference value only after a confirmation run of that single value on other probes (another --seed, or a labelled set).
- measured: the meaning channel alone (facts admitted on meaning, at most `keep` per probe); words, entities and names_fit are outside it.
- confusion: a labelled probe whose closest admitted fact is not a target (gated); extra: every non-target fact admitted on labelled probes (shown, not gated).

## zbar: RECALL_MARGIN: z >= sqrt(2 ln N) + value (upstream admission, value 1.0 is the default)

| value | recall@5 | pts | noise (net) | confusion (net) | extra | b | c | p | lost | gate | by category |
|---|---|---|---|---|---|---|---|---|---|---|---|
| -0.5 | 4/36 | +8.3 | 3 (+3) | 21 (+18) | 21 | 3 | 0 | 0.2500 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 4/8, paraphrase 0/10 |
| -0.25 | 4/36 | +8.3 | 3 (+3) | 15 (+12) | 15 | 3 | 0 | 0.2500 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 4/8, paraphrase 0/10 |
| 0.0 | 3/36 | +5.6 | 1 (+1) | 10 (+7) | 10 | 2 | 0 | 0.5000 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 3/8, paraphrase 0/10 |
| 0.25 | 3/36 | +5.6 | 1 (+1) | 8 (+5) | 8 | 2 | 0 | 0.5000 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 3/8, paraphrase 0/10 |
| 0.5 | 2/36 | +2.8 | 1 (+1) | 5 (+2) | 5 | 1 | 0 | 1.0000 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 2/8, paraphrase 0/10 |
| 0.75 | 2/36 | +2.8 | 1 (+1) | 3 (+0) | 3 | 1 | 0 | 1.0000 | 0 | fail: noise_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 2/8, paraphrase 0/10 |
| 1.0 | 1/36 | +0.0 | 0 (+0) | 3 (+0) | 3 | 0 | 0 | 1.0000 | 0 | default | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 1.25 | 1/36 | +0.0 | 0 (+0) | 0 (-3) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 1.5 | 1/36 | +0.0 | 0 (+0) | 0 (-3) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 1.75 | 1/36 | +0.0 | 0 (+0) | 0 (-3) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 2.0 | 0/36 | -2.8 | 0 (+0) | 0 (-3) | 0 | 0 | 1 | 1.0000 | 1 | fail: no_target_lost,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 0/8, paraphrase 0/10 |

## zbar_floor: embedding_min_score: cosine >= value AND the default z_bar (upstream optional floor, unset by default)

| value | recall@5 | pts | noise (net) | confusion (net) | extra | b | c | p | lost | gate | by category |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.089 | 1/36 | +0.0 | 0 (+0) | 3 (+0) | 3 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.109 | 1/36 | +0.0 | 0 (+0) | 3 (+0) | 3 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.117 | 1/36 | +0.0 | 0 (+0) | 3 (+0) | 3 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.124 | 1/36 | +0.0 | 0 (+0) | 3 (+0) | 3 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.139 | 1/36 | +0.0 | 0 (+0) | 3 (+0) | 3 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.151 | 1/36 | +0.0 | 0 (+0) | 3 (+0) | 3 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.182 | 1/36 | +0.0 | 0 (+0) | 3 (+0) | 3 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.218 | 1/36 | +0.0 | 0 (+0) | 3 (+0) | 3 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.307 | 1/36 | +0.0 | 0 (+0) | 3 (+0) | 3 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.377 | 1/36 | +0.0 | 0 (+0) | 1 (-2) | 1 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.466 | 0/36 | -2.8 | 0 (+0) | 1 (-2) | 1 | 0 | 1 | 1.0000 | 1 | fail: no_target_lost,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 0/8, paraphrase 0/10 |

## floor: experimental: cosine >= value alone admits, z_bar is not consulted (KG-1 admission_floor.diff)

> floor is an experimental admission mode, not an upstream default and not proposed as one; its values do not carry over between models.

| value | recall@5 | pts | noise (net) | confusion (net) | extra | b | c | p | lost | gate | by category |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.089 | 4/36 | +8.3 | 5 (+5) | 32 (+29) | 32 | 3 | 0 | 0.2500 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 4/8, paraphrase 0/10 |
| 0.109 | 4/36 | +8.3 | 3 (+3) | 31 (+28) | 31 | 3 | 0 | 0.2500 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 4/8, paraphrase 0/10 |
| 0.117 | 4/36 | +8.3 | 2 (+2) | 28 (+25) | 28 | 3 | 0 | 0.2500 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 4/8, paraphrase 0/10 |
| 0.124 | 4/36 | +8.3 | 1 (+1) | 24 (+21) | 24 | 3 | 0 | 0.2500 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 4/8, paraphrase 0/10 |
| 0.139 | 3/36 | +5.6 | 1 (+1) | 21 (+18) | 21 | 2 | 0 | 0.5000 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 3/8, paraphrase 0/10 |
| 0.151 | 3/36 | +5.6 | 1 (+1) | 17 (+14) | 17 | 2 | 0 | 0.5000 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 3/8, paraphrase 0/10 |
| 0.182 | 2/36 | +2.8 | 1 (+1) | 14 (+11) | 14 | 1 | 0 | 1.0000 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 2/8, paraphrase 0/10 |
| 0.218 | 2/36 | +2.8 | 1 (+1) | 10 (+7) | 10 | 1 | 0 | 1.0000 | 0 | fail: noise_not_higher,confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 2/8, paraphrase 0/10 |
| 0.307 | 1/36 | +0.0 | 0 (+0) | 8 (+5) | 8 | 0 | 0 | 1.0000 | 0 | fail: confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.377 | 1/36 | +0.0 | 0 (+0) | 4 (+1) | 4 | 0 | 0 | 1.0000 | 0 | fail: confusion_not_higher,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 1/8, paraphrase 0/10 |
| 0.466 | 0/36 | -2.8 | 0 (+0) | 1 (-2) | 1 | 0 | 1 | 1.0000 | 1 | fail: no_target_lost,mcnemar_p_below_0.05 | colloquial 0/10, crosslingual 0/8, direct 0/8, paraphrase 0/10 |

## Points that pass the gate (exploratory)

- zbar: none
- zbar_floor: none
- floor: none
