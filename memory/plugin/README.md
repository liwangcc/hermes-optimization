# holographic-semantic plugin

A memory provider that **subclasses the holographic provider unchanged** and adds a
semantic recall channel backed by the local sidecar. The original holographic plugin
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

## Behavior

`prefetch = base prefetch (unchanged) + up to N extra semantic facts`, where extra facts are:
- cosine ≥ `tau`, trust-filtered, and not already in the base result;
- skipped for greetings (no semantic noise on "hi");
- subject to the repeat-window and the total cap;
- **fail-open**: any sidecar error/timeout returns the base result unchanged. Recall
  never blocks on the semantic channel.

## Rollback

```bash
hermes config set memory.provider holographic
```

One command back to the unmodified base provider. The sidecar can keep running or be stopped.