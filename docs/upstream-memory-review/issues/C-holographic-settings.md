# Holographic: configure semantic recall from Hermes Desktop

**Target:** `itpartypattaya/hermes-plugin-holographic` · draft only

## Problem or use case

`hermes memory setup` already knows Holographic's embedding settings. A Desktop user shouldn't need to leave Settings or edit YAML just to turn embeddings on and choose the endpoint and model. Hermes Desktop's existing provider settings panel can render these fields from a provider's `config_schema.py`.

## First slice: settings only

Add that schema and pass profile-scoped reads and saves through the plugin's existing configuration helpers. The API key stays in its environment variable; the panel only edits the variable name. This needs no new Hermes interface and doesn't change `requires_hermes`. On the pinned Holographic 0.30.1 base (`76689f9`), the prototype passed **7 targeted tests**: five for the Desktop schema and two for the existing save path.

Would you prefer a small PR for the settings panel, or prefer to implement it yourselves? The PR can include the full results, reproduction steps, and limitations.

## Optional later slices

- **Read-only usage and review:** if Hermes adopts the optional hooks for capacity and checkups, Holographic could report its store's counts and consented review items. Does `protected` as a fact tag fit your design? Should a fact count as `unconfirmed` when it was inferred and has not been confirmed since?
- **Run backfill from Settings:** if Hermes adopts provider maintenance jobs, a Holographic job could reuse existing after-turn backfill and indexing logic to index the remaining facts for the active embedding configuration. It would be separate from the schema PR. This isn't a proposal to replace Holographic's index with a sidecar.

Our `holographic-semantic` adapter is a reference consumer on the Hermes side, not a dependency for this plugin. The core proposals can be discussed separately.
