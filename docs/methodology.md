# Methodology & lessons

How the optimizations in this repo were chosen and verified. The recurring theme:
**measure first, keep a fail-open path, and survive upstream updates.**

## 1. Evaluate before tuning

Every retrieval parameter here was set by an eval, not by feel. The loop:

1. Build a labeled query set (direct / paraphrase / crosslingual / colloquial / negative).
2. Run the candidate systems on the *same* embeddings.
3. Read recall@5, top1, and the negative false-positive rate **by category**.
4. Pick the operating point that raises recall without raising noise.

The negative queries matter as much as the positive ones: a recall gain bought with
chit-chat false positives is not a gain. See [`../memory/eval/`](../memory/eval/README.md).

## 2. Check the upstream latest before building

A local README can be stale. Before building a capability, check the upstream project's
latest release — it may already exist. (Here, the upstream plugin had added a built-in
embeddings client; the durable, non-overlapping value turned out to be the *local GPU
embedding service* + the *eval-driven fusion*, not the HTTP client.)

## 3. Wrap, don't fork

To survive upstream updates, the enhancement **subclasses the upstream provider at load
time** instead of editing it:

- the original plugin is never modified;
- upstream updates flow through automatically;
- rollback is a one-line config change.

This was verified across a large upstream version jump with a post-update self-check
(static symbol presence + a behavioral test suite), not just "it imports".

## 4. Fail-open everywhere

A recall enhancement must never block a turn:

- sidecar down or slow → fall back to lexical recall within a small timeout budget;
- localhost calls bypass any system proxy (a proxy on `127.0.0.1` is a classic timeout);
- a warmup encode avoids the first-query GPU cold start.

## 5. Keep three things untouched

When adding semantic recall to a memory system, do not disturb:

1. the always-on USER/MEMORY layer (keep it small; don't vectorize it);
2. proper-noun hard anchors (exact identifiers must still match);
3. trust/feedback, supersede, and contradiction detection.

## 6. Lean skills over confirmation ritual

Behavioral skills should confirm *decisions*, not re-check *facts* the runtime can
verify. A heavy pre-emptive confirmation ritual is overhead, not safety. This repository
no longer ships workflow skills — it is focused on memory — but the principle still
applies to any skill you keep in `$HERMES_HOME/skills/`.

## 7. Sanitize before sharing

A personal agent setup is full of keys, personal memory, and network/account details.
Anything shared publicly must be a *generic* guide with example values — never a dump of
the live environment. Run an exposure audit (secrets, personal paths, identity) before
publishing, and prove a "zero hits" scan can actually hit a known positive sample.