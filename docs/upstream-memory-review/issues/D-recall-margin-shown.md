# Recall by meaning: a lower margin only before a turn that already shows a fact

**Target:** `itpartypattaya/hermes-plugin-holographic` · draft only

## Problem or use case

#17 lowered `RECALL_MARGIN` before every turn and did not pass the gate: noise rose. On small stores the default admits almost nothing on meaning (on `synthetic_zh` at full keyword coverage, no fact in either arm of #95), so questions that share no word with their fact stay unanswered before the turn.

In the committed margin rows, every noise row a lower margin adds is a turn that showed nothing at 1.0. That is by definition: a noise row is a chit or no-answer row with output, and a row that already had output is already counted. So the lower margin costs noise only where the words and the entity stream leave the turn silent.

## A: two margins (what I would like measured)

Keep `RECALL_MARGIN` for a turn that would otherwise show nothing. Use a second, lower margin when the turn already shows a fact: the words found one, or the message names an entity that has one. Proposed pair: 0.7 and 0.5. The default stays as it is until the gate passes.

A replay over `results/provenance_*_m{1,0.7,0.5}_on.jsonl` (five sets, 810 rows). Per `(set, lang, qid)` the proposal takes the 0.5 row when the 1.0 row shows a fact whose `sources` are not `meaning` alone, else the 0.7 row. Hits, noise, confusion and p are computed by `mcnemar_gate.py`'s own functions:

| margin | hit@5 of 540 | b / c | exact McNemar p | noise | confusion |
|---|---|---|---|---|---|
| 1.0 (default) | 481 | | | 94 | 34 |
| 0.5 before every turn | 487 | 6 / 0 | 0.031 | 98 | 34 |
| 0.7 silent, 0.5 shown | 486 | 5 / 0 | 0.063 | 94 | 34 |

What this is not:

- It is not a gate result. The committed rows are from two commits (`958de48` for 1.0 and 0.6, `3eb1099` for the rest), so `--pair margin` rightly refuses them. The 0.95 rows equal the 1.0 rows on all 810, which is why I think the replay is worth reading; it still needs one run at one commit.
- 0.7 and 0.5 were chosen on these rows, after seeing them. The sixth rescue of the plain 0.5 run (`contrast_zh p4q0`) is a silent turn that needs 0.65 or lower, where `contrast_ru c31` flips too.
- It is one rescue short of p < 0.05, and `synthetic_zh` is not in the committed sweep.

## B: the closest fact only, on a cosine floor (a trade, for comparison)

Vectors from `content+keywords`; only the single closest fact is considered, admitted at cosine ≥ 0.55 (bge-m3) when the turn does not already show it; no second candidate when it is refused.

Measured on two small stores with bge-m3, through the plugin's prefetch on frozen cosines: `synthetic_zh` 29 → 33 of 36 and a private store 34 → 38 of 44, no target lost. Noise +1 and +0 rows, confusion +1 and +2 rows, three non-target facts added on each. A on the same two stores, with keywords in the vector: +1 and +1, nothing else moved.

B does not pass the gate, and its floor is tied to the model (#95, #110). I include it because it is where the larger gain is, in case an opt-in for one's own store is of interest.

## C: the 0.5 margin, with the added fact checked by a small cross-encoder (for information)

When the meaning stream showed nothing at the default and fewer than five facts are shown, the first fact the stream would admit at 0.5 goes, with the message, to a local cross-encoder (`Qwen3-Reranker-0.6B`). The instruction asks whether the fact alone gives a concrete answer, with the entity and the attribute asked for. The fact is appended when the `yes` logit is above the `no` logit. No threshold is fitted.

On the same committed rows, 19 added facts could be rebuilt: 6 targets and 13 others. The check passed the 6 targets and 1 of the others, in a row that already showed a non-target:

| | hit@5 of 540 | b / c | exact McNemar p | noise | confusion |
|---|---|---|---|---|---|
| 0.5, the added fact checked | 487 | 6 / 0 | 0.031 | 94 | 34 |

- The limits of A's table apply: a replay over two commits. These rows had been used to choose 0.5 and to try other rules, so p is exploratory.
- On the household dev questions (not in those rows; the same facts, bge-m3, through `prefetch`): 74 → 76 of 99, noise 48 → 48, confusion 7 → 7. The plain 0.5 margin there gives 80 with noise 52. The check refused all 6 non-targets, and 4 of the 6 targets.
- On the two small stores of B it adds nothing: at 0.5 the bar offers 3 and 1 candidates.
- The instruction is mine and its wording matters. Checking B's closest fact on the small stores, where 5 of the candidates on each are targets, mine passed 1 and 0 of them and nothing else. The model card's own passed 3 and 1, and one non-answer on each.
- Cost: at most one pair a turn (19 of 810 turns here), about 50 ms on a laptop GPU, 1.2 GB of weights. `rerank.scores()` returns `[(0, 1.0)]` for a single document, so this needs a call that scores one pair. I read the logits locally and have not tried it through a `/v1/rerank` endpoint.

## Question

Would you measure A on the gate at one commit, with `synthetic_zh` in the pool? I have a patch that adds it the way `EMBED_TEXT` was added: a module value that is unset by default, `--recall-margin-shown` in the probe with its stamp in the rows and the file name, and the gate reading that stamp. With the value unset, recall is unchanged. I can open it as a PR, or you may prefer to wire it yourself.

And are B or C, as opt-ins, something you would want to see at all?
