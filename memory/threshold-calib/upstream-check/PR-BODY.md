Title: RECALL_CHECK_MARGIN: a probe-only lower margin whose facts a check confirms (#121)

---

`RECALL_CHECK_MARGIN` as agreed in #121: a probe-only module value, unset by default. While it is unset nothing changes: no call is made and recall is what it was. A user-facing setting stays a separate decision after the result replicates.

## What it does

- **`embeddings.RECALL_CHECK_MARGIN`** (`None`). Set below `RECALL_MARGIN`, with `rerank` off, the meaning stream admits at that lower margin, and a fact that stands out there but not at `RECALL_MARGIN` enters only on the check's yes. One question a turn, about the closest such fact. A fact that stands out at `RECALL_MARGIN` enters as before, unasked.
- **One function, `recall_check.CHECK`**: `(message, fact) -> (verdict, raw score)`, where the verdict is `"yes"`, `"no"` or `"not_answered"`. `None`, the default, means `recall_check.cross_encoder` on the `rerank_*` keys, made on first use and only when `rerank_url` is set. A run swaps in another check by setting the value. Nothing in the plugin changes, and the swapped check needs no `rerank_url`:

  ```python
  # tools/your_checker.py
  import sys
  import provenance_probe as pp
  from hermes_plugin_holographic import recall_check

  def check(message: str, fact: str) -> tuple[str, float | None]:
      ...  # "yes", "no" or "not_answered", and the raw score

  recall_check.CHECK = check
  pp.main(sys.argv[1:])  # the flags of point 2; --check-model and --check-instruction name this checker
  ```

  `--endpoint` is stamped into every row and the head compares it, so give both arms the same one; your checker's address keeps the rows honest.
- `recall_check.ask` runs whichever check it is behind the screens of point 3. A check that raises, or answers anything but yes or no, counts as not answered.
- `rerank.Rescorer.scores(..., single=True)` sends the one document instead of taking the single-document shortcut.

The code is 8 files, +607 −27: the new test file is 378 of the added lines, the plugin itself 98 (`recall_check.py` 47, `__init__.py` 41, `embeddings.py` 5, `rerank.py` 5), `tools/` 118, README 13. A last commit adds only data: `results/issue121/`, with the rows, the gate reports, the instruction and a README.

## 1. Tests that fail without the change

`tests/test_holographic_recall_check_margin.py`, 28 cases:

| what you asked for | test |
|---|---|
| unset leaves recall as it is and makes zero checker calls | `test_unset_leaves_recall_as_it_is_and_makes_no_call` |
| an eligible turn makes exactly one call | `test_an_eligible_turn_makes_exactly_one_call`: two facts between the margins, one call about the closest, and after its no the other is not asked |
| accept | `test_a_yes_lets_the_fact_in` |
| reject | `test_a_no_keeps_the_fact_out` |
| a failed call keeps the baseline result | `test_a_failed_call_keeps_the_baseline_result`, three cases: not answered, a check that raises, an answer that is neither yes nor no. On a turn whose words show a block, the block is the one of the value unset |
| the guards of point 3 | `test_the_check_runs_with_rerank_off_only`, `test_the_screens_send_nothing` (five cases), `test_the_check_fits_the_prefetch_budget_with_the_embedding_call`, `test_a_slow_endpoint_costs_one_timeout_then_is_left_alone` |
| the swap | `test_a_run_can_swap_in_another_check` |
| the rows and the gate of point 2 | `test_the_probe_stamps_both_arms_and_names_their_files`, `test_the_probe_refuses_a_checked_arm_that_cannot_check` (three cases), `test_the_probe_records_each_turn_of_the_check`, `test_the_probe_stops_on_a_check_that_did_not_answer`, `test_the_gate_pairs_the_off_arm_with_the_checked_one`, `test_the_plain_pairs_refuse_runs_that_differ_in_check_margin`, `test_the_gate_refuses_a_checked_arm_it_cannot_name` (three cases) |
| one document scored | `test_one_document_is_scored_only_when_asked_for` |

On `main` (`ceb802b`) all 28 fail, each on the thing it names. The value and the provider's check are set with `raising=False`, so where behaviour can differ a test fails on its assertion, not in its setup:

- 10 fail on their assertion. The eligible turn makes no call. The yes does not let the fact in. The no and the three failures keep the block, but no question was asked. With rerank off no call is made. The probe's turn has no record and does not stop. `--pair margin` does not refuse.
- 18 fail because what they exercise does not exist on `main`: `embeddings.RECALL_CHECK_MARGIN` (the unset test), `recall_check` (the swap and the five screens), `_recall_checker` (the budget and the slow endpoint), `scores(single=)`, `--recall-check-margin` (the stamps and the three refusals; argparse exits 2) and `--pair check_margin` (four gate tests).

<details><summary>The failure on <code>main</code>, test by test</summary>

```
test_unset_leaves_recall_as_it_is_and_makes_no_call        AttributeError: module 'hermes_plugin_holographic.embeddings' has no attribute 'RECALL_CHECK_MARGIN'
test_an_eligible_turn_makes_exactly_one_call               AssertionError: assert ('' == '' and [] == [('Whereabout...he balcony.')]
test_a_yes_lets_the_fact_in                                AssertionError: assert False
test_a_no_keeps_the_fact_out                               AssertionError: assert ('' == '' and [] == [('Whereabout...he balcony.')]
test_a_failed_call_keeps_the_baseline_result (x3)          AssertionError: assert ('## Holograph...of year 2012.' == '## Holograph...of year 2012.' and [] == [('Which shel...he balcony.')])
test_the_check_runs_with_rerank_off_only                   assert 0 == 1
test_a_run_can_swap_in_another_check                       ModuleNotFoundError: No module named 'hermes_plugin_holographic.recall_check'
test_the_screens_send_nothing (x5)                         ModuleNotFoundError: No module named 'hermes_plugin_holographic.recall_check'
test_the_check_fits_the_prefetch_budget_with_the_...       AttributeError: 'HolographicMemoryProvider' object has no attribute '_recall_checker'
test_a_slow_endpoint_costs_one_timeout_then_is_left_alone  AttributeError: 'HolographicMemoryProvider' object has no attribute '_recall_checker'
test_one_document_is_scored_only_when_asked_for            TypeError: Rescorer.scores() got an unexpected keyword argument 'single'
test_the_probe_stamps_both_arms_and_names_their_files      SystemExit: 2
test_the_probe_refuses_a_checked_arm_that_cannot_check (x3) AssertionError: Regex pattern did not match. Actual message: '2' (argparse: unrecognized arguments)
test_the_probe_records_each_turn_of_the_check              KeyError: 'check'
test_the_probe_stops_on_a_check_that_did_not_answer        Failed: DID NOT RAISE <class 'SystemExit'>
test_the_gate_pairs_the_off_arm_with_the_checked_one       SystemExit: --pair margin|embed_text <files>
test_the_plain_pairs_refuse_runs_that_differ_in_check_...  Failed: DID NOT RAISE <class 'SystemExit'>
test_the_gate_refuses_a_checked_arm_it_cannot_name (x3)    AssertionError: Regex pattern did not match. Actual message: '--pair margin|embed_text <files>'
```

</details>

## 2. Rows anyone can re-pair

- Both arms keep the ordinary `margin`, 1.0 in every row. The new stamp is `check_margin`, `"off"` or the value, in every row and in the file name: `--recall-check-margin off` writes `provenance_<set>_coff_<emb>.jsonl`, `--recall-check-margin 0.5` writes `provenance_<set>_c0.5_<emb>.jsonl`. A run without the flag also writes `check_margin: "off"`, under its old file name. Adding `--recall-margin 1.0` to both arms puts the ordinary margin into the file names too (`_m1.0_coff`, `_m1.0_c0.5`); the rows carry it either way.
- `check_margin` joins `_HEAD`, so `--pair margin` and `--pair embed_text` refuse two runs that also differ in it. Rows written before the stamp existed read as `"off"`, so the committed `results/` pair as before.
- **This is how the patch pairs the two arms:** `--pair check_margin`. Its head is `_HEAD` with `margin` in place of `check_margin`, so the ordinary margin must be the same in both arms. It refuses a `-dirty` `git_sha`, and a checked arm that does not name exactly one checker and one instruction hash. The report adds the check's calls, outcomes and slowest time, and marks dev rows as reported beside the decisive pool, not deciding it.
- The checked arm's rows carry `check_model` (`--check-model`, also sent as `rerank_model`) and `check_instruction_sha256` (the sha256 of the bytes of `--check-instruction`). Every row carries the turn's `check_calls`, `check_outcome`, `check_score` and `check_ms` (point 3).
- All the rows below come from one commit, `31de6eb`, the last code commit of this branch, with nothing uncommitted. They are committed in `results/issue121/`, with the four gate reports; the commit after `31de6eb` adds only that folder, so a run at the branch head measures the same code.

The commands, with the two loopback endpoints of point 5 and `EMB_URL=http://127.0.0.1:12371/v1 EMB_MODEL=bge-m3`:

```bash
COMMON="--emb on --modes off --endpoint http://127.0.0.1:12372/v1/rerank --out rows"
CHECKED="--recall-check-margin 0.5 --check-model Qwen/Qwen3-Reranker-0.6B --check-instruction instruction.txt"
for set in "multi --langs ar,bn,de,en,es,fr,hi,id,it,ja,ko,nl,pl,pt,ru,th,tr,zh" contrast_en contrast_ru contrast_zh \
           "household --split test" "household --split dev" synthetic_zh; do
  python tools/provenance_probe.py $COMMON --set $set --recall-check-margin off
  python tools/provenance_probe.py $COMMON --set $set $CHECKED
done
# the decisive pool: the test split and the sets without a split
python tools/mcnemar_gate.py --pair check_margin rows/provenance_{multi,contrast_en,contrast_ru,contrast_zh,household_test}_{coff,c0.5}_on.jsonl
# beside it: the same with household dev and synthetic_zh, then dev alone
python tools/mcnemar_gate.py --pair check_margin rows/provenance_{multi,contrast_en,contrast_ru,contrast_zh,household_test,household_dev,synthetic_zh}_{coff,c0.5}_on.jsonl
python tools/mcnemar_gate.py --pair check_margin rows/provenance_household_dev_{coff,c0.5}_on.jsonl
```

`instruction.txt` holds the instruction of point 5 and nothing else, with no newline at the end; it is committed as `results/issue121/instruction.txt`. To replay the gate on the committed rows, without a server or a key, run the same gate commands with `results/issue121/` in place of `rows/`.

## 3. The cost stays bounded

- **One timeout.** The default check is a `rerank.Rescorer` on `rerank.Settings(config)`, so it waits `rerank_timeout` at most, and `Settings` fits that with `embedding_timeout` under the prefetch budget (`_PREFETCH_BUDGET_S`, 7.5 s). At `embedding_timeout` 6 and `rerank_timeout` 10 the check gets 1.5 s (a test pins this). One call a turn at most.
- **The pause after a failure.** The same client pauses for 60 s, doubling to 900 s. A slow endpoint costs one timeout, then gets no request until the pause ends (a test).
- **The screens**, before any call and for any check. Nothing is sent, and the fact stays out (`skipped_secret`, `skipped_long`), when the message or the fact looks secret (`_secret_in`, `_sendable`; the whole fact, not only the line recall shows), when the message is over `RERANK_MAX_QUERY_CHARS` (500), or when the pair is over `RERANK_PAIR_CHARS` (1000). The fact sent is `_one_line`, at most 300 characters, so with the message under 500 the pair limit already holds; the screen stays for a check that is called some other way.
- **With `rerank` on the check does not run**, and the value changes nothing there: no call, and the margin stays `RECALL_MARGIN`. The rerank stage already spends the turn's call to that endpoint inside the budget, and a second call is not in it.
- **The rows** report each turn's calls, outcome, raw score and time, also on turns that show nothing. On the run below each arm has 1,068 turns. The off arm made 0 calls. The checked arm made 46, 22 of them on turns that showed nothing: 11 yes, 35 no, 0 not answered. The check took 101 ms at the median and 171 ms at most; the slowest turn took 232 ms, against 81 ms with the check off. A check that does not answer stops the probe run, as a failed rerank call does.
- **The docs line**, in the README paragraph beside the `RECALL_MARGIN` gate: "With the value set, the message and one fact go to the checker's endpoint, which gets nothing today while rerank is off."

## 4. What it was measured on

bge-m3 for the embeddings, with `Qwen3-Reranker-0.6B` as the check. The margin 0.5, the rule (one question a turn, yes above the middle of the scale) and the instruction were all chosen on these same question sets, so the p values are exploratory. A run on a second model with everything frozen is a replication: that is your `text-embedding-3-small` run. Confirmation needs questions they were not chosen on.

From `31de6eb`, `--emb on --modes off`, both arms on one `--endpoint`:

| pool | hit@5 | b / c | exact McNemar p | noise | confusion | `--pair check_margin` |
|---|---|---|---|---|---|---|
| decisive: multi (18 languages), contrast en / ru / zh, household test: 540 real | 480 → 486 | 6 / 0 | 0.031 | 93 → 93 | 34 → 34 | passes |
| beside: the same with household dev and `synthetic_zh`: 696 real | 565 → 573 | 8 / 0 | 0.008 | 142 → 142 | 46 → 46 | passes |
| beside: household dev alone: 120 real | 74 → 76 | 2 / 0 | 0.5 | 48 → 48 | 7 → 7 | does not pass (p) |
| beside: `synthetic_zh` alone: 36 real | 11 → 11 | 0 / 0 | 1 | 1 → 1 | 5 → 5 | does not pass (p) |

- These are the numbers posted in #121. Those rows were written before the patch was committed (`-dirty`). Row by row, three multi rows differ, all because 0.31.3 and 0.31.4 renamed the people of the corpus, and none of them moves the gate's counts. `hi` q7 shows one fact fewer in both arms. In `it` and `ko` q14 ("how should I answer Leon?") the check now says yes to the target, which both arms already show by the name.
- What the check said on the decisive pool: 29 calls. 9 yes: the 6 rescued targets; the target of `it` and `ko` q14 again; and one more fact about the same person on a question whose target is already shown (household zh q051). 20 no, 7 of them on chit-chat, among them `contrast_ru` c17 and c31, the two turns A let in. None not answered.
- A second run of both arms from the same commit wrote the same rows: every check call, verdict, raw score and shown fact identical, only the times differ.
- Six rescues is the gate's minimum on the decisive pool: one fewer and it fails.
- Not rerun on this commit, from #121: 0.5 without the check gave 10 / 0 on the decisive pool, with noise 93 → 99. A private store of 54 facts did not move, with one question asked.

## 5. So you can repeat the run

The embeddings and the check run behind two loopback servers of mine. They are not in this PR; the scoring is short enough to give here.

- Embeddings: `BAAI/bge-m3` through sentence-transformers 5.5.0, fp16 on CUDA, unit vectors, at `/v1/embeddings`. `pytorch_model.bin` sha256 `b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38`.
- Check: `Qwen/Qwen3-Reranker-0.6B` through transformers 5.8.1 (`AutoModelForCausalLM`, bf16 on CUDA), at `/v1/rerank`, answering in the Cohere shape. `model.safetensors` sha256 `27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b`.
- Python 3.11.4, torch 2.11.0+cu128, an RTX 4060 Laptop GPU. I did not record the Hugging Face revisions; the sha256 values above can be compared with the LFS hashes on the model pages.
- The instruction, exactly: 186 bytes, no newline at the end, sha256 `5336bc93ae7c30960c4f5940de5a98826fe2ecee05c549a846897344d7b73b72`.

  > Decide whether the document alone supplies a concrete answer to the query, including the requested entity and attribute. A shared topic without the requested information is insufficient.

- The pair format is the model card's, with that instruction. The query is the message as the plugin hands it to recall (the person's own words, at most 4,000 characters). The document is the fact as recall shows it (`_one_line`: whitespace collapsed, at most 300 characters). The score is the logit of "yes" minus the logit of "no" at the last position:

  ```python
  PREFIX = ('<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct '
            'provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n')
  SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'

  def score(model, tokenizer, instruction, query, document):  # what the server answers as relevance_score
      text = f'<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {document}'
      ids = (tokenizer.encode(PREFIX, add_special_tokens=False) + tokenizer.encode(text, add_special_tokens=False)
             + tokenizer.encode(SUFFIX, add_special_tokens=False))
      with torch.inference_mode():
          logits = model(input_ids=torch.tensor([ids], device=model.device), use_cache=False,
                         logits_to_keep=1).logits[0, -1].float()
      yes, no = tokenizer.convert_tokens_to_ids(['yes', 'no'])
      return (logits[yes] - logits[no]).item()
  ```

  A pair longer than the model's context is answered as -100, a plain no; none of these sets has one.
