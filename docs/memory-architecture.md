# Memory architecture: why two layers, and how they stay clean

The design behind the semantic enhancement in [`../memory/`](../memory/README.md).
The short version: **a tiny always-on layer and a large retrieved store do different
jobs; every memory has one home, the store by default; a catalog generated from the store,
not hand-kept pointers, lets the first stay small while reaching the second; retrieval
getting better means the always-on layer should get *smaller*, not disappear.**

## A mental model

- **Always-on layer** (`USER.md`, and optionally `MEMORY.md`) = what is *always* in mind:
  who the user is, their standing preferences, and the few notes that must hold in any session.
- **Fact store** (SQLite) = the filing cabinet: all the detail, opened only when needed.
- **Fact catalog** (`#42=label`) = the cabinet's table of contents, printed from the drawers
  themselves and never written by hand.
- **Vector retrieval** = a smart clerk who fetches drawers based on what you ask.

You cannot rely on the clerk to *volunteer* "the user prefers Chinese" on every task —
that has to live in your head, not behind a query.

## The two layers do different jobs

| | always-on layer | fact store + retrieval |
|---|---|---|
| trigger | **query-independent**, present every turn | **query-dependent**, recalled when relevant |
| content | identity / standing preferences / must-see notes | every other durable fact (the default) |
| size | tiny (a few KB) | large (hundreds+ of facts) |
| guarantee | **never missed** | bounded recall |

### Why retrieval cannot replace the always-on layer

1. **Retrieval fires on the current query.** But "prefer Chinese", "edit config via the
   CLI, not by patching the file", "use this git binary" apply to *every* task. A query
   like "help me write code" may not retrieve "prefer Chinese" — yet it must still hold.
2. **Retrieval has a recall ceiling.** Even a good hybrid misses some relevant facts
   (see [`../memory/eval/`](../memory/eval/README.md)). For safety / credentials /
   identity, a miss is not acceptable. The always-on layer is the guaranteed floor.
3. **Meta-knowledge must be resident.** "Where things are, how to use the memory system,
   the user's conventions" is what *interprets* the query in the first place; it has to
   exist before retrieval runs.

So the right shape is: **the stronger retrieval gets, the smaller the always-on layer
should be** — keep only "never-miss + query-independent", hand the long tail to retrieval.
The conclusion is *trim*, not *remove*.

## Where a new memory goes

One question decides it: **is it needed in every session, whatever the task?**

| answer | home | what it holds |
|---|---|---|
| no, or not sure | `fact_store` (**the default**) | durable facts needed on demand |
| yes, and about the user | `USER.md` | identity and standing preferences |
| yes, and not about the user | `MEMORY.md` (optional) | short notes that must be visible even in unrelated sessions |

- **One home per memory.** A fact is not repeated in the always-on layer. When the store
  already holds it, the existing fact is revised instead of a second one being added.
- **What `MEMORY.md` is still for.** Facts live in the store, the user lives in `USER.md`,
  and the map of the store is generated (next section), so little is left: notes that hold
  for any task and are not about the user, such as "edit config via the CLI, not by patching
  the file". Retrieval fires on the query and cannot promise those. With no such notes,
  `MEMORY.md` can stay off, which is why it is optional. Whether it is on is the user's
  decision, and the entries already in it are left as they are.
- **`MEMORY.md` is not a fallback.** A failed `fact_store` write is reported. A fact parked
  in `MEMORY.md` instead would be a second copy that nothing reconciles, paid for on every turn.
- **Either built-in store can be off.** `USER.md` and `MEMORY.md` are switched separately in
  Hermes. What would go to one that is off goes to the store.

The `holographic-semantic` wrapper puts this rule in the system prompt as a fixed block, the
same with its fact catalog on or off. See [`../memory/plugin/README.md`](../memory/plugin/README.md).

## Reaching a fact: recall, and a generated catalog

There are **two independent paths** to a fact:

- **Automatic** — the provider's prefetch (lexical + semantic) recalls facts by query
  similarity and injects them.
- **By id** — the plugin's opt-in **fact catalog** lists every recallable fact as `#id=label`
  in the system prompt, and the agent reads the ones it needs with `fact_store get`. With
  the catalog off, the agent searches the store itself.

They are complementary: automatic recall covers the query-relevant long tail; the catalog
gives the agent a map of what exists.

The catalog is a **generated read index, not a write policy**. It says what the store holds
and decides nothing about where a memory is written, so the routing above is the same with
it on or off. Fact ids are never written by hand into `USER.md` or `MEMORY.md`: a hand-kept
`fact#42` dangles as soon as that fact is merged or forgotten, and a generated list cannot.

## What "full" means for each layer

**Always-on layer (hard character budget).** It is deliberately tiny (a few KB). When a
new entry would overflow, the write is *rejected* — you must **consolidate**: remove or
shorten stale entries and add the new one in a single atomic batch, checked against the
final budget. Fullness is not a bug; it is the signal to curate. The hard cap is what
forces "only what is needed every turn" to stay. In `MEMORY.md` that curation is the user's
call: the agent does not rewrite existing entries on its own initiative.

**Fact store (SQLite).** Capacity is essentially never the problem — SQLite holds hundreds
of thousands of facts; a few dozen is nothing. The real problem is **bloat hurting
retrieval**: more near-duplicate / stale facts means more noise, and a statistical-outlier
admission gate gets *stricter* as the store grows (`z ≥ sqrt(2·ln N) + margin`). So cleanup
is about **retrieval quality, not capacity**. The store fears *dirty*, not *many*.

## Cleanup discipline

Always-on layer:
- Anything that goes stale within a week belongs in session history, not resident memory.
- Reusable procedures belong in skills, not memory.
- Keep entries as compact declarative facts.
- A fact that lives in the store is not repeated here.

Fact store:
- **supersede** — a new fact replaces an old one (old removed in the same step).
- **remove** — confirmed-useless facts are deleted, with a durable archive of the original.
- **trust feedback** — rate facts helpful / unhelpful so good ones rise and bad ones sink.
- **review** — surface cleanup candidates periodically.

No hand-kept pointers:
- `fact#N` is not written into the always-on layer. The plugin's opt-in **fact catalog**
  generates the list from the store, so there is nothing to keep in step. See
  [`../memory/plugin/README.md`](../memory/plugin/README.md).
- Pointers already in `MEMORY.md` are existing entries: they stay until the user removes
  them. Until then one dangles when its fact is merged or forgotten, so a periodic reference
  check (every `fact#N` there still resolves to a live row) is worth running.

## Bottom line

> The always-on layer is the query-independent, never-miss floor; vector retrieval is the
> query-dependent long tail. They divide labor — they are not redundant. Every memory has
> one home: the store by default, `USER.md` for the user, `MEMORY.md` only for the few notes
> that must show in any session. A catalog generated from the store, never hand-kept
> pointers, lets the floor stay tiny yet reach the whole store. The floor stays small by a
> hard budget; the store stays useful by supersede / archive / trust decay. SQLite never
> "fills up" — the thing to fight is dirt, not size.