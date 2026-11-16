# Real set — methodology card (text withheld for privacy)

**This is a real personal Chinese memory store.** It contains server IPs, account details and private information, so the fact texts and query texts are NOT shared — not even redacted (54 personal facts + 54 queries are too easy to leak by missed redaction, and the queries alone reveal personal projects). What IS shared: opaque per-query rows (IDs, flags, stamps — zero text, zero vectors) and this methodology card, so the gate math can be audited without exposing content.

## Store
- Source: a frozen snapshot of a live personal Hermes holographic memory store (56 facts, all created before the queries were labelled).
- Measurement store: **54 facts**. Two facts (#203, #229) carry credential-like values that the plugin's `_sendable` secret screen never sends → vector coverage 54/56 → semantic cells discarded under the pre-registered completeness rule. Resolution: exclude those 2 facts uniformly at data-prep (all cells identical, lexical side loses them too); query A6 targets intersected to the remaining fact, query D1 (target fully excluded) dropped. The gate rule itself was NOT changed. Conservative: the excluded queries cannot be rescued by meaning in either arm.
- Keywords: **naturally present on 35 of 54 facts** in the snapshot (pre-existing tags from earlier optimization), created before query labelling → naturally blind, not rewritten. half coverage = fixed seed 20261116 draw of n//2 facts ∩ facts-with-keywords = 15.

## Queries
- 54 total: 44 labelled (direct 8, paraphrase 14, crosslingual 8, colloquial 14) + 10 noise (5 chit + 5 in-domain no-answer extensions RX1–RX5, topics verified absent from the store).
- Language: zh (crosslingual queries are English questions targeting Chinese facts).

## Run conditions
bge-m3 fp16 CUDA (local sidecar, OpenAI-protocol shim, no second model load); rerank off; RECALL_MARGIN 1.0; stemmer snowballstemmer-3.1.1; vendor 0.27.0 @114cf5f; core shim (cross-checked against real hermes-agent core: 144 synthetic rows, 0 differences). OpenAI arm not run (no API key available) — bge-m3 only, per the maintainer's stated fallback.

## Results (hit@5 = recall@5, 44 labelled)
| coverage | L0 | ZC | ZK | FC | FK | gate ZC→ZK |
|---|---|---|---|---|---|---|
| full | 31 | 34 | 35 | 36 | 38 | b=1 c=0 p=1.0 FAIL (rescued B14:183) |
| half (kw 15) | 30 | 34 | 35 | 36 | 37 | b=1 c=0 p=1.0 FAIL |

Decomposition (full): embeddings L0→ZC +6.8pts (b=3 c=0 p=0.25); admission ZC→FC +4.5pts, by_meaning 2→18, confusion +2 (guard FAIL); keywords FC→FK +4.5pts (b=2: C2:198, C5:215), 0 lost, noise/confusion flat. The recall gain is dominated by the admission rule, not keywords — convergent with the maintainer's pilot reading.

## Files
- `opaque/real-bge-full-m54/`, `opaque/real-bge-half-m54/` — 270 rows each (54 queries × 5 cells). Fields: qid, category, lang, kind, ext, targets (fact IDs), keys/search_keys (fact IDs), hit/hit5, by_meaning (IDs), confused, noise flags, stamps (emb, coverage, seed, git_sha, stemmer, core, kw_n, tags_sha, vector_variant, admission). Verified: 0 CJK characters, 0 long strings, 0 text fields.
- `gate_report_real-bge-full-m54.md`, `gate_report_real-bge-half-m54.md`.

Privacy contact: the set author. Text stays local; only this card + opaque rows leave the machine.