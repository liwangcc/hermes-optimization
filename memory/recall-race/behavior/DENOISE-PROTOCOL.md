# Catalog pointer denoising — offline protocol (v1)

Date: 2026-11-24. Status: frozen before any model call for this question.

## Decision question

Does the user's proposal — score catalog pointers with the query vector and inject only relevant pointers — reduce irrelevant catalog context, and what does it cost in missed-target recovery and model behavior?

This is separate from the race referee's retrieval `noise_rows/confused_rows`, which score only automatic-retrieval output keys and do not count catalog entries.

## Fixed inputs

- Official frozen synthetic pack, single-store scope: 818 rows, 460 answerable rows, 358 no-target rows (322 chit).
- Big-probe scope: 693 rows, 360 answerable, 333 no-target (297 chit).
- Automatic recall frozen at production shape: cap=9, semantic tau=0.55; every arm receives exactly the same D0 keys.
- Catalog budget=3500 approx tokens. Pointer scorer is frozen bge-m3 cosine(query, content+tags), the existing C4 mechanism. No evaluation labels are read by candidate construction.
- Full-label baseline is the exact race `referee.full_catalog` under the same budget. Static compressed baseline uses installed-plugin label logic at 8 tokens.

## Offline arms already replayed

- full30, static8
- vector thresholds .30/.35/.40/.45/.50/.55
- top 1/3/5/10/20
- vector .35/.40/.45 + 8-token labels; vector .40 + 12-token labels
- greeting/worth-asking guard + vector .35/.40/.45

Offline metrics: total/non-target pointer entries and line tokens; no-target/chit rows with any pointer; all target and missed-target visibility; exact lost target IDs. These are structural measurements, not claims about model attention.

## Real-model arms (bounded)

Five arms, same questions and same D0 recall:
1. `full30`: current full-label catalog baseline.
2. `static8`: full static catalog, compressed labels.
3. `vec45`: user's originally frozen filter, full labels.
4. `vec40_lab8`: wider filter + compressed labels; offline preserves 44/44 missed targets.
5. `top10`: fixed-size vector ranking; offline preserves 44/44 missed targets in single scope.

Question set: all 43 production-shape missed-target questions + 43 matched clean controls + 30 no-target rows (15 chit, 15 real/no-answer), selected deterministically to match the missed-question language distribution where possible. Total 116 questions × 5 arms = 580 logical conversations maximum. Each conversation allows at most 3 model requests (initial + at most two tool follow-ups), zero automatic retries. Hard cap 1,740 HTTP dispatches; actual count expected lower. Workers=3 to leave headroom on the shared endpoint. Stop on first HTTP/auth/transport failure or any malformed tool contract; preserve completed receipts and report partial results. A third response that still requests tools is a valid bounded behavioral outcome (`no_final_answer_tool_budget`): fetch metrics remain scoreable, final-answer quality is unavailable, and it does not trigger transport-failure stopping. No production config changes.

The model sees only `fact_store get`, not search/probe, so the test isolates the catalog route. It is not told that a target was missed or that it must call the tool.

## Primary outcomes

- Missed questions: correct missed-target ID fetched; all missed targets fetched; answer contains a distinctive target payload token after fetching.
- Controls: redundant fetch of already injected target; non-target fetches.
- No-target rows: any fact fetched (false-positive behavior), non-target fetch count.
- Across all rows: irrelevant gets, total calls/rounds, completion rate, latency, raw prompt/completion/cached/reasoning usage when returned.

Catalog structural noise is reported separately from behavioral noise. A reduction in listed pointers is not called a model-behavior improvement unless gets/answers improve.

## Cost/cache accounting

Every HTTP dispatch gets one receipt with arm/qid/round, request SHA, timestamps, HTTP status, response ID/model, finish reason, raw usage and parsed output/tool calls. Missing usage is unknown, never zero. Dynamic catalogs are not credited with static prompt-cache pricing. The first probe is run alone and inspected before the batch continues.

## Interpretation limits

- Single-store is the primary production-like scope; big scope is offline stress evidence unless a later authorized model run tests it.
- Synthetic official facts have equal trust. Results do not establish trust-order effects.
- `payload_any_hit` is a transparent secondary heuristic, not a human semantic grade. Objective fetch behavior is primary; low-score/high-score samples are retained for audit.
- The tested vector filter uses content+tags, exactly the prior C4 implementation. Label-vector scoring is a different hypothesis and is not silently substituted.