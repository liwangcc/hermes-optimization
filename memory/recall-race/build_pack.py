"""Freeze the referee pack for the recall race on the official probe sets, daily-version shape.

The daily version runs the base with embeddings off and lets a sidecar append the closest fact by
cos(content + " " + tags). This builds what every route reads, once:

    python -B memory/recall-race/build_pack.py          # from the repo root; CPU, then CUDA for bge-m3

pack/base_rows/   official tools/provenance_probe.py rows: --emb off --modes off --keywords <frozen file>
pack/stores.json  per store: facts (key, content, raw tags, keywords, catalog label, recallable),
                  per query: worth_asking, is_greeting, the fact keys names_fit refuses
pack/labels.json  per row: kind, targets, split, slice, confusion rule  (the referee's; routes do not read it)
pack/vectors.npz  bge-m3 unit vectors (fp16 on CUDA), index in pack/vectors_index.json
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "vendor" / "holo-check" / "plugin"
KW = PLUGIN / "tools" / "issue95_keywords"
PACK = Path(__file__).resolve().parent / "pack"
SHIM = ROOT / "vendor" / "tools" / "tmp" / "race" / "memory" / "keyword-gate" / "core_shim"
LANGS8 = "de,en,it,ja,nl,ru,th,zh"  # the languages the frozen multi keywords cover
LABEL_TOKENS = 30  # catalog_label_tokens default of the daily plugin

os.environ["HERMES_AGENT_REPO"] = str(SHIM)
os.environ["HERMES_HOME"] = str(ROOT / "vendor" / "tools" / "tmp" / "race" / "home")
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
Path(os.environ["HERMES_HOME"]).mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(PLUGIN / "tools"))
import provenance_probe as pp  # noqa: E402

H = sys.modules["hermes_plugin_holographic"]

RUNS = [  # (probe args, keywords file)
    (["--set", "multi", "--langs", LANGS8], "multi.json"),
    (["--set", "contrast_en"], "contrast_en.json"),
    (["--set", "contrast_ru"], "contrast_ru.json"),
    (["--set", "contrast_zh"], "contrast_zh.json"),
    (["--set", "household", "--split", "test"], "household.json"),
    (["--set", "household", "--split", "dev"], "household.json"),
    (["--set", "synthetic_zh"], "synthetic_zh.json"),
]


def base_rows() -> None:
    out = PACK / "base_rows"
    out.mkdir(parents=True, exist_ok=True)
    for args, kw in RUNS:
        pp.main(args + ["--emb", "off", "--modes", "off", "--keywords", str(KW / kw), "--out", str(out)])


def _cut(text: str, tokens: int) -> str:
    """Daily plugin's _cut: the longest opening that with its closing … costs at most *tokens*."""
    n = min(len(text), tokens * 4)
    while n and H.approx_tokens(text[:n] + "…") > tokens:
        n -= 1
    return text[:n].rstrip(" ,") + "…"


def label(content: str, tags) -> str:
    """Daily plugin's _label: the fact itself when it fits, else its keywords (or opening words), ending in …."""
    flat = " ".join((content or "").split())
    if H.approx_tokens(flat) <= LABEL_TOKENS:
        return flat
    kws = ", ".join(H._split_tags(tags)[1])
    if kws and (H._recall_problem(kws) or H._role_prompt(kws)):
        kws = ""
    return _cut(kws or flat, LABEL_TOKENS)


def stores_spec():
    """(store id, keywords file, keywords lang key, facts {key: (text, entities)}, [(row set, row lang, qid, text, label)])."""
    data = pp.load_multilingual()
    for lang in LANGS8.split(","):
        persons = dict(data.PROBES[lang])
        qs = []
        for i, (q, rel) in enumerate(data.QUERIES[lang]):
            conf = {"type": "none"}
            if rel:
                for name in persons:  # the probe's own loop: the last name found in the query wins
                    if name in q:
                        other = set().union(*(v for n, v in persons.items() if n != name))
                        conf = {"type": "keys", "keys": sorted(other)}
            qs.append(("multi", lang, str(i), q, {"kind": "real" if rel else "chit", "targets": list(rel or []),
                                                    "split": "all", "slice": "multi", "conf": conf}))
        yield f"multi/{lang}", "multi.json", lang, data.CORPUS[lang], qs
    for name in ("contrast_en", "contrast_ru", "contrast_zh"):
        c = pp.load_contrast(name)
        qs = []
        for pi, pair in enumerate(c.PAIRS):
            partner = [pair["queries"][1 - i][1] for i in range(len(pair["queries"]))]
            for i, (q, target) in enumerate(pair["queries"]):
                part = partner[i]
                conf = {"type": "none"} if part == target else {"type": "keys", "keys": [part]}
                qs.append((name, name, f"p{pi}q{i}", q, {"kind": "real", "targets": [target], "split": "all",
                                                          "slice": "contrast", "conf": conf}))
        for i, (q, cat) in enumerate(c.CHITCHAT):
            qs.append((name, name, f"c{i}", q, {"kind": "chit", "targets": [], "split": "all", "slice": "chit",
                                                 "conf": {"type": "none"}}))
        yield name, f"{name}.json", name, c.FACTS, qs
    hh = pp.load_contrast("household")
    for lang in hh.LANGS:
        qs = []
        for qid, q in hh.QUERIES.items():
            qs.append(("household", lang, qid, q[lang], {
                "kind": "real", "targets": sorted(q["targets"]), "split": q["split"], "slice": q["slice"],
                "conf": {"type": "keys", "keys": sorted(q.get("confused", ()))}}))
        for hid, h in hh.CHITCHAT.items():
            qs.append(("household", lang, hid, h[lang], {"kind": "chit", "targets": [], "split": h["split"],
                                                          "slice": "chit", "conf": {"type": "none"}}))
        yield f"household/{lang}", "household.json", lang, {k: v[lang] for k, v in hh.FACTS.items()}, qs
    sz = pp.load_contrast("synthetic_zh")
    qs = []
    for qid, q in sz.QUERIES.items():
        ql = "en" if "en" in q else "zh"
        qs.append(("synthetic_zh", ql, qid, q[ql], {"kind": "real", "targets": sorted(q["targets"]), "split": "all",
                                                     "slice": q["slice"], "conf": {"type": "nontarget"}}))
    for hid, h in sz.CHITCHAT.items():
        ql = "en" if "en" in h else "zh"
        qs.append(("synthetic_zh", ql, hid, h[ql], {"kind": "chit", "targets": [], "split": "all", "slice": "chit",
                                                     "conf": {"type": "none"}}))
    yield "synthetic_zh", "synthetic_zh.json", sz.LANG, sz.FACTS, qs


