# Semantic memory enhancement

A hybrid semantic-recall layer for the [holographic](https://github.com/itpartypattaya/hermes-plugin-holographic)
memory provider, tuned for a **Chinese-heavy** personal fact store. It is an
*enhancement*, not a replacement: holographic still owns the fact store, the lexical
retriever, and trust/feedback; this layer adds a local embedding channel on top.

> Design rationale — why a tiny always-on layer coexists with a retrieved store, where a
> new memory is written, and how each layer is kept clean — is in
> [`../docs/memory-architecture.md`](../docs/memory-architecture.md).

## Why

Lexical recall (FTS5 + stemming) misses queries that share *meaning* but not *words* —
paraphrases, colloquial phrasings, and cross-lingual questions ("what database is used"
vs a fact written in Chinese). On a real Chinese store the cross-lingual recall was 0.25.
A local multilingual embedding model (bge-m3) closes most of that gap.

## Architecture

```
query ──► base holographic prefetch (lexical, unchanged) ──┐
      └─► sidecar /candidates (bge-m3, cos ≥ tau) ──────────┤
                                                            ▼
                          gated union, dedup, trust filter, greeting guard,
                          repeat-window, total cap ──► injected facts
```

- **`sidecar/`** — local bge-m3 HTTP service (GPU fp16, offline, cached, fail-safe).
  Produces vectors; read-only on the fact DB.
- **`plugin/holographic-semantic/`** — subclasses the holographic provider *unchanged*
  and appends up to N semantic facts to `prefetch`. Any sidecar problem falls back to
  the base result; recall never blocks. One-command rollback.
- **`eval/`** — a self-contained, synthetic Chinese-heavy eval reproducing the tuning.

## What actually matters: how facts are *admitted* on meaning

Holding bge-m3 fixed, two admission rules behave very differently:

- **Upstream default (`zbar`)** — admit a fact only if its standardized similarity
  `z ≥ sqrt(2·ln N) + RECALL_MARGIN` (margin 1.0). A precision-first statistical-outlier
  gate. On a small store it admits almost nothing for paraphrased/colloquial queries.
- **Tuned (`cos`)** — admit facts with `cosine ≥ tau` (0.55). A recall-first absolute gate.

And the fact text matters: upstream embeds **content only**; adding the curated
**keywords** (`tags`) to the embedded text raises true-match similarity.

### Reproducible result (synthetic 30-fact Chinese store, 42 queries)

| admission | fact text | recall@5 | colloquial | crosslingual | neg false-pos |
|---|---|---|---|---|---|
| zbar (margin 1.0) | content | 0.083 | 0.00 | 0.125 | 0.0 |
| zbar (margin 1.0) | content+keywords | 0.194 | 0.20 | 0.125 | 0.0 |
| cos ≥ 0.55 | content | 0.556 | 0.50 | 0.375 | 0.0 |
| **cos ≥ 0.55** | **content+keywords** | **0.722** | **0.90** | **0.50** | **0.0** |

Run it yourself: see [`eval/README.md`](eval/README.md). Numbers come from
[`eval/results.json`](eval/results.json) (bge-m3, CUDA fp16).

Two things to note — and one correction:
- **Keywords help without lowering the bar** — they enrich the fact vector, so this is
  an *admission-input* improvement, not a request to relax the precision gate.
- **Precision is NOT preserved — earlier wording retracted.** On the 36 positive queries,
  `cos ≥ 0.55` + keywords returns 75 facts but only 26 are the target (precision ≈ 0.35);
  the other 49 are non-target. The `neg_fp_rate = 0.0` above only means the 6 *chit-chat*
  negatives recall nothing — there are **no same-domain hard negatives** in this eval, so
  it does not show that real-world precision is intact.

In production the semantic channel is unioned with the lexical channel (hybrid). On the
real store the bigger lever is the write-time bilingual + colloquial keywords (lexical
recall@5 24/39 → 32/39); the sidecar adds fallback + association on top (→ 34/39) at ~3G
VRAM and falls back to lexical-only when unavailable. The top-level README has the
real-store three-keyword comparison, the scale experiment, and the limitations.

## Tuning knobs

| knob | value | rationale |
|---|---|---|
| `semantic_tau` | 0.55 | eval-tuned cosine floor; lower = more recall, more noise |
| fact text | content + keywords | keywords are curated signal absent from the prose |
| `semantic_max_extra` / `semantic_total_cap` | 3 / 7 | bound injected context |
| `semantic_timeout_ms` | 400 | fail-open budget; exceed → lexical only |
| greeting guard | on | no semantic noise on "hi"/"hello" |

## Design constraints

- **Update-proof**: the base plugin is never edited; the wrapper subclasses it at load
  time, so upstream updates flow through. Verified across a 0.6 → 0.26 plugin jump.
- **Fail-open**: sidecar down/slow → lexical recall, never a blocked turn.
- **Three things kept untouched**: the always-on USER/MEMORY layer is not vectorized;
  proper-noun hard anchors stay; trust/feedback, supersede, and contradiction detection stay.