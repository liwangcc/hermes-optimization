"""A score dump for replaying admission rules offline (calib_replay.py): every probe's cosine to every fact of a
store, once per vector text. The dump holds ids and numbers, never a text.

    # the synthetic set on a local sentence-transformers model, loaded as ../eval/run_eval.py loads it
    BGE_MODEL=/path/to/bge-m3 python calib_dump.py --facts F.json --keywords K.json --queries Q.json QX.json --out D.json

    # a COPY of a real store through an OpenAI-compatible endpoint, exactly as calib_run.py sends
    EMBED_URL=... EMBED_MODEL=... python calib_dump.py --store /copy.db --queries Q.json --out /outside/the/repo/D.json

    python calib_dump.py --stub ...     # offline plumbing check

Vector texts (VARIANTS): the fact's content; content+keywords as upstream's vector_text joins them; the keywords
alone as one vector; and one vector per keyword, the fact scoring its closest keyword. A fact without keywords keeps
its content in all four (listed under no_keywords): its numbers there are not comparable with a keyword vector's.
Keywords come from --keywords ({fact_id: [keyword, ...]}), else from a store's tags as the snapshot splits them.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

import numpy as np

import calib_cost
import calib_probes
import calib_run
import calib_vendor

HARNESS_VERSION = "td-1"
VARIANTS = ("content", "content+keywords", "keywords", "keyword-max")
KW_MARK = "keywords: "  # upstream text._KW_MARK: vector_text puts the keywords on a line after the content


def keywords_of(v, args) -> dict[int, list[str]]:
    if args.keywords:
        data = json.loads(Path(args.keywords).read_text(encoding="utf-8"))
        return {int(k): [w.strip() for w in ws if w.strip()] for k, ws in data.items()}
    if not args.store:
        return {}
    split = getattr(v.emb, "_split_tags", None)  # the plugin's own split of a stored tags value (0.30+)
    if split is None:
        raise SystemExit("this snapshot does not split keywords from tags: pass --keywords, or a newer --plugin-src")
    con = sqlite3.connect(Path(args.store).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return {int(i): split(tags)[1] for i, tags in con.execute("SELECT fact_id, tags FROM facts")}
    finally:
        con.close()


def vectors_by(v, args, texts: list[str]):
    """(texts, batch) -> unit vectors, the model's name, and where it runs. Nothing goes to a remote endpoint before
    the estimate is printed and --yes is given, as in calib_run."""
    if args.st_model:
        import torch  # only this backend needs it
        from sentence_transformers import SentenceTransformer
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        model = SentenceTransformer(args.st_model, device=dev,
                                    model_kwargs={"torch_dtype": torch.float16} if dev == "cuda" else {})
        cut = v.emb.TEXT_MAX_CHARS
        return (lambda ts, batch: np.asarray(model.encode([t[:cut] for t in ts], normalize_embeddings=True,
                                                          batch_size=16, show_progress_bar=False), dtype=np.float64),
                Path(args.st_model).name, "local")
    if not args.stub and not (args.embed_url and args.embed_model):
        raise SystemExit("set BGE_MODEL (--st-model), or EMBED_URL and EMBED_MODEL, or pass --stub")
    emb = calib_run.embedder(v, args)
    if emb._refused:
        raise SystemExit(emb._refused)
    model = calib_run.STUB_MODEL if args.stub else args.embed_model
    local = args.stub or emb._local
    est = calib_cost.estimate([t[:v.emb.TEXT_MAX_CHARS] for t in texts], model, local, args.price_per_mtok)
    print(calib_cost.line(len(texts), est))
    if not local and not args.yes:
        raise SystemExit("remote endpoint: nothing was sent. Add --yes to send these texts.")
    why = emb.unavailable()
    if why:
        raise SystemExit(f"the endpoint cannot be used: {why}")
    return (lambda ts, batch: calib_run.embed(emb, ts, batch)), model, "stub" if args.stub else "local" if local else "remote"


def run(args) -> dict:
    v = calib_vendor.load(args.plugin_src)
    out = Path(args.out).resolve()
    if args.store and out.is_relative_to(calib_run.REPO):
        raise SystemExit("a real store's dump stays outside the repository: share calib_replay.py's summary instead")
    stored = calib_probes.load_facts(args.facts, args.store)
    facts = [f for f in stored if v.screen._sendable(f["content"])]  # the others get no vector, as in the plugin
    if not facts:
        raise SystemExit("no fact of this store may be sent to an embeddings endpoint")
    ids = [f["fact_id"] for f in facts]
    probes = [p for path in args.queries for p in calib_probes.labelled_probes(path, {f["fact_id"] for f in stored})]
    if len({p["qid"] for p in probes}) != len(probes):
        raise SystemExit("two queries share a qid across the query files")
    for p in probes:  # the plugin's test before it embeds a message, as calib_run
        ok = not v.screen._secret_in(p["q"]) and v.emb.worth_asking(p["q"], before_turn=True)
        p["meaning_call"] = "ok" if ok else "skipped"
    asked = [p["q"] for p in probes if p["meaning_call"] == "ok"]
    if not asked:
        raise SystemExit("the plugin would embed none of these probes (worth_asking / secret screen)")

    kw = keywords_of(v, args)
    texts = {"content": [f["content"] for f in facts], "content+keywords": [], "keywords": []}
    words, owner = [], []  # every keyword of every fact, and the row of the fact it belongs to
    for row, f in enumerate(facts):
        joined = f"{f['content']}\n{KW_MARK}{', '.join(kw.get(f['fact_id']) or [])}"
        mine = (kw.get(f["fact_id"]) or []) if v.screen._sendable(joined) else []  # vector_text's own condition
        texts["content+keywords"].append(joined if mine else f["content"])
        texts["keywords"].append(", ".join(mine) if mine else f["content"])
        words += mine or [f["content"]]
        owner += [row] * len(mine or [0])
    everything = [t for ts in texts.values() for t in ts] + words + asked
    vectors, model, where = vectors_by(v, args, everything)

    probe_vecs = vectors(asked, 1)
    cos = {name: vectors(ts, v.emb.BATCH) @ probe_vecs.T for name, ts in texts.items()}  # facts x asked
    per_word = vectors(words, v.emb.BATCH) @ probe_vecs.T
    cos["keyword-max"] = np.vstack([per_word[[k for k, o in enumerate(owner) if o == row]].max(axis=0)
                                    for row in range(len(facts))])
    column = iter(range(len(asked)))
    rows = []
    for p in probes:
        k = next(column) if p["meaning_call"] == "ok" else None
        rows.append({"qid": p["qid"], "kind": p["kind"], "category": p["category"], "lang": p["lang"],
                     "targets": p["targets"], "meaning_call": p["meaning_call"],
                     "cos": {} if k is None else {name: [round(float(x), 6) for x in cos[name][:, k]]
                                                  for name in VARIANTS}})
    with_kw = {f["fact_id"] for f, t in zip(facts, texts["keywords"]) if t != f["content"]}
    dump = {
        "manifest": {"tool": "threshold-calib-dump", "harness_version": HARNESS_VERSION, "plugin_version": v.version,
                     "emb": model, "endpoint": where, "variants": list(VARIANTS), "fact_n": len(facts),
                     "keywords_fact_n": len(with_kw), "keyword_texts_n": len(words), "min_trust": calib_run.MIN_TRUST,
                     "probes_n": len(probes), "probes_skipped_n": len(probes) - len(asked)},
        "fact_ids": ids,
        "eligible": [f["fact_id"] for f in facts
                     if f["trust_score"] is not None and f["trust_score"] >= calib_run.MIN_TRUST],
        "recallable": [f["fact_id"] for f in facts if not v.screen._role_prompt(f["content"])],
        "no_keywords": [i for i in ids if i not in with_kw],
        "probes": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dump, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(probes)} probes x {len(facts)} facts x {len(VARIANTS)} vector texts ({model}, {where}) -> {args.out}")
    return dump


def main(argv=None) -> dict:
    env = os.environ.get
    ap = argparse.ArgumentParser(description="dump probe-to-fact cosines per vector text, for calib_replay.py")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--facts", help="a JSON list of facts (the synthetic set)")
    src.add_argument("--store", help="a COPY of a holographic SQLite store, opened read-only")
    ap.add_argument("--keywords", help="{fact_id: [keyword, ...]}; without it a store's tags are split by the snapshot")
    ap.add_argument("--queries", nargs="+", required=True, help="labelled query files (calib_probes formats)")
    ap.add_argument("--stub", action="store_true", help="the offline deterministic embedder: plumbing only")
    ap.add_argument("--st-model", default=env("BGE_MODEL"), help="a local sentence-transformers model (env BGE_MODEL)")
    ap.add_argument("--embed-url", default=env("EMBED_URL"), help="the /v1 base address (env EMBED_URL)")
    ap.add_argument("--embed-model", default=env("EMBED_MODEL"), help="the model id (env EMBED_MODEL)")
    ap.add_argument("--embed-key-env", default=env("EMBED_KEY_ENV"), help="the NAME of the variable holding the key")
    ap.add_argument("--embed-dimensions", default=env("EMBED_DIMENSIONS"), help="the plugin's embedding_dimensions")
    ap.add_argument("--price-per-mtok", type=float, help="USD per million tokens, for a remote model not listed")
    ap.add_argument("--yes", action="store_true", help="send to a remote endpoint after the estimate")
    ap.add_argument("--plugin-src", default=calib_vendor.DEFAULT_SRC, help="the plugin snapshot (read only)")
    ap.add_argument("--out", required=True, help="the dump file")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
