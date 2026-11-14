# Eval

A self-contained retrieval eval on a **synthetic** Chinese-heavy fact store. No personal
data, no lexical stack, no database — just bge-m3 and the two JSON files here.

- `facts.json` — 30 generic software-project facts (content + keywords + trust).
- `queries.json` — 42 queries: direct / paraphrase / crosslingual / colloquial, plus 6
  negative queries that must recall nothing.
- `run_eval.py` — embeds facts (content-only and content+keywords) and queries, then
  compares admission rules.
- `results.json` — the committed output of the last run.

## Run

```bash
pip install numpy torch sentence-transformers
BGE_MODEL=/path/to/bge-m3 python run_eval.py
# BGE_MODEL defaults to the HuggingFace id "BAAI/bge-m3" if unset
```

Embeddings are cached to `emb_*.npy` (gitignored); delete them to re-embed.

## What it compares

| system | admission | fact text |
|---|---|---|
| `zbar_content` | `z ≥ sqrt(2·ln N) + 1.0` (upstream default) | content |
| `zbar_content_tags` | same | content + keywords |
| `cos_content` | `cosine ≥ 0.55` | content |
| `cos_content_tags` | `cosine ≥ 0.55` | content + keywords |

Metrics: recall@5, top1, negative false-positive rate, and recall@5 by category.

## Reading the result

The point is not the absolute numbers (a 30-fact synthetic store is tiny) but the
*ordering*: the upstream `zbar` gate admits almost nothing on paraphrased/colloquial
queries, while `cos ≥ 0.55` with keywords admits most of them — and the negative
false-positive rate stays 0.0, so the gain is not bought with noise.