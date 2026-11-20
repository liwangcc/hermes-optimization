"""One calibration run: embed a store's facts and a probe set once, sweep every admission rule over its values,
write the rows, then the working-point curve and the gate (calib_gate.py).

    # offline plumbing check: reproduces dryrun/ byte for byte
    python calib_run.py --stub --facts ../eval/facts.json --out dryrun/auto
    python calib_run.py --stub --facts ../eval/facts.json --queries ../eval/queries.json --out dryrun/labelled

    # a real run: any OpenAI-compatible embeddings endpoint, a COPY of a store, written outside the repository
    EMBED_URL=... EMBED_MODEL=... python calib_run.py --store /copy/of/store.db --out /outside/the/repo/run

Nothing is sent before the cost estimate is printed, and a remote endpoint also needs --yes. The endpoint's address
and key are never printed or written, not even hashed: the manifest says stub, local or remote. Vectors come from the
plugin's own client (embeddings.Embedder) and similarities exactly as retrieval.meaning makes them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

import calib_cost
import calib_gate
import calib_probes
import calib_vendor

HARNESS_VERSION = "tc-1"
REPO = Path(__file__).resolve().parents[2]
STUB_MODEL, STUB_DIM = "stub-charbigram-256", 256
MARGINS = (-0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
FLOOR_POINTS = 11  # default cosine values of a floor rule: quantiles of the probes' closest similarities
MIN_TRUST = 0.3  # the plugin's default min_trust_threshold: by_meaning skips facts below it
REQUEST_SECONDS = 120.0  # per request: a local server took 7.7 s for 32 facts (embeddings.py:68-69, issue #5)


def stub_vector(text: str) -> list[float]:
    """Offline and deterministic: signed hashed character bigrams (sha256, so no PYTHONHASHSEED in it)."""
    vector = [0.0] * STUB_DIM
    t = " ".join(text.lower().split())
    for gram in [t[i:i + 2] for i in range(len(t) - 1)] or [t or " "]:
        h = int.from_bytes(hashlib.sha256(gram.encode("utf-8")).digest()[:4], "little")
        vector[h % STUB_DIM] += 1.0 if (h >> 16) & 1 else -1.0
    if not any(vector):
        vector[0] = 1.0  # the client refuses a zero vector
    return vector


def embedder(v, args):
    """The plugin's Embedder on the endpoint the arguments name, or on the stub (no socket is ever opened)."""
    if args.stub:
        class Stub(v.emb.Embedder):
            def _request(self, batch, budget=None, fact=False, timing=None):
                payload = {"data": [{"index": i, "embedding": stub_vector(t)} for i, t in enumerate(batch)]}
                return v.emb._vectors(payload, len(batch))

        return Stub(v.emb.Settings({"embedding_url": "http://localhost/v1", "embedding_model": STUB_MODEL}))
    return v.emb.Embedder(v.emb.Settings({
        "embedding_url": args.embed_url, "embedding_model": args.embed_model, "embedding_key_env": args.embed_key_env,
        "embedding_dimensions": args.embed_dimensions, "embedding_timeout": 6.0}))  # 6.0: the plugin's maximum


def embed(emb, texts: list[str], batch: int):
    """Vectors of *texts*, *batch* to a request, each request with REQUEST_SECONDS: a slow local server is waited
    for, a dead one fails in bounded time. Facts go in the plugin's batches of 32 (embed_facts); probes one to a
    request, as Embedder.query sends a message (a server batching with padding may give other vectors)."""
    out = []
    for start in range(0, len(texts), batch):
        got = emb.embed(texts[start:start + batch], budget=REQUEST_SECONDS)
        if got is None:
            raise SystemExit(f"embedding failed: {emb.status()}")  # a category, never the key or the address
        out += got
    return np.vstack(out) if out else []


def floor_grid(sims: list, keep: int) -> list[float]:
    """FLOOR_POINTS quantiles of the *keep* closest similarities of every embedded probe, rounded down to 0.001."""
    pool = np.concatenate([np.sort(s)[::-1][:keep] for _, s in filter(None, sims)])
    return sorted({math.floor(float(q) * 1000) / 1000 for q in np.quantile(pool, np.linspace(0, 1, FLOOR_POINTS))})


