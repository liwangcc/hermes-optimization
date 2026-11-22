# Semantic memory sidecar

A localhost-only HTTP service that loads **bge-m3** locally and serves normalized
sentence embeddings to the `holographic-semantic` wrapper. It is the "fuel" for
semantic recall: the wrapper decides *how* to use vectors; this service produces them.

> **Manual / CLI path.** The 0.6.1 wrapper can deploy a profile-managed service for you
> (Settings → Memory → embedding model → local → deploy). That path pins the model
> commit and the Python runtime (`memory/plugin/holographic-semantic/local-runtime.txt`)
> and keeps everything under `$HERMES_HOME/services/memory-embeddings/`. This directory
> is for CLI-only installs, custom CUDA setups, and debugging the protocol. Both speak
> the same endpoints; a running manual BGE-M3 sidecar is reused by the managed path.

- **Local & offline.** The model is loaded from disk; no network egress at runtime.
- **GPU if available.** CUDA + fp16 when present, otherwise CPU. A warmup encode
  avoids the first-query CUDA cold start.
- **Read-only.** It only reads the fact DB (`mode=ro`); it never writes your store.
- **Fail-safe.** Any error returns HTTP 5xx and the wrapper falls back to lexical recall.
- **Cached.** Fact vectors are cached in `cache/vectors.npz`, keyed by a content+tags
  hash, so a restart does not re-embed unchanged facts.

## 1. Get the model

Download `BAAI/bge-m3` into `models/bge-m3` (weights are **not** redistributed here):

```bash
# with the HuggingFace CLI
huggingface-cli download BAAI/bge-m3 --local-dir models/bge-m3
# or git-lfs
git lfs install && git clone https://huggingface.co/BAAI/bge-m3 models/bge-m3
```

## 2. Install deps

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

For CUDA, install the torch build matching your driver (see pytorch.org); the default
pip wheel may be CPU-only.

## 3. Run

Point `SEMANTIC_DB` at the SQLite fact store used by your holographic provider:

```bash
SEMANTIC_DB=/path/to/memory_store.db python server.py
```

| env | default | meaning |
|---|---|---|
| `SEMANTIC_DB` | `./memory_store.db` | holographic fact store (SQLite, read-only) |
| `SEMANTIC_MODEL` | `./models/bge-m3` | local bge-m3 directory |
| `SEMANTIC_PORT` | `8791` | listen port (bound to 127.0.0.1) |
| `SEMANTIC_CACHE` | `./cache` | vector cache directory |

Example launch scripts: `run.example.sh` (POSIX) / `run.example.cmd` (Windows).

## Endpoints

| method | path | body | returns |
|---|---|---|---|
| GET | `/health` | — | readiness, device, indexed fact count, the store's fact count |
| POST | `/sync` | `{limit}` | index new/changed facts now (at most `limit`), drop deleted ones; returns `embedded`, `remaining`, `facts` |
| POST | `/candidates` | `{query, tau, limit, min_trust}` | ranked cosine candidates above `tau` |
| POST | `/embed` | `{texts: [...]}` | normalized vectors |

`/candidates` re-syncs the fact cache (embeds new/changed facts, drops deleted ones)
before scoring, so the index tracks the store without a separate indexing step.