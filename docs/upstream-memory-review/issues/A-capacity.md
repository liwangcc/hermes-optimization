# Desktop: show memory capacity by layer

**Target:** `NousResearch/hermes-agent` · Feature request · draft only

## Problem or use case

When a memory write reaches its configured limit, a Desktop user has no clear way to tell which layer is full. The byte sizes of `USER.md` and `MEMORY.md` don't answer how close they are to the write-time character cap. An optional provider store is a third, separate layer; its usage should not be guessed from those files.

## Proposed solution

Show each layer in Memory & Context and Command Center → Maintenance. For the two built-in files, use the same count and limit as the write path. For an active provider, display only the usage it reports through an optional read-only `MemoryProvider.usage_report(hermes_home)`. Keep **off**, **empty**, **unreadable**, and **not reported** distinct. There is no new route for this slice: `GET /api/memory` adds a `layers` field without removing the existing fields. The built-in layers work without a provider.

On the pinned Hermes base (`152fe189`), this slice alone passed **6 targeted backend tests and 119 Desktop tests (including i18n checks)** on Windows. Our `holographic-semantic` adapter is a reference consumer of the optional hook; Holographic itself could adopt it separately. Neither plugin change is required for the built-in layers.

## Review plan

1. **First PR: capacity by layer**, as above. It does not depend on the reminder or either refactor.
2. **Follow-ups only if useful:** a separate user-started, read-only checkup that makes proposals but applies nothing; a separate suggestion when a provider catalog overlaps `MEMORY.md`; and an opt-in reminder. The reminder needs two small preparatory refactors (profile-keyed storage and composer offers), each reviewable on its own. They are not prerequisites for the first PR.

Would you be open to reviewing the standalone capacity PR first? I'll include the full test output summary, reproduction steps, and limitations in each PR. The checkup and reminder can be discussed separately. Provider maintenance jobs are a separate proposal, not a dependency.
