# Memory providers: let the user start a provider's maintenance job and see it finish

**Target:** `NousResearch/hermes-agent` · Feature request · draft only

## Problem or use case

Some memory providers have work to do on facts that are already stored. The usual case is search by meaning: after a user turns embeddings on or changes the model, the stored facts need vectors for the active model.

Today that work happens implicitly. The catalog's Holographic plugin, for example, makes vectors in a time-boxed batch after each chat turn, and that catch-up works, including for slow local endpoints (itpartypattaya/hermes-plugin-holographic#5). What a user cannot do is start the work, see how far along it is, and know when it is done. The provider settings in the Desktop can change the configuration but cannot run anything, and `hermes memory` has only `setup`, `status`, `off` and `reset`.

## Proposed solution

Two optional methods on `MemoryProvider`, both with inert defaults:

- one lists the provider's jobs, each with a label, where it stands now and whether it can run;
- one runs a single bounded step of a job, and is called again until the job says it is done.

Hermes only lists the jobs and calls the steps:

- `hermes memory action [id]` lists the jobs or runs one, printing each status.
- The Desktop shows the jobs under the provider's settings with **Run**, progress and the result. It starts that same CLI command through the existing maintenance-action mechanism (the one behind doctor, backup and the others), and adds nothing of its own to how action status is tracked (#25916).
- Nothing runs unless the user starts it. A provider that offers no jobs gets no new UI.
- The provider owns what a job does, its model, its index and how it resumes. No provider or model name is added to core.

There is a concrete consumer. `holographic-semantic`, a standalone adapter I maintain outside this repo, implements both methods for its local embedding index. It is not published yet; I can publish it alongside the PR. The catalog's Holographic plugin does not need the adapter or its local embedding service. It could offer a job over its own embedding path if its maintainer wants one.

## Evidence so far

On Windows 11, with a prototype of this change on `main` as of 2026-11-19, the actual **Run** button in the Desktop drove that adapter with BGE-M3 on CPU over 12 synthetic facts: **0 of 12 → 12 of 12** indexed. A second run embedded **0**, and all 12 vectors were still there after the embedding service restarted.

That shows the flow working end to end with a real consumer. It is not a benchmark: I have not measured how much sooner a store is fully indexed than with the after-turn catch-up, and nothing has been run on macOS or Linux.

Would a maintainer be open to reviewing one PR for the two optional methods plus the CLI and Desktop entry points? It is about 1,000 added lines, including tests, docs and the 9 locales.
