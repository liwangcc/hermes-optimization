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
| `SEMANTIC_JUDGE_MODEL` | unset | optional: a local `Qwen/Qwen3-Reranker-0.6B` directory; with it `/judge` is served (about 0.25 s a message on a laptop GPU; on a CPU 1 to 3 s, which needs the wrapper's `semantic_timeout_ms` raised) |
| `SEMANTIC_DEVICE` | CUDA when present, else CPU | `cuda`, `mps` or `cpu`. Apple's GPU is used only when asked for: `mps` has run on one Mac (an M5), where the judge takes about 2 s a message in float16 |

Example launch scripts: `run.example.sh` (POSIX) / `run.example.cmd` (Windows).

## Endpoints

| method | path | body | returns |
|---|---|---|---|
| GET | `/health` | — | readiness, device, indexed fact count, the store's fact count |
| POST | `/sync` | `{limit}` | index new/changed facts now (at most `limit`), drop deleted ones; returns `embedded`, `remaining`, `facts` |
| POST | `/candidates` | `{query, tau, limit, min_trust}` | ranked cosine candidates above `tau` |
| POST | `/embed` | `{texts: [...]}` | normalized vectors |
| POST | `/judge` | `{query, ids, k, min_trust}` | for the facts in `ids` and the `k` closest by cosine: `cos`, `rank` in the store, and the judge's readings of the message with the fact. On CUDA every one of them is read, `strict` and `generic`. Off CUDA the judge reads the facts in `ids` and the closest one, `strict` only; the rest carry `cos` and `rank` for the wrapper's pointers; 404 without a judge model. Used by the wrapper's `semantic_judge` |

When a judge is loaded, the sidecar checks for new or edited facts every two seconds and indexes up to four at a
time. `/judge` ranks facts by vectors that match their current content and tags. Requested IDs can still be scored
while their vectors are pending. The response's `embedded` count is zero.

`/candidates` re-syncs the fact cache (embeds new/changed facts, drops deleted ones)
before scoring, so the index tracks the store without a separate indexing step.
