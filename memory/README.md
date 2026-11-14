# Semantic memory enhancement

A hybrid semantic-recall layer for the [holographic](https://github.com/itpartypattaya/hermes-plugin-holographic)
memory provider, tuned for a **Chinese-heavy** personal fact store. It is an
*enhancement*, not a replacement: holographic still owns the fact store, the lexical
retriever, and trust/feedback; this layer adds a local embedding channel on top.

> Design rationale — why a tiny always-on layer coexists with a retrieved store, what
> pointers point at, and how each layer is kept clean — is in
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

Two things to note:
- **Keywords help without lowering the bar** — they enrich the fact vector, so this is
  an *admission-input* improvement, not a request to relax the precision gate.
- **Negative false-positive rate stays 0.0** — the cosine threshold does not admit
  chit-chat, so recall goes up without the noise that a lower `zbar` margin would add.

In production the semantic channel is unioned with the lexical channel (hybrid), which
pushes recall higher still; the eval above isolates the semantic admission decision so
it is reproducible without the lexical stack.

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