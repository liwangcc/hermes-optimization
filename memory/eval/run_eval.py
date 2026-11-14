"""Self-contained semantic-channel retrieval eval (synthetic Chinese-heavy store).

Compares how facts are ADMITTED on meaning, holding the embedding model fixed (bge-m3):

  zbar_*  : the upstream holographic default — admit a fact only if its standardized
            similarity z >= sqrt(2*ln(N)) + RECALL_MARGIN (margin=1.0). A precision-first
            statistical-outlier gate.
  cos_*   : the tuned alternative — admit facts with cosine >= tau (0.55), top-5.

Each runs on two fact-text variants:
  content      : embed the fact content only (what upstream does)
  content_tags : embed content + keywords (the proposed improvement)

No lexical stack and no personal data required: just bge-m3 + the synthetic JSON next to this file.

Run:
    BGE_MODEL=/path/to/bge-m3 python run_eval.py
    (BGE_MODEL defaults to the HuggingFace id "BAAI/bge-m3" if unset)
"""
import json, math, os, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
FACTS = json.loads((HERE / "facts.json").read_text(encoding="utf-8"))
QUERIES = json.loads((HERE / "queries.json").read_text(encoding="utf-8"))["queries"]
IDS = [f["fact_id"] for f in FACTS]
N = len(FACTS)
MARGIN = 1.0          # upstream RECALL_MARGIN
TAU = 0.55            # tuned cosine threshold
TOPK = 5
ZBAR = math.sqrt(2 * math.log(N)) + MARGIN

MODEL_PATH = os.environ.get("BGE_MODEL", "BAAI/bge-m3")
print(f"loading model: {MODEL_PATH}", flush=True)
import torch
from sentence_transformers import SentenceTransformer
dev = "cuda" if torch.cuda.is_available() else "cpu"
kw = {"torch_dtype": torch.float16} if dev == "cuda" else {}
model = SentenceTransformer(MODEL_PATH, device=dev, model_kwargs=kw)

def embed(texts):
    return np.asarray(model.encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False))

variants = {
    "content": [f["content"] for f in FACTS],
    "content_tags": [f["content"] + " " + (f.get("tags") or "") for f in FACTS],
}
fact_vecs = {}
for name, texts in variants.items():
    cache = HERE / f"emb_{name}.npy"
    if cache.exists():
        fact_vecs[name] = np.load(cache)
    else:
        v = embed(texts); np.save(cache, v); fact_vecs[name] = v
    print(f"fact vectors [{name}]: {fact_vecs[name].shape}", flush=True)

embed(["warmup"])
qvecs = {q["id"]: embed([q["query"]])[0] for q in QUERIES}

def admit_zbar(sims):
    mu, sd = float(sims.mean()), float(sims.std())
    if sd < 1e-9:
        return []
    z = (sims - mu) / sd
    order = np.argsort(-sims)
    return [IDS[i] for i in order if z[i] >= ZBAR][:TOPK]

def admit_cos(sims, tau=TAU):
    order = np.argsort(-sims)
    return [IDS[i] for i in order if sims[i] >= tau][:TOPK]

def run(admit, variant):
    rows = []
    for q in QUERIES:
        sims = fact_vecs[variant] @ qvecs[q["id"]]
        got = admit(sims)
        rows.append({"id": q["id"], "category": q["category"], "expected": q["expected"], "got": got})
    return rows

def summarize(rows):
    pos = [r for r in rows if r["expected"]]
    neg = [r for r in rows if not r["expected"]]
    recall = np.mean([len(set(r["expected"]) & set(r["got"])) / len(r["expected"]) for r in pos])
    top1 = np.mean([bool(r["got"]) and r["got"][0] in r["expected"] for r in pos])
    negfp = np.mean([bool(r["got"]) for r in neg]) if neg else 0.0
    cats = {}
    for c in sorted({r["category"] for r in pos}):
        rs = [r for r in pos if r["category"] == c]
        cats[c] = round(float(np.mean([len(set(r["expected"]) & set(r["got"])) / len(r["expected"]) for r in rs])), 3)
    return {"recall@5": round(float(recall), 3), "top1": round(float(top1), 3),
            "neg_fp_rate": round(float(negfp), 3), "by_category": cats}

systems = {
    "zbar_content":      (admit_zbar, "content"),
    "zbar_content_tags": (admit_zbar, "content_tags"),
    "cos_content":       (admit_cos, "content"),
    "cos_content_tags":  (admit_cos, "content_tags"),
}
summary, all_rows = {}, []
for name, (admit, variant) in systems.items():
    rows = run(admit, variant)
    summary[name] = summarize(rows)
    all_rows.extend([{**r, "system": name} for r in rows])

out = {"model": f"BAAI/bge-m3 ({dev})", "n_facts": N, "n_queries": len(QUERIES),
       "zbar_threshold": round(ZBAR, 3), "tau": TAU, "summary": summary, "rows": all_rows}
(HERE / "results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))
print("saved results.json")