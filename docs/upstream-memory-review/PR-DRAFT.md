# Upstream PR drafts: Hermes and Holographic

PR bodies for after maintainer feedback. For the three Issue drafts, start with [`ISSUES.md`](ISSUES.md). The order, the reasons and the commands are in [`SUBMISSION.md`](SUBMISSION.md) (Chinese).
Each Hermes PR is one patch in [`patches/`](patches/), made against upstream `main` at `152fe189` (2026-11-19, the
catalog pins holographic 0.30.0); [`hermes-agent-memory-review.patch`](hermes-agent-memory-review.patch) is all seven
as one file.

The public reference adapter is `liwangcc/hermes-optimization@c4d265b`
(`memory/plugin/holographic-semantic/`, version 0.5.0). Use that fixed commit in cross-references, not the moving
`main`. The release snapshot is not a PR slice: the patches below still target the latest upstream `main` and must be
rebased before posting.

| PR | Patch | Discussion | Needs first | Files | Lines |
|---|---|---|---|---|---|
| 1 | `01-profile-families.patch` | none yet | — | 3 | +29 −15 |
| 2 | `02-composer-offers.patch` | none yet | — | 3 | +86 −19 |
| 3 | `03-memory-capacity.patch` | #5320 (a comment) | — | 35 | +1006 −19 |
| 4 | `04-memory-checkup.patch` | #78307 | PR 3 | 42 | +2317 −6 |
| 5 | `05-checkup-reminder.patch` | none yet | PRs 1, 2, 4 | 23 | +991 −16 |
| 6 | `06-catalog-suggestion.patch` | none yet | PRs 3, 4 | 18 | +133 −22 |
| 7 | `07-memory-provider-jobs.patch` | Issue B | — (made on `main`) | 31 | +996 −13 |

Line counts include tests, docs, 9 locales and the generated key list. PR 7 touches no file PRs 1–6 create; after
PR 4 has merged, its route ledger is regenerated (`scripts/gen_serve_handler_ledger.py`), the one generated file both
change. Screenshot names below refer to the testkit’s generated output; inspect the images before attaching them. Replace `#ISSUE-B`, `#PR1` … `#PR7` and `#HOLO-…` with the real links once they exist.

There is no Issue A of our own. PR 3 refers to the existing #5320 and PR 4 to #78307, and neither closes it.
`#ISSUE-TBD` in the deferred PRs 1, 2, 5 and 6 stands for a discussion that does not exist yet: settle it when
one of them is taken up, and never replace it with #5320.

---

