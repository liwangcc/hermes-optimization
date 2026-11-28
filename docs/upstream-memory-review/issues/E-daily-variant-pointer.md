# A recall-first wrapper built on the plugin: numbers on the probe's sets, and a small ask

**Target:** `itpartypattaya/hermes-plugin-holographic` · draft only · not a code proposal

## What it is

The setup I run every day is a thin wrapper around the plugin plus a local sidecar. It lives at
https://github.com/liwangcc/hermes-optimization. The plugin itself is unchanged and runs with embeddings off:

- A bge-m3 sidecar appends the closest fact by cosine (floor 0.55).
- A small cross-encoder reads the message with each fact of the block and with that closest fact, drops what is off
  the message and confirms the addition. It is the same Qwen3-Reranker-0.6B as the #135 check.
- Up to four `#id=label` pointers list close facts that were not shown; the model reads one with `fact_store get`.

It trades the other way from the plugin's default: more shown on meaning, then cut back by a judge.

## Numbers on the probe's own sets

Both sides at one plugin commit (`67229de`, v0.31.4 with the switch unset), bge-m3 for both, and the same blind
keywords from `tools/issue95_keywords/` in the facts of both. Six sets (household dev and test, contrast en/ru/zh,
`synthetic_zh`), 618 rows, 300 answerable. Hits, noise and confusion are counted with `mcnemar_gate.py`'s
definitions, copied into my referee.

| | hit@5 of 300 | non-targets shown | noise rows | confusion rows | b / c against main + keywords | targets lost |
|---|---:|---:|---:|---:|---|---:|
| main, no keywords (the committed gate rows) | 206 | 915 | 142 | 45 | | |
| main, `--keywords`, full coverage | 244 | 1004 | 155 | 52 | | |
| wrapper, judge off | 265 | 1079 | 192 | 52 | 23 / 2 | 3 |
| wrapper, judge on | 273 | 524 | 129 | 31 | 30 / 1 | 4 |

On the rows my rule was not fitted on (contrast and household test, 165 answerable): main with keywords 133,
wrapper 147, b / c 15 / 1 (exact McNemar p = 0.0005), non-targets 652 against 371, noise 103 against 88,
confusion 34 against 24, 2 targets lost.

Two checks behind the table. The no-keyword arm is a rerun and shows the same facts as the committed
`results/issue121` rows on all 618. The wrapper's rows were measured on the base block of an older checkout; the
same arm from `67229de` gives the same block on all 618 (one renamed fact key aside).

Rows, scripts and the method are in
[`memory/recall-race/VS-OFFICIAL.md`](https://github.com/liwangcc/hermes-optimization/blob/main/memory/recall-race/VS-OFFICIAL.md).

## What this is not

- **Not a candidate for the plugin.** It loses targets (4 here, 2 on the held-out rows), so it fails the gate's
  first guard. It also needs a local sidecar and two local models: bge-m3 and the 0.6B judge, about 1.3 GB of VRAM
  and 0.2 s a message on a laptop GPU.
- **Not a result on the current version.** These are v0.31.4 rows. `multi` is left out because my frozen pack
  predates the renamed persons of 0.31.3 and 0.31.4.
- **One embedding model, one judge.** The judge's constants were fitted on the dev pool of these same sets.
- **Synthetic, direct questions on small stores.** Nothing here is measured on a real store or with a model in
  the loop.
- **Not a new reading of #95.** The sidecar's vectors include the keywords and the plugin's do not, but the
  admission rule differs too, and I have not separated the two. Your result under the plugin's own gate stands.
- Of the 67 hits between the committed rows and the wrapper, 38 are the keywords: the plugin's own feature at full
  coverage, not mine.

## The ask

Would you be open to one line in the README pointing to it, for users who want the recall-first trade and can run
local models? Something like a "Built on this plugin" or "Related" entry; the wording is yours, and the numbers and
limits stay on my side.

If you would rather not link an out-of-tree wrapper, that is fine. I would still value your read on whether the
comparison is fair: the keyword coverage, the counting, or anything in the method that favours my side.
