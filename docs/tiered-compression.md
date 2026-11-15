# Tiered density compression (proposal — not implemented)

> **Status: design proposal.** The *motivation* is backed by a synthetic scaling
> experiment (below); the *tiered scheme itself is an idea, not built or measured*.
> It is written down to be picked up later, not claimed as a result.

## The problem: density makes top-k structurally incomplete

A personal fact store grows in two ways at once:

- **Dense growth** — more facts about topics you already care about.
- **Broad growth** — facts about brand-new topics.

They are not equivalent. In a controlled synthetic expansion (56 → 3000 facts,
two arms grown to the same size):

| growth | acceptable-set size per query | top-1 is an acceptable answer | top-5 coverage of the acceptable set |
|---|---|---|---|
| dense | ~2 → ~190 | stays high (~0.98) | collapses (~0.85 → ~0.03) |
| broad | ~2 → ~7 | stays high | stays high (~0.82) |

Two readings, two different stories:

- **"Can it answer correctly?"** (is *any* acceptable fact in top-k): dense growth
  makes this *better* — more correct answers exist, so any pick works.
- **"Can it retrieve the whole acceptable set?"** (coverage): dense growth makes
  this *worse* — there are ~190 acceptable facts and top-5 only covers ~3%.

The second is a real need for **set tasks** (aggregation, audit, dedup, timeline
reconstruction), where truncating to top-k silently drops data. Ranked top-k cannot
solve it by raising k: the curve is flat, you would need k in the hundreds.

## The idea: shrink the denominator, don't grow the numerator

Instead of retrieving more, **compress the redundancy away** so the acceptable set
becomes small enough that top-k covers most of it again. This mirrors how human
memory works: we do not keep every episodic detail ("what were you doing at 8:10 pm
on 2025-11-20" is useless); we compress repeated experience into a *gist*.

A flat near-duplicate merge already shows the mechanism (same synthetic dense arm):

| | store size | acceptable-set mean | top-5 coverage |
|---|---|---|---|
| before | 3000 | ~190 | ~0.03 |
| after near-dup merge | ~80 | ~4 | ~0.89 |

Coverage jumps from ~3% to ~89% while "can it answer correctly" stays high. The
denominator collapsed; top-k became sufficient again.

## The proposal: compress in similarity tiers, triggered by density

A flat merge is too blunt — it treats "almost identical" and "loosely related" the
same. The proposal is to **trigger compression when local density crosses a
threshold, then merge in graduated similarity bands**, tight bands first:

| band (pairwise cosine) | action | intent |
|---|---|---|
| ≥ 0.90 | merge aggressively into one gist | near-duplicates; safe to collapse |
| 0.80 – 0.90 | merge, keep distinguishing details | same topic, minor variants |
| 0.70 – 0.80 | merge cautiously, preserve differences | related but distinct sub-facts |
| 0.60 – 0.70 | link / cluster, do **not** merge | loosely related; keep separate, group |
| < 0.60 | leave alone | unrelated |

Principles:

1. **Density-triggered, not always-on.** Compress a topic cluster only when its
   acceptable-set size exceeds a budget (e.g. > k × target-coverage). Sparse topics
   are left untouched — no point compressing what already fits.
2. **Tight first, loose last.** High-similarity bands collapse safely; lower bands
   preserve more, because the risk of destroying a useful difference rises as
   similarity falls.
3. **Merge ≠ delete.** A merged gist keeps pointers to the originals (cold storage),
   so set tasks can still reach the full set when they truly need it. Daily lookup
   uses the gist; aggregation/audit walks the originals.
4. **Conflict-check before merge.** Two facts that look like duplicates may record
   *different* values (e.g. two different server addresses). Detect contradiction
   first; never compress a conflict into a single misleading gist.
5. **Gist generation is an LLM job, not vector deletion.** The bands decide *what to
   group*; producing the compressed text (keep key differences, drop redundancy) is
   a summarization step. Vector-level dedup is only the cheap proxy used in the
   motivating experiment.

## Why tiers rather than one threshold

A single threshold forces a binary choice: too high and redundancy survives; too low
and distinct facts get destroyed. Bands let the system be **aggressive where it is
safe and conservative where it is risky**, which is exactly the precision/recall
trade-off the rest of this repo tunes — applied to *storage* instead of *admission*.

## Honest boundaries

- The tiered scheme is **not implemented and not measured**. Band edges (0.9/0.8/0.7/
  0.6) are a starting guess, to be set by eval like every other knob here.
- The motivating numbers come from a **synthetic, highly redundant** dense arm; real
  memory is less uniform, so real compression ratios will be lower.
- Vector dedup ≠ true summarization; the experiment shows the *ceiling* of the
  mechanism, not a production result.
- Compression can lose useful detail; the conflict-check and cold-storage pointers
  are mandatory guards, not optional polish.

## Relation to the rest of the repo

This is the storage-side counterpart to the admission-side tuning in
[`../memory/README.md`](../memory/README.md): admission decides *what gets recalled*,
compression decides *what stays worth recalling*. Both follow the same discipline —
measure first, keep a fail-open path, and never buy a gain with silent data loss.