- Score to verdict: `rerank_scale: logit`, so the middle is 0, and the verdict is yes when the score is above 0.
- One synthetic request and response each way. The body is the one `rerank.Rescorer.scores` sends with `single=True`:

  ```
  request:  {"model": "Qwen/Qwen3-Reranker-0.6B", "query": "Where is the spare key?", "documents": ["The spare key hangs behind the blue flowerpot on the balcony."], "top_n": 40}
  response: {"model": "Qwen/Qwen3-Reranker-0.6B", "results": [{"index": 0, "relevance_score": 5.25}]}
  recall_check.cross_encoder -> ("yes", 5.25)

  request:  {"model": "Qwen/Qwen3-Reranker-0.6B", "query": "Where is the spare key?", "documents": ["The spare bulb lies behind the green bucket in the cellar."], "top_n": 40}
  response: {"model": "Qwen/Qwen3-Reranker-0.6B", "results": [{"index": 0, "relevance_score": -0.9375}]}
  recall_check.cross_encoder -> ("no", -0.9375)
  ```

- The rows (14 files, 2,136 rows, only your public sets), the four gate reports and the instruction are in `results/issue121/`.

## Checked

On Windows 11 with Python 3.11.4. The core is a checkout of Hermes `main` at `152fe189` that carries unrelated local changes; both runs below used the same one.

