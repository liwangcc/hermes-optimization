Title: tools: measure a lower recall margin whose facts a cross-encoder confirms

---

A measurement switch for #121, added the way `EMBED_TEXT` was added for #95. Nothing changes by default.

- **`embeddings.RECALL_CHECK_MARGIN`** (a module value, `None`). When it is set below `RECALL_MARGIN` and a cross-encoder is configured, the meaning stream admits at that margin, and a fact that does not stand out at `RECALL_MARGIN` is offered only when the cross-encoder scores it above the middle of `rerank_scale` (0 for `logit`, 0.5 for `unit`). A fact that stands out at `RECALL_MARGIN` is offered as before and is not asked about. With no endpoint the margin stays `RECALL_MARGIN`; a call that was not made, or failed, is a no for that fact.
- **`_recall_checker`, `_answers`**. The cross-encoder is the reranker when `rerank` is on; otherwise a `rerank.Rescorer` of its own on the same `rerank_*` keys, made on first use and only when `rerank_url` is set. `rerank` itself stays off, so the pool is not reordered. One question a turn at most: the closest fact that needs the check. The document sent is the fact as recall shows it (`_one_line`).
- **`rerank.Rescorer.scores(..., single=True)`** sends one document. Without it the single-document shortcut (`skipped_single`) is unchanged.
- **`tools/provenance_probe.py --recall-check-margin <v>`** sets the value for one run and puts it back. The run's stores get `rerank_url` and `rerank_scale` from `--endpoint` and `--rerank-scale` with rerank off. Every row carries `<v>` as `margin` and the recall margin as `margin_check` (`None` on a plain run); the file name gets `_c<v>`.
- **`tools/mcnemar_gate.py --pair margin`** names the check beside the proposal's margin and refuses a side whose rows carry two stamps. Rows written before the stamp existed read as none.

**Measured** with the probe on this branch, `--emb on --modes off --repeats 1`, the default against `--recall-check-margin 0.5`, both runs on one `--endpoint`:

| pool | hit@5 | b / c | p | noise | confused | gate |
|---|---:|---:|---:|---:|---:|---|
| multi (18 languages), contrast en / ru / zh, household test: 540 real | 480 → 486 | 6 / 0 | 0.031 | 93 → 93 | 34 → 34 | passes |
| the same plus household dev and `synthetic_zh`: 696 real | 565 → 573 | 8 / 0 | 0.008 | 142 → 142 | 46 → 46 | passes |

- Embeddings: bge-m3 behind a local `/v1/embeddings`. Cross-encoder: Qwen3-Reranker-0.6B behind a local `/v1/rerank` that answers the model's yes-minus-no logit for "the document alone supplies a concrete answer to the query, including the requested entity and attribute" (`--rerank-scale logit`).
- The margin at 0.5 without the check, same embeddings and sets: 10 / 0 on the first pool with noise 93 → 99. That run changes 26 of the 810 rows, which is how many turns have a fact to ask about.
- The rows (14 files) and the two gate reports are not in this branch. I can add them under `results/` or send them. They carry a `-dirty` `git_sha`: they were written from this patch before it was committed.
- A private store of 54 facts, same switch: nothing moves (34 of 44 both ways, noise 3, confusion 30; one question asked).
- Not measured: `text-embedding-3-small`. I have no key for it. A replay over the committed `m1` / `m0.5` rows with the same cross-encoder gives 6 / 0, noise 94 → 94, confusion 34 → 34 (#121).

**Tests**: 16 new in `tests/test_holographic_recall_check_margin.py`, 15 failing on `main` (the sixteenth is the control that a bare margin reads as before).

- Nothing is asked and nothing added by default; a fact between the margins enters on a yes; a no, a score at the middle of the scale and a failed call keep it out; one question a turn; the unit scale; a fact that stands out at `RECALL_MARGIN` is not asked about; without `rerank_url` the margin stays `RECALL_MARGIN`; the check uses the `rerank_*` keys with rerank off; one document is scored only when asked for.
- The probe stamps the checked margin, gives it a file of its own and puts the value back.
- The gate names the check, reads a bare margin as before and refuses checked and bare rows under one margin.

**Checked** on Windows 11, Python 3.11, against Hermes `main` at `152fe189`:

- The new file with `tests/test_mcnemar_gate.py`, `tests/test_holographic_provenance_recall_margin.py` and `tests/test_holographic_rerank_single.py`: 46 passed.
- Full suite: 3,709 passed, 16 skipped, 7 failed. The seven are in `tests/test_holographic_blas_threads.py` and fail the same way on an unchanged clone of `main` in this setup.
- `ruff check .` is clean.

**Not done**:

- No setting, no README entry in the configuration table: this is a module value for a measurement. If the gate passes on your model, whether it becomes a setting, and under what name, is yours to decide.
- One cross-encoder and one instruction. A general-purpose reranker's score above 0 means "relevant", which is a looser question than "answers it"; I have not measured one.
- The `rerank` on path (`_unified_stream`) reaches the same code through `_stream_extras`, but I measured only `--modes off`.
- `hermes plugins validate` not run; the patch adds no file outside `tests/` and no import.
- Version and CHANGELOG left to you. Not run on Linux or macOS; CI covers them.
