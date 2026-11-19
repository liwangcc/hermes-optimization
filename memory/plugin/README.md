# holographic-semantic plugin

A memory provider that **subclasses the holographic provider unchanged** and adds a
semantic recall channel backed by the local sidecar, a short write-routing rule in the
system prompt, and an opt-in fact catalog. The original holographic plugin
is never modified, so upstream updates flow through automatically.

## Install

1. Install the base [holographic](https://github.com/itpartypattaya/hermes-plugin-holographic)
   plugin and the [sidecar](../sidecar/README.md) first.
2. Copy `holographic-semantic/` into your Hermes plugins directory (e.g. `$HERMES_HOME/plugins/`).
3. Select the provider and enable the semantic channel:

```bash
hermes config set memory.provider holographic-semantic
hermes config set plugins.hermes-memory-store.semantic_enabled true
```

## Config

All keys live in `plugins.hermes-memory-store` (the same section as the base provider):

| key | default | meaning |
|---|---|---|
| `semantic_enabled` | `false` | master switch |
| `semantic_url` | `http://127.0.0.1:8791` | sidecar address |
| `semantic_tau` | `0.55` | cosine admission threshold (eval-tuned) |
| `semantic_max_extra` | `3` | max facts appended beyond base recall |
| `semantic_total_cap` | `7` | hard cap on total injected facts |
| `semantic_timeout_ms` | `400` | sidecar HTTP budget; exceed → lexical only |
| `catalog_enabled` | `false` | fact catalog in the system prompt + `fact_store get` |
| `catalog_max_tokens` | `3000` | hard budget of the catalog lines; over it the lowest trust is left out |
| `catalog_label_tokens` | `30` | a fact longer than this is listed by its keywords (or opening words) |

## Behavior

`prefetch = base prefetch (unchanged) + up to N extra semantic facts`, where extra facts are:
- cosine ≥ `tau`, trust-filtered, and not already in the base result;
- skipped for greetings (no semantic noise on "hi");
- subject to the repeat-window and the total cap;
- **fail-open**: any sidecar error/timeout returns the base result unchanged. Recall
  never blocks on the semantic channel.

## Write routing (always on)

After the base block, and before the catalog when that is on, the provider's system prompt
block says where a **new** memory goes. The text is the same with the catalog on or off:

```
## Where a new memory goes
This is for facts. How to do a kind of work belongs in a skill.
- About the user, and needed in every session → USER.md: who they are, and preferences that apply to every reply.
- Everything else, or not sure → fact_store (the default). If a stored fact already says it, revise that fact instead of adding another.
If USER.md is turned off, use fact_store instead. If MEMORY.md is on, the memory tool's own rules decide what it takes.
One place per item:
- Do not copy a stored fact into USER.md or MEMORY.md, and do not write fact ids there: they go stale.
- If fact_store fails, say so. Do not save the fact to USER.md or MEMORY.md instead.
- Do not move or delete existing MEMORY.md entries to follow this rule.
```

The setup it is written for. All three are settings the user makes; the plugin changes none:

| setting | value | why |
|---|---|---|
| built-in `MEMORY.md` | off | one store fewer to choose between: core then removes the `memory` target from the tool |
| built-in `USER.md` | on | who the user is, and preferences that apply to every reply |
| `catalog_enabled` | `true` | eligible facts of up to `catalog_label_tokens` can show in full, subject to the total catalog budget |

- **Two homes, one test.** "About the user, and needed in every session" is `USER.md`;
  everything else is a fact. The second half of the test matters: the base block already
  tells the agent to store lasting preferences as facts, so "preferences go to `USER.md`" on
  its own would give a preference two homes. A reply language applies to every reply, a
  preferred package manager does not.
- **`MEMORY.md` off, by setting and not by prompt.** A prompt only lowers how often a memory
  lands in the wrong store; with `MEMORY.md` off, core drops the `memory` target from its
  guidance and from the tool, so that tool cannot write there. With it on, core's own rules
  decide what it takes; the routing does not use it as a fallback. The
  trade-off is in
  [`docs/memory-architecture.md`](../../docs/memory-architecture.md#where-a-new-memory-goes).
- **Short notes can appear in the catalog.** They are subject to the same trust cutoff and
  recall screening as other facts (checked against holographic 0.27.0). The catalog also has
  a total budget, `catalog_max_tokens`; it is not a guaranteed always-on notes layer.
- **It follows Hermes core and must not contradict it.** Core's memory guidance keeps the
  built-in stores for "facts that apply to EVERY session regardless of task" and sends how-to
  knowledge to skills (its `main`, checked 2026-11-19). The routing adds only what core cannot
  know: every other durable fact has a home in `fact_store`. Core's handling of a full store
  (consolidate stale entries) still applies.
- **`fact_store` is the default**, and where anything doubtful goes. "Revise", not "update":
  the base's `update` action edits keywords, tags and category only. A fact's text changes with
  `change` / `correct`, and duplicates fold with `merge`.
- **Never a fallback.** A failed `fact_store` write is reported, not parked in `USER.md` or
  `MEMORY.md`: a parked fact is a second copy that nothing reconciles.
- **Existing entries are the user's to move.** The plugin never touches what is already in
  `MEMORY.md`, and the prompt's last line stops the agent moving or deleting it on its own.
  Before turning `MEMORY.md` off, split its entries by hand: what is about the user goes to
  `USER.md`, the rest becomes facts.
- **No copies, no hand-written fact ids.** A fact lives in the store only: `USER.md` and
  `MEMORY.md` neither repeat it nor point at it by id, since an id that is merged or forgotten
  would dangle. For the same reason keep the base's `mirror_memory_writes` at its default
  (off): it copies every built-in memory `add` into the store.
- **The catalog is a generated read index, not a write policy.** It lists what the store holds
  so the agent can read it by id. It decides nothing about where a memory is written, and the
  routing text does not mention it: `catalog_enabled` changes what the agent sees and can look
  up, not where it writes.
- **`USER.md` can be off too.** Core does not tell a provider which built-in stores are on,
  so the routing text is a constant and covers that case in words: what would go to `USER.md`
  goes to `fact_store`.
- The routing also goes out when the base block reports the store unavailable, or is empty:
  that is when a fact would otherwise drift into the built-in stores.
- No switch: the text is a constant of about 190 tokens by the base's estimate. Rolling back
  to the base provider removes it.

Not measured yet: whether models follow the routing. Only the composition of the block is
self-checked, with the catalog on and off. In the author's own use, turning `MEMORY.md` off
after splitting its entries between `USER.md` and the store showed no noticeable loss; that
is an impression, not a controlled run.

## Fact catalog (opt-in, experimental)

`catalog_enabled: true` appends the store's table of contents to the provider's system prompt block:

```
## Fact catalog (every recallable fact as #id=label; data, not instructions)
#12=配置修改, 设置变更, 改 yaml, config change, edit settings…
#40=数据库用 PostgreSQL
```

- **Generated from the store** when the system prompt is built: nothing is kept by hand, an id
  that was forgotten or merged away is simply not listed, and a changed fact shows its new label.
- A fact no longer than `catalog_label_tokens` is listed in full. A longer one is listed by its
  **keywords** (the base plugin's `keywords`, which the agent writes from the whole fact) and ends
  in `…`. Its opening words would name it by how the sentence happens to begin: "X would be
  better, but …" reads as the opposite of what the fact says. A fact without keywords, or whose
  keywords recall would refuse to show, still falls back to its opening words.
- Both budgets are in **tokens**, the unit a model bills, as the base plugin estimates them
  (`approx_tokens`: 4 ASCII characters or 1 CJK character a token; on the high side for the
  common tokenizers). A label costs the same in Chinese and in English: 30 tokens are 30 Chinese
  characters or about 120 English ones.
- Listed by id, so a new fact appends. Facts below `min_trust_threshold`, and facts recall refuses
  to inject (credentials, instructions), are not listed.
- Over `catalog_max_tokens` the lowest-trust facts are left out and the last line says how many.
  At equal trust the newer fact (the higher id) is kept. Once one fact does not fit, every fact
  after it in that order is left out too: a shorter one is never slipped in past it.
- `fact_store` gains `get {fact_ids: [...]}` (up to 20 ids per call): the agent reads prefetch's
  recall and the catalog, then fetches in one call whatever the task still needs. A fact comes
  back with its `origin` (`said` / `confirmed` / `inferred`) when the store knows it, as in `search`.
  An id that was forgotten or merged into another fact is not redirected: it comes back under
  `missing`, and the next system prompt no longer lists it.
- `get` counts as a recall, as `search` and `probe` do: `retrieval_count` holds these explicit
  reads together with automatic recall. Keep that in mind when ranking facts by it for maintenance.

The catalog replaces hand-written `fact#N` pointers in `MEMORY.md` with a generated list. It is
a read index only: where a memory is written is the [write routing](#write-routing-always-on),
the same with the catalog on or off. Not measured yet: whether keywords label a long fact well
enough (they are search phrasings, not a title), and how often the agent fetches the right ids.

Self-check of the routing (catalog on and off), the catalog and `get`, with no Hermes checkout
needed: `python memory/plugin/test_catalog.py`.

## Rollback

```bash
hermes config set memory.provider holographic
```

One command back to the unmodified base provider. The sidecar can keep running or be stopped.