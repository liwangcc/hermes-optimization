# Desktop: run a memory provider’s maintenance jobs on demand

**Target:** `NousResearch/hermes-agent` · Feature request · draft only

## Problem or use case

After a user enables embeddings or changes models, facts already in the store may not have vectors for the active model. Some providers catch up a batch after each chat turn; their own CLI, when available, is another path. Desktop settings can configure a provider, but cannot ask it to finish this work now or show the result.

## Proposed solution

Let providers optionally list jobs with availability and progress, and run a job in bounded steps. Desktop shows **Run**, progress and the final result in the provider's settings, using the existing action-status mechanism. `hermes memory action` offers the same entry point from the CLI. The provider owns the tasks, model, index and continuation rules. No model or provider name is added to core, and providers without jobs have no new UI.

Our `holographic-semantic` adapter is a reference consumer that indexes existing facts through a local BGE-M3 sidecar. The catalog's Holographic plugin could offer a job using its own embedding path; it doesn't need this sidecar.

## Evidence and review plan

In a separate test of Holographic 0.30.0's existing **after-turn** backfill, five local embedding models each finished indexing the same 40 synthetic facts. Qwen3 stopped at **28/40** in the intentionally bounded first run; a new process submitted **only the remaining 12**, with no overlap in inputs. That tests provider-side continuation, not the proposed Desktop job. It isn't a performance or model-quality ranking.

Would you be open to reviewing a **single, independent PR** for the optional job hooks, CLI and Desktop flow? I'll include the full per-PR test results, reproduction steps and limits. This proposal doesn't require the separate work on capacity or checkups.
