# Memory architecture: why two layers, and how they stay clean

The design behind the semantic enhancement in [`../memory/`](../memory/README.md).
The short version: **a tiny always-on layer and a large retrieved store do different
jobs; pointers keep the first small while reaching the second; retrieval getting
better means the always-on layer should get *smaller*, not disappear.**

## A mental model

- **Always-on layer** (`MEMORY.md` / `USER.md`) = common sense and habits that are
  *always* in mind: who the user is, their standing preferences, hard rules.
- **Fact store** (SQLite) = the filing cabinet: all the detail, opened only when needed.
- **Pointer** (`fact#42`) = a sticky note on your forehead: "this lives in drawer 42".
- **Vector retrieval** = a smart clerk who fetches drawers based on what you ask.

You cannot rely on the clerk to *volunteer* "the user prefers Chinese" on every task —
that has to live in your head, not behind a query.

## The two layers do different jobs

| | always-on layer | fact store + retrieval |
|---|---|---|
| trigger | **query-independent**, present every turn | **query-dependent**, recalled when relevant |
| content | preferences / identity / hard rules / pointers | long-tail factual detail |
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

## Pointers: what they point at, and two retrieval paths

A pointer like `fact#42` in the always-on layer refers to the row `fact_id = 42` in the
SQLite store. The always-on layer holds only "pointer + a tiny label"; the detail lives in
the store and is fetched on demand.

There are **two independent paths** to a fact:

- **Automatic** — the provider's prefetch (lexical + semantic) recalls facts by query
  similarity and injects them. No pointer needed.
- **Index/convention** — the always-on pointers tell the agent "these facts exist, here
  are their IDs"; the agent fetches a specific one when it needs it.

They are complementary: automatic recall covers the query-relevant long tail; the resident
layer guarantees the floor and gives the agent a map.

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

Fact store:
- **supersede** — a new fact replaces an old one (old removed in the same step).
- **remove** — confirmed-useless facts are deleted, with a durable archive of the original.
- **trust feedback** — rate facts helpful / unhelpful so good ones rise and bad ones sink.
- **review** — surface cleanup candidates periodically.

Pointer integrity:
- Deleting a fact **must** update or remove its pointer in the always-on layer, or the
  pointer dangles. A periodic reference check (every `fact#N` in the resident layer still
  resolves to a live row) keeps the map honest.

## Bottom line

> The always-on layer is the query-independent, never-miss floor; vector retrieval is the
> query-dependent long tail. They divide labor — they are not redundant. Pointers keep the
> floor tiny yet able to reach the whole store. The floor stays small by a hard budget; the
> store stays useful by supersede / archive / trust decay. SQLite never "fills up" — the
> thing to fight is dirt, not size.

## Related: keeping the store *worth* recalling

Cleanup removes dirt; it does not address **density** — many *legitimate* facts on the
same topic, which makes top-k structurally unable to cover the acceptable set. A
proposed storage-side counterpart (compress redundancy into gists, in similarity tiers,
triggered by density) is sketched in [`tiered-compression.md`](tiered-compression.md).
It is a design proposal, not implemented.