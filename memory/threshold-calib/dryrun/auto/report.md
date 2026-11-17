# Threshold calibration: stub-charbigram-256, auto probes, keep 1

run: auto_n=40, below_trust_n=0, emb=stub-charbigram-256, endpoint=stub, est_texts=64, est_tokens=703, est_usd=0.0, fact_n=30, harness_version=tc-1, keep=1, min_trust=0.3, min_vectors_for_z=20, plugin_version=0.27.0, probe_source=auto, probes_n=34, probes_skipped_n=0, recall_margin=1.0, role_prompt_n=0, seed=20261117, tool=threshold-calib, unsendable_n=0, vec_n=30

summary.json sha256: `7fb3d67e547dc601bfa234be233cb675ab2daa968dcd9f86fd947598859929d5`

probes: chit 10, fragment 18, holdout 6

- Every point is judged on the probes the sweep ran on: choosing the best of many points inflates significance. A value becomes a reference value only after a confirmation run of that single value on other probes (another --seed, or a labelled set).
- auto probes are the middle half of a stored fact: they share words with their target, so recall here is optimistic for real paraphrases. Noise (holdout, chit) and confusion are the dependable side.
- measured: the meaning channel alone (facts admitted on meaning, at most `keep` per probe); words, entities and names_fit are outside it.
- confusion: a labelled probe whose closest admitted fact is not a target (gated); extra: every non-target fact admitted on labelled probes (shown, not gated).

## zbar: RECALL_MARGIN: z >= sqrt(2 ln N) + value (upstream admission, value 1.0 is the default)

| value | recall@5 | pts | noise (net) | confusion (net) | extra | b | c | p | lost | gate | by category |
|---|---|---|---|---|---|---|---|---|---|---|---|
| -0.5 | 18/18 | +0.0 | 7 (+7) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: noise_not_higher,mcnemar_p_below_0.05 | fragment 18/18 |
| -0.25 | 18/18 | +0.0 | 4 (+4) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: noise_not_higher,mcnemar_p_below_0.05 | fragment 18/18 |
| 0.0 | 18/18 | +0.0 | 1 (+1) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: noise_not_higher,mcnemar_p_below_0.05 | fragment 18/18 |
| 0.25 | 18/18 | +0.0 | 1 (+1) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: noise_not_higher,mcnemar_p_below_0.05 | fragment 18/18 |
| 0.5 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | fragment 18/18 |
| 0.75 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | fragment 18/18 |
| 1.0 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | default | fragment 18/18 |
| 1.25 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | fragment 18/18 |
| 1.5 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | fragment 18/18 |
| 1.75 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | fragment 18/18 |
| 2.0 | 13/18 | -27.8 | 0 (+0) | 0 (+0) | 0 | 0 | 5 | 0.0625 | 5 | fail: no_target_lost,mcnemar_p_below_0.05 | fragment 13/18 |

## zbar_floor: embedding_min_score: cosine >= value AND the default z_bar (upstream optional floor, unset by default)

| value | recall@5 | pts | noise (net) | confusion (net) | extra | b | c | p | lost | gate | by category |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.083 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | fragment 18/18 |
| 0.107 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | fragment 18/18 |
| 0.14 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | fragment 18/18 |
| 0.216 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | fragment 18/18 |
| 0.277 | 18/18 | +0.0 | 0 (+0) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: mcnemar_p_below_0.05 | fragment 18/18 |
| 0.576 | 17/18 | -5.6 | 0 (+0) | 0 (+0) | 0 | 0 | 1 | 1.0000 | 1 | fail: no_target_lost,mcnemar_p_below_0.05 | fragment 17/18 |
| 0.675 | 14/18 | -22.2 | 0 (+0) | 0 (+0) | 0 | 0 | 4 | 0.1250 | 4 | fail: no_target_lost,mcnemar_p_below_0.05 | fragment 14/18 |
| 0.709 | 10/18 | -44.4 | 0 (+0) | 0 (+0) | 0 | 0 | 8 | 0.0078 | 8 | fail: no_target_lost | fragment 10/18 |
| 0.783 | 7/18 | -61.1 | 0 (+0) | 0 (+0) | 0 | 0 | 11 | 0.0010 | 11 | fail: no_target_lost | fragment 7/18 |
| 0.833 | 4/18 | -77.8 | 0 (+0) | 0 (+0) | 0 | 0 | 14 | 0.0001 | 14 | fail: no_target_lost | fragment 4/18 |
| 0.922 | 1/18 | -94.4 | 0 (+0) | 0 (+0) | 0 | 0 | 17 | 0.0000 | 17 | fail: no_target_lost | fragment 1/18 |

## floor: experimental: cosine >= value alone admits, z_bar is not consulted (KG-1 admission_floor.diff)

> floor is an experimental admission mode, not an upstream default and not proposed as one; its values do not carry over between models.

| value | recall@5 | pts | noise (net) | confusion (net) | extra | b | c | p | lost | gate | by category |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.083 | 18/18 | +0.0 | 16 (+16) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: noise_not_higher,mcnemar_p_below_0.05 | fragment 18/18 |
| 0.107 | 18/18 | +0.0 | 12 (+12) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: noise_not_higher,mcnemar_p_below_0.05 | fragment 18/18 |
| 0.14 | 18/18 | +0.0 | 9 (+9) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: noise_not_higher,mcnemar_p_below_0.05 | fragment 18/18 |
| 0.216 | 18/18 | +0.0 | 6 (+6) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: noise_not_higher,mcnemar_p_below_0.05 | fragment 18/18 |
| 0.277 | 18/18 | +0.0 | 2 (+2) | 0 (+0) | 0 | 0 | 0 | 1.0000 | 0 | fail: noise_not_higher,mcnemar_p_below_0.05 | fragment 18/18 |
| 0.576 | 17/18 | -5.6 | 0 (+0) | 0 (+0) | 0 | 0 | 1 | 1.0000 | 1 | fail: no_target_lost,mcnemar_p_below_0.05 | fragment 17/18 |
| 0.675 | 14/18 | -22.2 | 0 (+0) | 0 (+0) | 0 | 0 | 4 | 0.1250 | 4 | fail: no_target_lost,mcnemar_p_below_0.05 | fragment 14/18 |
| 0.709 | 10/18 | -44.4 | 0 (+0) | 0 (+0) | 0 | 0 | 8 | 0.0078 | 8 | fail: no_target_lost | fragment 10/18 |
| 0.783 | 7/18 | -61.1 | 0 (+0) | 0 (+0) | 0 | 0 | 11 | 0.0010 | 11 | fail: no_target_lost | fragment 7/18 |
| 0.833 | 4/18 | -77.8 | 0 (+0) | 0 (+0) | 0 | 0 | 14 | 0.0001 | 14 | fail: no_target_lost | fragment 4/18 |
| 0.922 | 1/18 | -94.4 | 0 (+0) | 0 (+0) | 0 | 0 | 17 | 0.0000 | 17 | fail: no_target_lost | fragment 1/18 |

## Points that pass the gate (exploratory)

- zbar: none
- zbar_floor: none
- floor: none