def stores_and_labels() -> None:
    stores, labels = {}, {}
    pp.DB_DIR = Path(tempfile.mkdtemp(prefix="race_pack_", dir=ROOT / "vendor" / "tools" / "tmp" / "race"))
    for sid, kwfile, kwlang, facts, qs in stores_spec():
        pp.KEYWORDS = pp._load_keywords(str(KW / kwfile), "all", 95)
        p = pp.make_provider(pp._db(sid.replace("/", "_") + ".db"), "off", "off")
        back = pp.store_facts(p, kwlang, facts)
        rows = [dict(r) for r in p._store.read("SELECT * FROM facts ORDER BY fact_id")]
        fl = [{"key": back[r["fact_id"]], "fact_id": r["fact_id"], "content": r["content"], "tags": r["tags"],
               "keywords": H._split_tags(r["tags"])[1], "label": label(r["content"], r["tags"]),
               "recallable": bool(p._recallable(r))} for r in rows]
        ql = []
        for rset, rlang, qid, q, lab in qs:
            ql.append({"set": rset, "lang": rlang, "qid": qid, "q": q,
                       "worth_asking": bool(H.embeddings.worth_asking(q, before_turn=True)),
                       "greeting": bool(H.text.is_greeting(q)),
                       "names_refuse": [back[r["fact_id"]] for r in rows if not p._retriever.names_fit(q, r)]})
            labels[f"{rset}|{rlang}|{qid}"] = {"store": sid, **lab}
        stores[sid] = {"facts": fl, "queries": ql}
        p.shutdown()
        print(f"  {sid}: {len(fl)} facts, {len(ql)} queries")
    pp.KEYWORDS = None
    (PACK / "stores.json").write_text(json.dumps(stores, ensure_ascii=False, indent=0), encoding="utf-8")
    (PACK / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=0), encoding="utf-8")


def vectors() -> None:
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    stores = json.loads((PACK / "stores.json").read_text(encoding="utf-8"))
    model = SentenceTransformer(str(ROOT / "vendor" / "models" / "bge-m3"), device="cuda", local_files_only=True,
                                model_kwargs={"torch_dtype": torch.float16})

    def enc(texts):
        return model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False).astype(np.float32)

    facts, queries, kw = [], [], {}
    for sid, s in stores.items():
        facts += [(sid, f) for f in s["facts"]]
        queries += [(sid, q) for q in s["queries"]]
        for f in s["facts"]:
            for k in f["keywords"]:
                kw.setdefault(k, len(kw))
    texts = {
        "c": [f["content"] for _, f in facts],
        "ct": [f["content"] + " " + (f["tags"] or "") for _, f in facts],  # sidecar server.py: content + " " + tags
        "tc": [(f["tags"] or "") + " " + f["content"] for _, f in facts],  # route C1: the order swapped
        "k": [", ".join(f["keywords"]) or f["content"] for _, f in facts],
        "label": [f["label"] for _, f in facts],
    }
    arrays = {f"F_{name}": enc(t) for name, t in texts.items()}
    arrays["KW"] = enc(list(kw))
    arrays["Q"] = enc([q["q"] for _, q in queries])
    np.savez_compressed(PACK / "vectors.npz", **arrays)
    index = {"facts": [[sid, f["key"]] for sid, f in facts],
             "fact_kw": [[kw[k] for k in f["keywords"]] for _, f in facts],
             "keywords": list(kw),
             "queries": [[q["set"], q["lang"], q["qid"]] for _, q in queries],
             "model": "bge-m3 (vendor/models/bge-m3), fp16 CUDA, normalized"}
    (PACK / "vectors_index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"  vectors: {len(facts)} facts x {len(texts)} texts, {len(kw)} keywords, {len(queries)} queries")


if __name__ == "__main__":
    steps = sys.argv[1:] or ["base", "stores", "vectors"]
    if "base" in steps:
        base_rows()
    if "stores" in steps:
        stores_and_labels()
    if "vectors" in steps:
        vectors()