- The new file: 28 passed. On `main`, all 28 fail as listed under 1.
- With `test_mcnemar_gate.py`, `test_holographic_provenance_recall_margin.py`, `test_holographic_rerank_single.py`, `test_issue95_tools.py` and `test_holographic_provenance_classify.py`: 96 passed.
- Full suite: 3,830 passed, 16 skipped, 7 failed; on an unchanged `main`, 3,802 passed, 16 skipped, 7 failed. The 7 are the same tests in `tests/test_holographic_blas_threads.py` on both, and the 28 more passes are the new file.
- `ruff check .` (0.15.22) is clean.
- The committed rows of `results/issue95/` give the same `--pair embed_text` report on this branch as on `main`: rows without the new stamp read as `"off"`.
- The probe's budget set (`--set budget`, no embeddings and no rerank) writes the same 160 rows on this branch as on `main`, apart from times. `--recall-check-margin 0.5` refuses it, because the check needs embeddings.

## Not in this PR

- No setting and no entry in the configuration table: it is a module value for a measurement.
- Nothing OpenAI-specific, and nothing about `embedding_min_score` or a floor (B).
- Version and CHANGELOG are yours. Not run on Linux or macOS; CI covers them. `hermes plugins validate` was not run; the PR adds one module, `recall_check.py`, and no dependency.

Seven commits: six code commits in revertible steps (the wiring, the one-function interface, the guards, the rows and the gate, the tests, the README), then the data. Merging them as they are, rather than squashing, keeps each step revertible and keeps `31de6eb`, the commit the rows name, in your history.