def similarities(probes, fact_ids: list[int], fact_vecs, probe_vecs) -> list:
    """Per probe (ids, cosines) over the store as the plugin holds it — its own fact held out for a holdout — or
    None when the plugin would not embed the probe."""
    pos = {fact_id: k for k, fact_id in enumerate(fact_ids)}
    vecs = iter(probe_vecs)
    out = []
    for p in probes:
        if p["meaning_call"] != "ok":
            out.append(None)
            continue
        ids, matrix = fact_ids, fact_vecs
        if p["holdout"] is not None:  # the store without that fact, as the plugin would hold it
            k = pos[p["holdout"]]
            ids, matrix = ids[:k] + ids[k + 1:], np.delete(fact_vecs, k, axis=0)
        out.append((ids, matrix @ next(vecs)))  # retrieval.meaning: matrix @ vector
    return out


def sweep(v, probes, sims, grids: dict, keep: int, eligible: set, recallable: set | None = None) -> list[dict]:
    """A row per rule x value x probe: the facts admitted on meaning."""
    out = []
    for p, got in zip(probes, sims):
        if got is not None:
            meaning, floor = v.emb.Meaning(*got, 0.0), v.FloorMeaning(*got, 0.0)
            ranked = meaning.ranked()
        for rule, values in grids.items():
            for value in values:
                keys = []
                if got is not None:
                    margin, min_score = calib_vendor.standout_args(v, rule, value)
                    if rule == "floor":
                        floor.floor = value
                    keys = calib_vendor.walk(floor if rule == "floor" else meaning, ranked, margin, min_score, keep,
                                             eligible, recallable)
                out.append({"rule": rule, "value": value, "qid": p["qid"], "keys": keys})
    order = {(rule, value): k for k, (rule, value) in enumerate((r, x) for r, xs in grids.items() for x in xs)}
    return sorted(out, key=lambda r: order[(r["rule"], r["value"])])  # stable: probe order inside a point


def _floats(text: str | None):
    return None if text is None else [float(x) for x in text.split(",") if x.strip()]


def _write_jsonl(path: Path, rows: list[dict], **dump) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, **dump) + "\n")


def run(args) -> dict | None:
    v = calib_vendor.load(args.plugin_src)
    if not args.stub and not (args.embed_url and args.embed_model):
        raise SystemExit("set EMBED_URL and EMBED_MODEL (or --embed-url / --embed-model), or pass --stub")
    out = Path(args.out).resolve()
    if args.store and out.is_relative_to(REPO):
        raise SystemExit("a run on a real store keeps its text (probes.jsonl): write it outside the repository and "
                         "export it with calib_opaque.py")
    rules = [r for r in args.rules.split(",") if r]
    for rule in rules:
        calib_vendor.standout_args(v, rule, 0.0)  # refuses an unknown rule before anything is sent

    facts = calib_probes.load_facts(args.facts, args.store)
    sendable = [f for f in facts if v.screen._sendable(f["content"])]
    if not sendable:
        raise SystemExit("no fact of this store may be sent to an embeddings endpoint")
    # by_meaning's trust filter (NULL never passes `trust_score >= ?`), then prefetch's _recallable: a sendable fact
    # has no _recall_problem, so what is left is _role_prompt
    eligible = {f["fact_id"] for f in sendable if f["trust_score"] is not None and f["trust_score"] >= MIN_TRUST}
    recallable = {f["fact_id"] for f in sendable if not v.screen._role_prompt(f["content"])}

    def embeddable(text):  # the plugin's test before it embeds a message (__init__.py:1522-1523)
        return not v.screen._secret_in(text) and v.emb.worth_asking(text, before_turn=True)

    # auto probes only from facts prefetch could admit: any other positive could never be hit
    pool = [f for f in sendable if f["fact_id"] in eligible & recallable]
    probes = (calib_probes.labelled_probes(args.queries, {f["fact_id"] for f in facts}) if args.queries
              else calib_probes.auto_probes(pool, args.auto, args.seed, embeddable))
    for p in probes:
        p["meaning_call"] = "ok" if embeddable(p["q"]) else "skipped"
    asked = [p["q"] for p in probes if p["meaning_call"] == "ok"]
    if not asked:  # refused before anything is sent
        raise SystemExit("the plugin would embed none of these probes (worth_asking / secret screen)")

    emb = embedder(v, args)
    if emb._refused:  # the plugin's own address check: plain http to a public host, not http(s), malformed
        raise SystemExit(emb._refused)
    model = STUB_MODEL if args.stub else args.embed_model
    local = args.stub or emb._local
    cut = v.emb.TEXT_MAX_CHARS
    texts = [f["content"] for f in sendable] + asked
    est = calib_cost.estimate([t[:cut] for t in texts], model, local, args.price_per_mtok)
    print(calib_cost.line(len(texts), est))
    if not local and not args.yes:
        print("remote endpoint: nothing was sent. Add --yes to send these texts.")
        return None
    why = emb.unavailable()
    if why:
        raise SystemExit(f"the endpoint cannot be used: {why}")
    fact_ids = [f["fact_id"] for f in sendable]
    sims = similarities(probes, fact_ids, embed(emb, [f["content"] for f in sendable], v.emb.BATCH),
                        embed(emb, asked, 1))

    margins = sorted(set(_floats(args.margins) or MARGINS) | {v.emb.RECALL_MARGIN})
    floors = sorted(set(_floats(args.floor_values) or floor_grid(sims, args.keep)))
    # the default point (zbar at RECALL_MARGIN) is always swept: every point is judged against it
    grids = {"zbar": margins if "zbar" in rules else [v.emb.RECALL_MARGIN]}
    grids.update({rule: floors for rule in ("zbar_floor", "floor") if rule in rules})
    rows = sweep(v, probes, sims, grids, args.keep, eligible, recallable)

    manifest = {  # no address, not even hashed: a hash of a well-known address is recognised by hashing it again
        "tool": "threshold-calib", "harness_version": HARNESS_VERSION, "plugin_version": v.version, "emb": model,
        "endpoint": "stub" if args.stub else "local" if local else "remote",
        "probe_source": "labelled" if args.queries else "auto",
        "seed": None if args.queries else args.seed, "auto_n": None if args.queries else args.auto,
        "keep": args.keep, "min_trust": MIN_TRUST, "recall_margin": v.emb.RECALL_MARGIN,
        "min_vectors_for_z": v.emb.MIN_VECTORS_FOR_Z, "fact_n": len(facts), "vec_n": len(sendable),
        "unsendable_n": len(facts) - len(sendable), "below_trust_n": len(sendable) - len(eligible),
        "role_prompt_n": len(sendable) - len(recallable),
        "probes_n": len(probes), "probes_skipped_n": len(probes) - len(asked),
        "est_texts": len(texts), "est_tokens": est["tokens"], "est_usd": est["usd"],
        **{f"grid_{rule}": values for rule, values in grids.items()},
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                       newline="\n")
    _write_jsonl(out / "probes.jsonl", probes, ensure_ascii=False)
    _write_jsonl(out / "rows.jsonl", rows, separators=(",", ":"))
    summary, digest = calib_gate.write(out, v)
    print(f"{len(rows)} rows, {len(probes)} probes -> {args.out}; summary sha256 {digest}")
    return summary


