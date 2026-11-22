# Recall by meaning: a lower margin whose added fact a small cross-encoder confirms

**Target:** `itpartypattaya/hermes-plugin-holographic` · proposed revision of issue #121, draft for approval

> 修订说明（不发出去）：原 #121 以 A（双档余量）为主提议。bge-m3 端到端直跑后 A 噪声上涨过不了门禁，C（小模型复核）已有补丁且两池门禁全过，故 C 升为主提议、A 如实降级为更正段。标题随之改。下面是拟替换 #121 的英文标题与正文。

## Problem or use case

#17 lowered `RECALL_MARGIN` before every turn and did not pass the gate: noise rose. On small stores the default admits almost nothing on meaning (on `synthetic_zh` at full keyword coverage, no fact in either arm of #95), so questions that share no word with their fact stay unanswered before the turn.

In the committed margin rows, every noise row a lower margin adds is a turn that showed nothing at 1.0. That is by definition: a noise row is a chit or no-answer row with output, and a row that already had output is already counted. So the lower margin costs noise only where the words and the entity stream leave the turn silent.

## What I would like measured: a lower margin whose added fact a cross-encoder confirms

Lower the meaning margin to 0.5, but offer the one fact this adds beyond the default only when a local cross-encoder confirms the fact alone answers the message. A fact that already stands out at `RECALL_MARGIN` is offered as before and is not asked about. At most one question a turn — the closest fact that needs the check. The cross-encoder is `Qwen3-Reranker-0.6B`; the fact is appended when its `yes` logit beats `no` for "the fact alone supplies a concrete answer, with the entity and the attribute asked for". No threshold is fitted. `rerank` itself stays off; the candidate pool is not reordered.

I have a patch that adds this as `embeddings.RECALL_CHECK_MARGIN`, a module value unset by default, the way `EMBED_TEXT` was added for #95: `--recall-check-margin` in the probe, stamped in the rows and the file name, the gate reading that stamp. With the value unset, recall is unchanged.

Measured with the probe on the patched branch, `--emb on --modes off --repeats 1`, the default against `--recall-check-margin 0.5`, both runs on one endpoint — bge-m3 embeddings, the cross-encoder above:

| pool | hit@5 | b / c | exact McNemar p | noise | confusion | gate |
|---|---|---|---|---|---|---|
| multi (18 languages), contrast en / ru / zh, household test: 540 real | 480 → 486 | 6 / 0 | 0.031 | 93 → 93 | 34 → 34 | passes |
| the same plus household dev and `synthetic_zh`: 696 real | 565 → 573 | 8 / 0 | 0.008 | 142 → 142 | 46 → 46 | passes |

The check is what keeps the noise flat: 0.5 without it on the first pool is 10 / 0 with noise 93 → 99. The cross-encoder is conservative — of 25 candidates on the first pool (10 of them targets) it passed 6 targets and 1 other, and that 1 other landed in a row already showing a non-target, so noise and confusion did not move.

On your committed `text-embedding-3-small` rows, a replay with the same cross-encoder gives 6 / 0, noise 94 → 94, confusion 34 → 34. I have no key for that model and have not run it directly; the bge-m3 numbers above are end-to-end on the branch.

What this is not:

- Five sets is exactly the gate's minimum (6 rescues); there is no margin for a missed answer. The larger pool gives 8.
- One cross-encoder and one instruction. A general-purpose reranker's score above 0 means "relevant", which is looser than "answers it"; I have not measured one.
- The rows carry a `-dirty` `git_sha` (written before the patch was committed); the questions are the same as the replay, not independent.
- Cost: at most one pair a turn, about 45 ms on a laptop GPU, 1.19 GB of weights alongside bge-m3.

## A two-tier margin on its own does not pass on bge-m3 (a correction)

The earlier draft of this issue proposed two margins — keep `RECALL_MARGIN` for a turn that would otherwise show nothing, use 0.5 when the turn already shows a fact — and reported noise and confusion unchanged, one rescue short of significance. That was a replay over your committed `text-embedding-3-small` rows: 481 → 486, 5 / 0, p = 0.0625, noise 94 → 94.

Run directly with the probe on bge-m3, the same rule raises noise: 480 → 487, 7 / 0, p = 0.016, noise 93 → 95, confusion 34 → 34. The two extra noise rows are `contrast_ru` `c17` and `c31`, both silent chit turns. Tightening the silent margin until noise stays flat leaves 4 rescues, not significant; on bge-m3 no setting of the two-tier rule passes all four conditions. The "noise unchanged" result was specific to the replay model, so I am not proposing the two-tier rule on its own.

## B: the closest fact only, on a cosine floor (a trade, for comparison)

Vectors from `content+keywords`; only the single closest fact is considered, admitted at cosine ≥ 0.55 (bge-m3) when the turn does not already show it; no second candidate when it is refused.

Measured on two small stores with bge-m3, through the plugin's prefetch on frozen cosines: `synthetic_zh` 29 → 33 of 36 and a private store 34 → 38 of 44, no target lost. Noise +1 and +0 rows, confusion +1 and +2 rows, three non-target facts added on each. The two-tier rule on the same two stores, with keywords in the vector: +1 and +1, nothing else moved.

B does not pass the gate, and its floor is tied to the model (#95, #110). I include it because it is where the larger gain is, in case an opt-in for one's own store is of interest.

## Question

Would you measure the checked margin on the gate at one commit, with `synthetic_zh` in the pool? The patch adds it as a module value unset by default; with it unset, recall is unchanged. I can open it as a PR, or you may prefer to wire it yourself. I have no key for `text-embedding-3-small`, so a run on your model is the missing piece.

And is B, as an opt-in for one's own store, something you would want to see at all?