[Comment draft for #5320: usage against the write limit](issues/A-capacity.md)

## PR 1 — `refactor(desktop): move the profile-keyed storage families out of session-states.ts`

Branch: `refactor/desktop-profile-families`. Commit message: the title, then
`dropTilesForProfile / migrateTilesForProfile delegate the sibling families to store/profile-families.ts.`

### What does this PR do?

`dropTilesForProfile` and `migrateTilesForProfile` also drop or move three sibling localStorage families (the
preview rail's tabs, the browser profile prefs, the queued launch pick). They move, unchanged, into
`store/profile-families.ts` (`dropProfileFamilies`, `migrateProfileFamilies`), and `session-states.ts` calls them.
`session-states.ts` is past the 2,000-line cap, so a new family could not be added there; the next one (the memory
checkup reminder, #PR5) joins `profile-families.ts`. No behaviour change. `apps/desktop/AGENTS.md` names the new
home.

### Related Issue

Refs #ISSUE-TBD (the checkup reminder's discussion). Prepares #PR5.

### Type of Change

- [x] ♻️ Refactor (no behavior change)

### Changes Made

- `apps/desktop/src/store/profile-families.ts` (new): the three families' drop and migrate calls, as they were.
- `apps/desktop/src/store/session-states.ts`: calls them (3,084 → 3,073 lines).
- `apps/desktop/AGENTS.md`: a new family joins `migrateProfileFamilies` and `dropProfileFamilies`.

### How to Test

```bash
cd apps/desktop
pnpm exec vitest run src/store/session-states.test.ts src/store/session-states-profile-rename.test.ts \
  src/store/session-tiles-connection-scope.test.ts src/store/composer-queued-pick.test.ts \
  src/store/preview-status-edge-cases.test.ts src/store/preview-status-lifecycle.test.ts \
  src/lib/browser-profile-prefs.test.ts src/lib/browser-desktop-bridge-saved-connections.test.ts \
  src/sdk/profile-routing.test.ts src/sdk/open-session-refresh-in-place.test.ts \
  src/app/profiles/rename-profile-dialog.test.tsx
pnpm run typecheck
```

Result: 11 files, 210 tests passed; typecheck clean; eslint clean; `scripts/check --staged` code health 0 blocking.

Tested on: Windows 11 (Node 26.12.1, pnpm 12.15.0).

---

## PR 2 — `refactor(desktop): pick the composer's one offer from a table`

Branch: `refactor/desktop-composer-offers`.

### What does this PR do?

`ComposerStatusStack` decides which single offer (the free-tier notice, then the shared-metrics question) owns the
composer's offer slot with a branch per offer. That decision moves into `status-stack/offers.tsx` as an ordered table
and a `useComposerOffer()` hook, so the next offer is a row instead of another branch on a function at its complexity
cap (root AGENTS.md: table-driven dispatch). Same order, same single owner across composers, no behaviour change.

### Related Issue

Refs #ISSUE-TBD (the checkup reminder's discussion). Prepares #PR5.

### Type of Change

- [x] ♻️ Refactor (no behavior change)

### Changes Made

- `apps/desktop/src/app/chat/composer/status-stack/offers.tsx` (new): `OFFERS` in offer order, `useComposerOffer()`.
- `apps/desktop/src/app/chat/composer/status-stack/index.tsx`: uses it.
- `offers.test.tsx` (new): one offer at a time, the metrics question waits for the free-tier notice, a non-owning
  composer shows none.

### How to Test

```bash
cd apps/desktop && pnpm exec vitest run src/app/chat/composer/status-stack && pnpm run typecheck
```

Result: 15 files, 42 tests passed; typecheck clean; code health 0 blocking. Tested on: Windows 11.

---

## PR 3 — `feat(memory): show memory capacity by layer`

Branch: `feat/memory-capacity-by-layer`.

### What does this PR do?

`GET /api/memory` gains `layers`, and the Desktop shows it in the existing Memory Layers summary (Settings → Memory &
Context, and Command Center → Maintenance):

- `USER.md` and `MEMORY.md`: entries and characters against the cap Hermes enforces, counted by
  `tools.memory_tool.builtin_memory_layers()` with the same parse, de-duplication and join the store uses when it
  refuses a write. A pure read: no directory is created, nothing is logged or scanned.
- The provider's store: whatever the new optional `MemoryProvider.usage_report(hermes_home)` returns: `items`,
  `storage_bytes`, and `budgets` the provider itself enforces, in its own unit. The default `{}` means *not reported*.
- Each layer has a `state`: `ok`, `empty`, `disabled`, `unavailable` (could not be read, or the provider raised) or
  `unsupported`. The UI never shows "0" for any of the last four.

Only enforced limits get a meter and a percentage. A provider's store has no ceiling, so it shows a count and a size.
A provider budget is labelled as the provider's own estimate, not model input or billing. No new route; the old keys
of `GET /api/memory` are unchanged, so the web dashboard and older clients read what they read today, and a newer
Desktop on a backend without `layers` says "This Hermes version does not report memory usage. Update Hermes to see
it." instead of showing zeros. With no provider, or one that does not implement the read, the two built-in rows
still work.

`usage_report` follows the existing contract for provider reads outside a session (`read_config_fields`,
`backup_paths`): an uninitialized instance, `hermes_home` passed in, no network, JSON values, a default on the ABC. It
is called through `load_memory_provider(name, register_skills=False)` inside a `try`.

### Related Issue

Refs #5320: the usage-visibility part only. It does not close that issue.

### Type of Change

- [x] ✨ New feature (non-breaking change that adds functionality)

### Changes Made

- `agent/memory_provider.py`: `usage_report()` with default `{}`.
- `tools/memory_tool.py`: `builtin_memory_layers(config)`.
- `hermes_cli/web_routers/memory_layers.py` (new): `memory_layers()`, the per-layer state, provider read and budget
  validation; `ops.py` adds it to `GET /api/memory`.
- Desktop: `types/memory-layers.ts`, `settings/memory/memory-capacity.tsx` (rows; `formatBytes` moves here from
  `maintenance.tsx`), `memory-layers.tsx`, the `memoryCapacity` copy in 9 locales, `locales/_keys.desktop.json`.
- Docs: memory provider plugin guide, memory feature page, dashboard REST table.

### How to Test

```bash
scripts/run_tests.sh tests/hermes_cli/test_web_memory_layers.py
cd apps/desktop && pnpm exec vitest run src/app/settings/memory src/app/command-center src/i18n scripts/i18n-keys.test.mjs
pnpm run typecheck
```

`test_web_memory_layers.py` runs a real temp `HERMES_HOME` with synthetic `USER.md` / `MEMORY.md` and a synthetic
provider plugin loaded through real discovery: capacity equals what the store enforces (not the file size), off /
empty / unreadable / unsupported / unloadable are distinct, a budget without numbers is dropped, and two profiles
report their own layers.

Results: backend 6 passed, and 14 neighbouring files (memory endpoints, provider seams incl. hosted, plugin docs
imports, route ledger, docs drift, profile scope, `test_web_server.py`) pass except
`tests/tools/test_memory_tool.py::TestMemoryFileLockPermissions` ×2, which fail identically on untouched `main` on
native Windows (POSIX mode bits on NTFS). Desktop 20 files, 117 tests passed; key registry 2 passed; typecheck clean;
eslint 0 errors; code health 0 blocking.

Tested on: Windows 11 (Python 3.14.9, Node 26.12.1).

### Screenshots

`screenshots/2-capacity.png` (real Desktop, the `holographic-semantic` adapter over synthetic memory).

---

## PR 4 — `feat(memory): a read-only memory checkup the user starts`

Branch: `feat/memory-checkup`. Needs #PR3.

### What does this PR do?

Command Center → Maintenance gains **Memory checkup → Review now**. It calls `POST /api/memory/checkup`, which makes
one `agent.auxiliary_client.call_llm(task="memory_checkup", ...)` with **no tools**: no agent, no memory store, no tool
dispatch, no session, so no `sync_turn` and no background review follows it. It cannot write by construction, not by
prompt. `memory_checkup` is an unconfigured auxiliary task and resolves to the profile's main model (the
`side_question` precedent).

It reads `USER.md`, `MEMORY.md` and the provider's items through the new optional
`MemoryProvider.review_items(hermes_home)` (default `{}` = not supported), and returns proposals by layer: changes
that stand (update / merge / remove), *needs evidence*, and keep.

Rules enforced in `agent/memory_checkup.py` on the reply:

| Rule | Effect |
|---|---|
| Unknown target, undefined action, a second verdict on one entry | dropped, counted in `dropped` |
| The user protected the item | no removal and no rewrite is proposed |
| The item is under 7 days old | no removal, and it cannot be folded away by a merge; a rewrite is allowed |
| `remove` on the basis `unused` | never stands |
| `remove` as duplicate / superseded / contradicted | must name the other entry |
| No evidence, or a rewrite without the new text | does not stand |

A proposal that breaks a rule is kept under *needs evidence* with the reason. Review order is a weight, never a
verdict: `0.5 × (1 − score) + 0.3 × unconfirmed + 0.2 × idle` (idle = never recalled and 30+ days old). The order
decides which items fit the input budget (60,000 characters of item text) and the response reports reviewed / total.

A failed model call is HTTP 503 naming the cause and "nothing was changed"; a reply that is not the review is 502.
Neither is shown as an empty review, and there is no fallback to a chat session. With more than one profile served the
route requires an explicit `profile`, like the other routes that send one profile's data somewhere. A newer Desktop
on a backend without the route reads its 404 with the existing `isMissingRestEndpoint` (the route has no path params,
so a 404 can mean nothing else) and says "This Hermes version has no memory checkup. Update Hermes to use it.", with
no retry: a missing capability is not a transient failure.

*Add selected to chat* puts the ticked changes in the composer as a request; the agent makes them with its normal
memory tools after the user sends it, under `memory.write_approval`. There is no client API to stage a write, and
adding one would overlap #131600.

### Related Issue

Refs #78307. Builds on #PR3.

### Type of Change

- [x] ✨ New feature (non-breaking change that adds functionality)

### Changes Made

- `agent/memory_checkup.py` (new): what the call reads, the prompt, and which proposals stand.
- `agent/memory_provider.py`: `review_items()` with default `{}`.
- `hermes_cli/web_routers/memory_checkup.py` (new): `POST /api/memory/checkup`; registered in `web_server.py`;
  `serve_handler_ledger.json` regenerated.
- Desktop: `command-center/memory-checkup.tsx` (panel), `store/memory-checkup.ts` (the run, per connection and
  profile), `lib/memory-checkup-request.ts`, `api/system.ts`, `types/memory-checkup.ts`, the route in
  `electron/connection-config.ts`, the `memoryCheckup` copy in 9 locales.
- Docs: plugin guide (`review_items`), memory feature page, dashboard REST table.

### How to Test

```bash
scripts/run_tests.sh tests/agent/test_memory_checkup.py tests/hermes_cli/test_web_memory_checkup.py \
  tests/hermes_cli/test_serve_handler_ledger.py
cd apps/desktop
pnpm exec vitest run src/app/command-center src/store/memory-checkup.test.ts src/app/settings/memory src/i18n \
  scripts/i18n-keys.test.mjs
pnpm exec vitest run --project electron electron/connection-config.test.ts
pnpm run build && pnpm exec playwright test e2e/memory-checkup.spec.ts
```

Every backend test that runs the checkup hashes the memory files, `pending/` and the provider's data before and after.
The e2e runs real Electron, a real `hermes serve` and a provider plugin loaded through real discovery from a sandbox
home; only the model is the repository's mock server.

Results: backend 10 files, 102 tests passed (with neighbours); desktop 23 files, 126 tests passed (including an older
backend's 404); electron connection-config 126 passed; e2e passed; typecheck clean; eslint 0 errors; code health 0
blocking.

Not exercised: a real model. The path down to the HTTP call is real; the reply is scripted, so how well a given
model follows the format is not measured. A reply that does not parse is a visible 502.

Tested on: Windows 11.

### Screenshots

`screenshots/3-proposals.png`, `screenshots/4-facts.png`.

---

## PR 5 — `feat(desktop): an opt-in reminder for the memory checkup`

Branch: `feat/desktop-memory-checkup-reminder`. Needs #PR1, #PR2, #PR4.

### What does this PR do?

**Remind me to review** in the Memory checkup panel, off by default. Turned on, every 10 or 14 days (14 by default)
one strip appears above the composer: *Review now* / *Next time*.

- A clock in `localStorage`, keyed by connection and profile, like the MCP health snooze. No cron job, no background
  model turn, nothing in the system prompt, no backend change.
- A due reminder becomes pending once, however many intervals passed while the app was closed.
- The next interval starts when the strip has been on screen for a second (a strip another offer displaces at boot
  does not count), not when it became due and not when a checkup completes.
- The read is fresh from storage each time, so a rerender, a reload or a second window changes nothing; a `storage`
  event carries an answer to the other windows.
- It takes the composer's single offer slot last, behind the free-tier notice and the shared-metrics question (one
  row in the table from #PR2).
- *Next time* only clears it. *Review now*, on the strip or in Maintenance, clears it and starts the one checkup.
- A renamed profile's clock moves with it and a deleted profile's clock is dropped (`profile-families.ts`, #PR1).

Known limit: `localStorage` has no cross-window transaction; two windows that first show the reminder within the same
few milliseconds both write a due date a moment apart. They never replay a cycle.

### Related Issue

Refs #ISSUE-TBD (the checkup reminder's discussion).

### Type of Change

- [x] ✨ New feature (non-breaking change that adds functionality)

### Changes Made

- `store/memory-checkup-reminder.ts` (new): the clock; started in `use-desktop-integrations.ts`.
- `components/memory-checkup/reminder-strip.tsx` (new), one row in `status-stack/offers.tsx`.
- `command-center/memory-checkup.tsx`: the opt-in and interval; *Review now* answers a waiting reminder.
- `store/profile-families.ts`: the reminder joins the families.
- Reminder copy in 9 locales; memory feature page.

### How to Test

```bash
cd apps/desktop
pnpm exec vitest run src/store/memory-checkup-reminder.test.ts src/components/memory-checkup \
  src/app/command-center src/app/chat/composer/status-stack
pnpm run build && pnpm exec playwright test e2e/memory-checkup.spec.ts e2e/boot.spec.ts
```

Reminder tests use a fake clock: due while closed shows one reminder; restart, rerender and a second window do not
move the clock; *Next time* makes no model call; one clock per connection and profile; nothing before the gateway says
which profile is in view; rename and delete.

Results: 40 files, 184 tests passed; profile-family tests 11 files, 210 passed; e2e passed 3 of 3 with
`--repeat-each=3`; `e2e/boot.spec.ts` passes; typecheck clean; `pnpm run lint` 0 errors (its warnings are all in files
this change does not touch); code health 0 blocking.

Tested on: Windows 11. macOS and Linux not run.

### Screenshots

`screenshots/1-reminder.png`.

---

## PR 6 — `feat(desktop): say when a provider's catalog makes MEMORY.md optional`

Branch: `feat/memory-catalog-suggestion`. Needs #PR3 (code) and #PR4 (its doc lines extend text #PR4 adds).

### What does this PR do?

A provider may keep a catalog of its stored facts in every session's system prompt. With that catalog on,
`MEMORY.md` as an index of the same facts only repeats them, but nothing tells the user, and nothing says what each
costs. This lets the provider say so, and the capacity view pass it on:

- A budget in `usage_report` may name the built-in files its text overlaps: `"overlaps": ["memory"]` (only
  `"memory"` and `"user"` are kept).
- Each built-in layer in `GET /api/memory` gains `tokens`: what its loaded text costs a session, by core's
  `estimate_tokens_rough` (CJK-aware), next to the character count the cap is measured in.
- While the budget is on and the overlapped file is on and holds something, the capacity view adds one row under the
  budget: "MEMORY.md is optional while Fact catalog is on", with the file's estimated tokens per session; the
  budget's own row above already shows the catalog's.

It only suggests: no button switches anything off, the user decides under Memory & Context, and both may stay on.
A backend without `tokens` gets the same row without the number.

### Related Issue

Refs #ISSUE-TBD. Builds on #PR3.

### Type of Change

- [x] ✨ New feature (non-breaking change that adds functionality)

### Changes Made

- `hermes_cli/web_routers/memory_layers.py`: `overlaps` kept on a budget; `tokens` on each built-in layer.
- Desktop: `memory-capacity.tsx` (the suggestion row), `types/memory-layers.ts`, two strings in 9 locales.
- Docs: plugin guide (`overlaps`), memory feature page.

### How to Test

```bash
scripts/run_tests.sh tests/hermes_cli/test_web_memory_layers.py tests/hermes_cli/test_web_memory_checkup.py
cd apps/desktop && pnpm exec vitest run src/app/settings/memory src/i18n scripts/i18n-keys.test.mjs
```

Results: backend 12 passed (capacity and checkup files); desktop 18 files, 111 tests passed, including: shown with
the file's tokens; not shown while `MEMORY.md` is off or empty or the catalog is off; no button or switch in the row.

Tested on: Windows 11.

### Screenshots

`screenshots/6-catalog-suggestion.png` (real Desktop, the `holographic-semantic` adapter with `MEMORY.md` on).

---

[Issue B draft: provider maintenance jobs](issues/B-provider-jobs.md)

## PR 7 — `feat(memory): run a memory provider's maintenance jobs from the Desktop`

Branch: `feat/memory-provider-jobs`. Made on `main`; independent of PRs 1–6.

### What does this PR do?

Lets a memory provider offer one-click jobs for its store, such as building a search index for the facts it already
holds after an embedding model is configured, and lets the Desktop run them under the provider's settings and show
how they went. See #ISSUE-B for the why.

- `agent/memory_provider.py`: `maintenance_actions(hermes_home)` (default `[]`) and
  `run_maintenance_step(action_id, hermes_home)` (default: no such job). JSON values only.
- `hermes_cli/memory_actions.py`: lists a provider's jobs (malformed entries and ids are dropped; `disabled`,
  `unavailable`, `unsupported` and `ok` are different answers) and runs one to the end, printing each status
  (`hermes memory action [<id>]`). Exit code: 0 done, 1 failed or not ready, 2 no such job.
- `hermes_cli/web_routers/memory_actions.py`: `GET /api/memory/actions`; `POST /api/memory/actions` validates the id,
  refuses a job that is not listed (404), not ready or already running (409), and names its profile like the other
  routes that write a profile's data; then spawns the CLI as the `memory-action` action.
- Desktop: `settings/memory/provider-jobs.tsx` under the provider config panel (also for a provider with no fields),
  `api/memory-jobs.ts`, the routes in `electron/connection-config.ts` beside the other action-spawning route, strings
  in the existing `memoryLayers` copy of 9 locales. A Hermes without the route shows no section.
- Docs: plugin guide (Maintenance jobs, Setup UX table), memory providers page, dashboard REST table.

### Related Issue

Closes #ISSUE-B.

### Type of Change

- [x] ✨ New feature (non-breaking change that adds functionality)

### Changes Made

See above; tests in `tests/hermes_cli/test_memory_actions.py`, `provider-jobs.test.tsx`,
`connection-config.test.ts` and `e2e/memory-provider-jobs.spec.ts`.

### How to Test

```bash
scripts/run_tests.sh tests/hermes_cli/test_memory_actions.py tests/hermes_cli/test_serve_handler_ledger.py tests/ci/test_docs_drift.py
cd apps/desktop
pnpm exec vitest run src/app/settings/memory src/i18n scripts/i18n-keys.test.mjs
pnpm exec vitest run --project electron electron/connection-config.test.ts
pnpm run build && pnpm exec playwright test e2e/memory-provider-jobs.spec.ts
```

The backend tests load a synthetic provider through real discovery in a temp `HERMES_HOME` and run the CLI in
process: a job runs step by step to the end and writes its data; a failing step, a stalled job, a job that is not
ready and an unknown id each end with their reason; the routes refuse what cannot run and spawn nothing. The e2e runs
real Electron and a real `hermes serve`, which spawns the real `hermes memory action` process; the job's data lands in
the sandbox home.

Results on `main` with only this PR: backend 6 files, 38 tests passed (with the plugin seams, docs drift and ledger
files); desktop 18 files, 106 tests passed; electron connection-config 126 passed; e2e passed; typecheck clean;
code health 0 blocking. `scripts/check --only no-tmp` fails on `plugin-catalog/layersift.yaml:14`, a catalog entry
already on `main`, not on a file this PR touches.

Tested on: Windows 11.

### Screenshots

`screenshots/5-provider-job.png` (real Desktop, the `holographic-semantic` adapter's index job; the sidecar there is
a stand-in that answers its two routes). Generate screenshots with the [testkit](testkit/README.md); see the
[validation notes](validation/EVIDENCE.md) to distinguish the real-model run from the stand-in and the separate after-turn tests.

---

## Plugin side: `itpartypattaya/hermes-plugin-holographic`

The 0.29.x store-open problem is fixed in 0.30.0, which Hermes `main` pins (#157174): nothing to send for it. What
follows makes the catalog's own holographic use the new core seams, so catalog users get them too, not only users of
the `holographic-semantic` adapter. One issue first, then up to three PRs, each safe on any Hermes.

| Plugin PR | What | Needs in Hermes | When |
|---|---|---|---|
| HOLO-1 | `config_schema.py`: configure search by meaning in the Desktop's provider panel | nothing new: the panel exists on `main` today | after the plugin maintainer is open to the settings PR |
| HOLO-2 | `usage_report` / `review_items` | #PR3, #PR4 | once those have a maintainer's nod or are merged |
| HOLO-3 | a maintenance job "Index facts for search by meaning" | #PR7 | once #PR7 has a nod or is merged |

None changes `requires_hermes`: on a Hermes without a seam the methods are never called, and HOLO-1 uses only what
`main` has.

[Plugin Issue draft: Desktop embedding settings](issues/C-holographic-settings.md)

### PR HOLO-1 — `feat: configure search by meaning in the Desktop (config_schema.py)`

A `config_schema.py` beside `__init__.py` declares `embeddings` and the `embedding_*` keys (inline: `embeddings`,
`embedding_url`, `embedding_model`, `embedding_key_env`; the rest grouped), with `storage=provider`.
`read_config_fields(hermes_home)` returns what `plugins.hermes-memory-store` holds for that home;
`write_config_fields(values, hermes_home)` goes through the existing `save_config`. The key itself stays an
environment variable named by `embedding_key_env`, as today; the panel never stores a key. Tests: the schema loads
through Hermes' loader by path; a read returns stored natives for the given home; a write lands in that home's
`config.yaml` and leaves other keys alone.

### PR HOLO-2 — `feat: answer Hermes core's optional memory reads (usage_report, review_items)`

Hermes core is gaining two optional, read-only provider methods (NousResearch/hermes-agent#PR3,
NousResearch/hermes-agent#PR4):
`usage_report(hermes_home)` feeds a capacity display, and `review_items(hermes_home)` feeds a memory checkup the user
starts (one model call with no tools; it proposes and writes nothing). The default of both is `{}`, so on any Hermes
without them these methods are never called.

- Both open the store with SQLite `mode=ro` on an uninitialized instance, from the `hermes_home` they are given: no
  write, no network, no embedding call.
- `usage_report`: `items` (active facts) and `storage_bytes` (the file and its WAL). No budget: the provider enforces
  no limit on the store, and none is invented.
- `review_items`: each fact as `{"id", "text", "created_at", "uses", "score", "unconfirmed", "protected"}`. A fact
  recall refuses to inject (credentials, instructions) is left out, by the same checks recall uses.
- A store per user or chat, or an in-memory store, answers `{}`: there is no single file to read.

Tests: a synthetic store read before and after with its bytes unchanged; off / empty / unsupported told apart; a
refused fact never listed.

### PR HOLO-3 — `feat: a Desktop job that indexes the facts already stored for search by meaning`

`maintenance_actions(hermes_home)` lists "Index facts for search by meaning": where it stands (facts with a current
vector for this endpoint, model and `embedding_space`, of facts stored) and `ready: false` with the reason while
embeddings are off or the endpoint is unusable. `run_maintenance_step` embeds one batch of facts without a current
vector, sized as the after-turn catch-up sizes it, stores the vectors in `fact_embeddings` as that path does, and says
`done` when none is left. A text the endpoint refuses is set aside as 0.30.0 does, so one fact cannot stall the job.
Tests: against a fake embeddings endpoint, a store fills batch by batch to "M of M"; off, unusable and a refused
text each end with their reason; nothing is written for a fact that changed meanwhile.

---

## Cross-references: what to post where, and when

GitHub links `owner/repo#N` both ways by itself; one link in each direction is enough, and nobody needs an @-mention.

**In the Hermes PR (#PR3 / #PR4 / #PR7), once the plugin issue exists** — a comment, or a line in the body:

> Consumers outside this repo: `holographic-semantic` implements these methods today
> (liwangcc/hermes-optimization@`c4d265b`, `memory/plugin/holographic-semantic/`). For the catalog's holographic I
> opened itpartypattaya/hermes-plugin-holographic#HOLO-ISSUE to settle the field meanings with its maintainer; this
> PR stands on its own either way, and a provider that implements nothing shows as "not reported".

**In the plugin issue, when a Hermes PR changes after review** (a renamed field, a dropped one):

> Update: in NousResearch/hermes-agent#PR3 review, `<field>` became `<new>`. The adapter is updated
> (liwangcc/hermes-optimization@`<SHA>`); nothing here needs to change until you pick it up.

**After a Hermes PR merges:**

> NousResearch/hermes-agent#PR7 is merged (in `<release>`). The job seam is final, so HOLO-3 can go ahead whenever
> suits you; I can send it.