def main(argv=None) -> dict | None:
    env = os.environ.get
    ap = argparse.ArgumentParser(description="calibrate the meaning admission of one embedding model on one store")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--facts", help="a JSON list of facts (the synthetic set)")
    src.add_argument("--store", help="a COPY of a holographic SQLite store, opened read-only")
    ap.add_argument("--queries", help="a labelled query file; without it the probes are made from the store")
    ap.add_argument("--auto", type=int, default=40, help="probes made from the store (a quarter held out), default 40")
    ap.add_argument("--seed", type=int, default=20261117, help="the draw of facts for auto probes")
    ap.add_argument("--keep", type=int, default=1, choices=(1, 2, 3),
                    help="facts admitted on meaning per probe: the plugin's embedding_prefetch_facts (default 1)")
    ap.add_argument("--rules", default="zbar,zbar_floor,floor", help="admission rules to sweep (calib_vendor.RULES)")
    ap.add_argument("--margins", help="comma-separated margins for zbar (default -0.5..2.0 by 0.25)")
    ap.add_argument("--floor-values", help="comma-separated cosines for zbar_floor and floor (default: quantiles)")
    ap.add_argument("--stub", action="store_true", help="the offline deterministic embedder: plumbing only")
    ap.add_argument("--embed-url", default=env("EMBED_URL"), help="the /v1 base address (env EMBED_URL)")
    ap.add_argument("--embed-model", default=env("EMBED_MODEL"), help="the model id (env EMBED_MODEL)")
    ap.add_argument("--embed-key-env", default=env("EMBED_KEY_ENV"),
                    help="the NAME of the variable holding the key (env EMBED_KEY_ENV; default: the plugin's own)")
    ap.add_argument("--embed-dimensions", default=env("EMBED_DIMENSIONS"),
                    help="the plugin's embedding_dimensions, when your config sets it (env EMBED_DIMENSIONS)")
    ap.add_argument("--price-per-mtok", type=float, help="USD per million tokens, for a remote model not listed")
    ap.add_argument("--yes", action="store_true", help="send to a remote endpoint after the estimate")
    ap.add_argument("--plugin-src", default=calib_vendor.DEFAULT_SRC, help="the plugin snapshot (read only)")
    ap.add_argument("--out", required=True, help="the run directory")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
