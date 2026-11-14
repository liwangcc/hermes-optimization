# Config patterns

Reusable Hermes configuration patterns. **All values below are placeholders** — swap in
your own. Never commit real endpoints, keys, or personal paths.

## Edit config through the CLI, not by patching the file

Hermes guards `config.yaml` against direct writes. Use the CLI so changes are validated
and the file stays consistent:

```bash
hermes config set memory.provider holographic-semantic
hermes config set plugins.hermes-memory-store.semantic_enabled true
hermes config set plugins.hermes-memory-store.semantic_tau 0.55
```

## Memory: keep the always-on layer small, vectorize the long tail

- The always-on `USER.md` / `MEMORY.md` layer is injected every turn — keep it tiny and
  high-signal; do **not** vectorize it.
- The long-tail fact store is where semantic recall pays off. Enable the semantic channel
  there (see [`../memory/`](../memory/README.md)).

```yaml
# example fragment (placeholders)
memory:
  provider: holographic-semantic
plugins:
  hermes-memory-store:
    semantic_enabled: true
    semantic_url: http://127.0.0.1:8791
    semantic_tau: 0.55
    semantic_max_extra: 3
    semantic_total_cap: 7
    semantic_timeout_ms: 400
```

## Providers: pin context length only on the default route

Pin `context_length` on the default model/route; let other routes auto-detect, so a
single pinned window does not silently cap every model:

```yaml
# example fragment (placeholders)
model:
  default: your-model
  context_length: 128000        # pins the default route only
providers:
  your-provider:
    base_url: https://api.example.com/v1   # your endpoint
    api_key_env: YOUR_PROVIDER_API_KEY      # key lives in the environment, never here
```

## Custom OpenAI-compatible provider

```yaml
providers:
  my-provider:
    base_url: https://api.example.com/v1
    api_key_env: MY_PROVIDER_API_KEY
    models: [model-a, model-b]
```

Keep the key in an environment variable / `.env` (gitignored), referenced by name only.

## Rollback is a config change, not a code change

Because the semantic layer is a separate provider, disabling it is one command:

```bash
hermes config set memory.provider holographic
```

Design enhancements so that turning them off is a config flip, not a revert.