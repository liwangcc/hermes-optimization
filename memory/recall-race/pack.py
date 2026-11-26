"""Read-only view of the frozen race pack (build_pack.py) and the daily sidecar rule every route starts from.

    from pack import load, daily_append
    P = load()
    for r in P.rows:                       # one per probe row: set, lang, qid, store, q, base, worth_asking, ...
        s = P.stores[r.store]               # facts: keys, content, tags, keywords, label, recallable, vectors
        cos = s.vec["ct"] @ r.qvec          # the sidecar's cosine (content + " " + tags), aligned with s.keys
        keys = daily_append(r, dict(zip(s.keys, cos)), s)

Labels (targets, kinds, confusers) are not here: they are the referee's (referee.py).
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
PACK = HERE / "pack"
ROOT = HERE.parents[1]
TAU = 0.55  # the daily plugin's semantic_tau for bge-m3
CAP = 7  # semantic_total_cap
TEXTS = ("c", "ct", "tc", "k", "label")  # content / content+" "+tags (daily now) / tags+" "+content / keywords / label


def plugin():
    """The base plugin module (approx_tokens, text helpers), loaded the way the probe loads it."""
    if "hermes_plugin_holographic" not in sys.modules:
        os.environ.setdefault("HERMES_AGENT_REPO", str(ROOT / "vendor/tools/tmp/race/memory/keyword-gate/core_shim"))
        os.environ.setdefault("HERMES_HOME", str(ROOT / "vendor/tools/tmp/race/home"))
        sys.path.insert(0, str(ROOT / "vendor/holo-check/plugin/tools"))
        import provenance_probe  # noqa: F401
    return sys.modules["hermes_plugin_holographic"]


def load() -> SimpleNamespace:
    stores_raw = json.loads((PACK / "stores.json").read_text(encoding="utf-8"))
    idx = json.loads((PACK / "vectors_index.json").read_text(encoding="utf-8"))
    vec = np.load(PACK / "vectors.npz")
    kwvec = vec["KW"]
    base = {}
    for path in glob.glob(str(PACK / "base_rows" / "*.jsonl")):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            base[(r["set"], r["lang"], r["qid"])] = r["keys"]
    pos = {}
    for i, (sid, key) in enumerate(idx["facts"]):
        pos.setdefault(sid, []).append(i)
    stores = {}
    for sid, s in stores_raw.items():
        rows = pos[sid]
        stores[sid] = SimpleNamespace(
            id=sid, keys=[f["key"] for f in s["facts"]], facts=s["facts"],
            fact_id={f["key"]: f["fact_id"] for f in s["facts"]},
            recallable={f["key"]: f["recallable"] for f in s["facts"]},
            vec={t: vec[f"F_{t}"][rows] for t in TEXTS},
            kwvec=[kwvec[idx["fact_kw"][i]] for i in rows])  # per fact: (n_keywords, dim), empty when none
    qpos = {tuple(k): i for i, k in enumerate(idx["queries"])}
    qv = vec["Q"]
    out = []
    for sid, s in stores_raw.items():
        for q in s["queries"]:
            key = (q["set"], q["lang"], q["qid"])
            out.append(SimpleNamespace(set=q["set"], lang=q["lang"], qid=q["qid"], store=sid, q=q["q"],
                                       base=base[key], worth_asking=q["worth_asking"], greeting=q["greeting"],
                                       names_refuse=set(q["names_refuse"]), qvec=qv[qpos[key]]))
    return SimpleNamespace(stores=stores, rows=out, keywords=idx["keywords"],
                           big={"big/en": ["household/en", "multi/en", "contrast_en"],
                                "big/ru": ["household/ru", "multi/ru", "contrast_ru"],
                                "big/zh": ["household/zh", "multi/zh", "contrast_zh", "synthetic_zh"]})


def daily_append(r, scores: dict, store, tau: float = TAU, cap: int = CAP) -> list:
    """The daily plugin's _add_semantic on one row: the single closest fact by *scores* is appended after the base
    when it reaches *tau*, is not shown yet, the base holds fewer than *cap*, and names_fit / recallable pass."""
    keys = list(r.base)
    if r.greeting or not r.worth_asking or len(keys) >= cap or not scores:
        return keys
    top = max(scores, key=scores.get)
    if top in keys or not scores[top] >= tau or top in r.names_refuse or not store.recallable[top]:
        return keys
    return keys + [top]


def write_rows(path, rows) -> None:
    """A submission for referee.py: one JSON object per row with set, lang, qid, keys (and catalog fields if any)."""
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
