# Daily-shape recall rules: plan frozen before any test feature exists (2026-11-22)

Baseline: daily 0.6.0 local mode, replayed offline by daily_eval.daily (base 0.30.0 prefetch with embeddings
off, then the closest fact by bge-m3 cosine of content + " " + tags, cos >= 0.55, not shown, block < 7,
recallable, names_fit). The replay reproduces the measured 0.6.0 numbers exactly (synthetic 33/36, noise 4,
confusion@5 11, +3 wrong; household zh 49/58, noise 33, confusion@5 27, +16 wrong; household en 8/12, ru 5/17).

Dev (rule design allowed): synthetic, household en/ru/zh  -> scratchpad/dump/dev
Test (generated only after rules are frozen): contrast_en, contrast_ru, contrast_zh, multi x8 (de en it ja nl ru
th zh), two_topics (ru)  -> scratchpad/dump/test

Metrics (daily_eval.row_counts, whole injected block): hit, hit5, rescued, lost_targets, noise rows,
confusion rows, shown_other, added_wrong, removed_other.

Decision per frozen rule, pooled test vs daily 0.6.0:
- PURE GAIN: lost_targets == 0, hit >= daily, shown_other < daily, noise <= daily, confusion <= daily,
  and no test family (contrast / multi / two_topics) loses a hit row.
- Otherwise TRADE: reported with exact numbers, never called an improvement.
No parameter is changed after the test run. Any later change needs a new holdout.

Usability gates (native run of the frozen rule): prefetch p95 < 3 s on CPU-only with the model resident,
and on GPU; GPU memory for the encoder < 6 GB; no new model, no extra encoder call per message.

## Addendum: rules frozen after dev exploration, before any test feature exists

frozen_rules.py (constants: Z_SILENT -0.5, RESCUE_TAU 0.45, Z_RESCUE 1.0, LEAD 0.02, GAP 0.20, FLOOR 0.35,
ENTITY_TAU 0.55). Primary: P1 (veto + silent standout) and P2 (P1 + silent rescue). Secondary: P1E, P2E
(+ entity bar; no entity-stream target exists on dev, so its risk could not be measured there).
Dev vs daily (hit / lost / noise / confusion / shown_other / added_wrong):
daily 183/-/99/102/551/-; P1 183/0/84/81/404/0; P2 188/0/88/81/408/4; P1E 183/0/80/73/329/0; P2E 188/0/84/73/333/4.
Each rule gets the PURE GAIN / TRADE verdict above on the pooled test set; all four are reported.
