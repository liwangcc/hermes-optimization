# Memory architecture: why two layers, and how they stay clean

The design behind the semantic enhancement in [`../memory/`](../memory/README.md).
The short version: **a tiny always-on layer and a large retrieved store do different
jobs; every memory has one home, the store by default; a catalog generated from the store,
not hand-kept pointers, lets the first stay small while reaching the second; retrieval
getting better means the always-on layer should get *smaller*, not disappear.**

## A mental model

- **Always-on layer** (`USER.md`; the built-in `MEMORY.md` is off in this design) = what is
  *always* in mind: who the user is and their standing preferences.
- **Fact store** (SQLite) = the filing cabinet: all the detail, opened only when needed.
- **Fact catalog** (`#42=label`) = the cabinet's table of contents, printed from the drawers
  themselves and never written by hand. A short fact that makes the catalog is printed in
  full; the catalog is optional and budgeted.
- **Vector retrieval** = a smart clerk who fetches drawers based on what you ask.

You cannot rely on the clerk to *volunteer* "the user prefers Chinese" on every task —
that has to live in your head, not behind a query.

## The two layers do different jobs

| | always-on layer | fact store + retrieval |
|---|---|---|
| trigger | **query-independent**, present every turn | **query-dependent**, recalled when relevant |
| content | identity / standing preferences | every other durable fact (the default) |
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

Two homes, and one test: **is it about the user, and needed in every session?**

| answer | home | what it holds |
|---|---|---|
| yes | `USER.md` | identity, and preferences that apply to every reply |
| no, or not sure | `fact_store` (**the default**) | every other durable fact |

How to do a kind of work is not a memory at all: it belongs in a skill. Hermes core draws
the same lines for its built-in stores ("facts that apply to EVERY session regardless of
task", procedures to skills), so the two do not disagree.

- **One home per memory.** A fact is not repeated in `USER.md`. When the store already holds
  it, the existing fact is revised instead of a second one being added.
- **The built-in `MEMORY.md` is off.** Which store a memory belongs in is a judgment the
  model makes per item; a prompt lowers the miss rate and never removes it. Turning
  `MEMORY.md` off removes one of the choices: core drops the `memory` target from its
  guidance and from the tool, so that tool cannot write there. That is a configuration core
  supports. Forbidding `MEMORY.md` by prompt while it is on would contradict core, so the
  plugin does not: the switch is the user's, in Hermes.
- **What took over its job.** `MEMORY.md` held short notes needed in every session and not
  about the user. A standing requirement of the user ("config is changed through the CLI,
  never by patching the file") fits `USER.md`. Other short notes can be stored as facts.
  A fact no longer than `catalog_label_tokens` appears in full if it passes recall screening
  and fits the total catalog budget. That makes the catalog useful with `MEMORY.md` off, but
  it is not a guarantee that a note always appears. Without the catalog, facts surface on demand.
- **Moving the old entries is the user's step.** Before `MEMORY.md` is turned off, its
  entries are split by hand: what is about the user to `USER.md`, the rest into facts.
  Neither the plugin nor the agent moves or deletes them.
- **Not a fallback.** A failed `fact_store` write is reported. A fact parked in `USER.md` or
  `MEMORY.md` instead would be a second copy that nothing reconciles, paid for on every turn.
- **`USER.md` can be off as well.** The two built-in stores are switched separately in
  Hermes. With `USER.md` off, what would go there goes to the store.
- **Off is recommended, not required.** The catalog and `MEMORY.md` can stay on together; the
  cost is one more block in every session's context, as large as what `MEMORY.md` holds. With
  the proposed core change, the Desktop says `MEMORY.md` is optional while the catalog is on and
  shows its estimated tokens per session next to the catalog's; it never switches anything off.
  Pointers to facts never go into `MEMORY.md` either way: the write routing keeps fact ids out.

Not measured in a controlled run: behavior with `MEMORY.md` off. In the author's own use,
with the old entries split as above, turning it off showed no noticeable loss.

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
forces "only what is needed every turn" to stay.

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

A review proposes; it never forgets on its own. The rules of the proposed Desktop Memory Checkup
([`upstream-memory-review/PR-DRAFT.md`](upstream-memory-review/PR-DRAFT.md)) are enforced in code on the model's
reply, the same for every provider:

- **Exempt from removal:** a fact the user tagged `protected` (no removal, no rewrite), and a fact under seven days
  old (no removal; a rewrite is allowed). A proposal that breaks this is shown as a question, not as a change.
- **Weight is order, not verdict:** bad feedback (0.5) outweighs an unconfirmed inference (0.3), which outweighs
  never being recalled for 30 days (0.2). It decides what is reviewed first. Low use alone never justifies a removal.
- **A removal needs evidence a person can check:** the other fact that repeats, replaces or contradicts it, or the
  fact's own text showing it has expired.

No hand-kept pointers:
- `fact#N` is not written into the always-on layer. The plugin's opt-in **fact catalog**
  generates the list from the store, so there is nothing to keep in step. See
  [`../memory/plugin/README.md`](../memory/plugin/README.md).
- Pointers already in `MEMORY.md` are the user's to drop when its entries are split. While
  `MEMORY.md` stays on, one dangles when its fact is merged or forgotten, so a periodic
  reference check (every `fact#N` there still resolves to a live row) is worth running.

## Bottom line

> The always-on layer is the query-independent, never-miss floor; vector retrieval is the
> query-dependent long tail. They divide labor — they are not redundant. Every memory has
> one home: `USER.md` for the user, the store for everything else. The built-in `MEMORY.md`
> is off in this setup, and the catalog can show eligible short facts in full. A catalog
> generated from the store, never hand-kept pointers, keeps the floor small while giving
> the agent a way to find more. The floor stays small by a hard budget; the store stays
> useful by supersede / archive / trust decay. SQLite never "fills up" — the thing to fight
> is dirt, not size.