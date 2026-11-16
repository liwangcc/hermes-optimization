# Synthetic set (public, MIT) — Chinese-heavy retrieval eval

Generic software-project knowledge, **no personal data**. Safe to publish and re-run.

## Files
- `facts.json` — 30 facts: `{fact_id, content, tags, trust_score}`. `tags` are user-style tags, NOT the blind keywords.
- `queries.json` — 42 queries: `{id, category, query, expected:[fact_id]}`. Categories: direct 8, paraphrase 10, crosslingual 8, colloquial 10, negative 6. Labelled = 36 (negative 6 are noise rows).
- `queries_ext.json` — 6 in-domain no-answer questions (topics none of the 30 facts covers); noise rows under the upstream definition. Total noise = 12.
- `blind_keywords.json` — `{fact_id: [keywords]}`, 219 keywords over 30 facts (6–8 each).
- `keywords_upstream_format.json` — the same keywords shaped `{lang: {fact_key: [keywords]}}` with `lang="synthetic_zh"`, matching `tools/issue95_keywords/` (validated: every fact present, none extra, 3–8 keywords ≤40 chars, no comma inside).
- `BLIND-FREEZE.md` — freeze record + sha256.
- `rows/` — our measurement rows (5 cells × full/half) + gate reports.

## How the keywords were written (blind)
A separate pass saw ONLY `facts_content_only.json` (fact_id + content) and the `keywords` field description — no queries, no results, no eval README. Written 2026-11-16, frozen before any run with them (sha256 in BLIND-FREEZE.md). Transcript audit: 0 reads of queries/results before the freeze. Information-blind (written after the queries existed calendar-wise, but with no access to them); NOT a separate session — disclosed as such.

## Results here (bge-m3 fp16, stemmer snowballstemmer-3.1.1, vendor 0.27.0 @114cf5f)
hit@5 (=recall@5), 36 labelled:

| coverage | L0 | ZC | ZK | FC | FK | gate ZC→ZK |
|---|---|---|---|---|---|---|
| full | 29 | 29 | 30 | 31 | 33 | b=1 c=0 p=1.0 FAIL |
| half (kw 15) | 17 | 17 | 18 | 22 | 22 | b=1 c=0 p=1.0 FAIL |

Keywords-in-vector under the upstream z_bar gate: +1 rescued, 0 lost, 0 noise, 0 confusion — directionally positive, not significant (power: only 7 L0-misses at full). The large recall gain is the admission change (ZC→FC), not keywords. See ../METRICS.md and ../real/METHODOLOGY.md.

## Re-running with the upstream tooling
The official `tools/provenance_probe.py` runs built-in sets; this set is not built-in. To run it natively at your head, add it as a set module + drop `keywords_upstream_format.json` into `tools/issue95_keywords/`. We can contribute that as a data-only PR (no behaviour change) on request, or re-run it ourselves at your head with `--embed-text content` / `content+keywords` and send the native rows. Our rows were captured at 0.27.0 (114cf5f) through the plugin's real prefetch path; gate math cross-checked against your `mcnemar_gate.py` (b=1 c=0 p=1.0 matched). They are independent convergent evidence, not poolable with your pilot (different head/model).