"""recall_dump.py for the private real store: a read-only copy of the store and its frozen labels.

The dump holds the store's text, so it must be written outside the repository; report.py on it prints counts only.
    python -X utf8 -B dump_real.py --store <frozen copy> --queries <labels.json> --core-src <core_shim> --out <dir>
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import recall_dump as rd
from calib_lexical_levers import backup
from calib_probes import labelled_probes


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--queries", type=Path, nargs="+", required=True)
    ap.add_argument("--core-src", type=Path, required=True)
    ap.add_argument("--model", type=Path, default=rd.REPO / "vendor" / "models" / "bge-m3")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.suite, args.lang = "real", "-"
    if args.out.resolve().is_relative_to(rd.REPO):
        ap.error("the dump holds the store's text: write it outside the repository")
    opened = rd.open_provider

    def open_copy(pkg, db, home, **config):
        backup(args.store.resolve(strict=True).as_uri() + "?mode=ro", db)
        return opened(pkg, db, home, **config)

    def build_real(pkg, provider, suite, lang):
        known = {i for (i,) in provider._store.read("SELECT fact_id FROM facts")}
        probes = [p for path in args.queries for p in labelled_probes(str(path), known)]
        return [{"qid": p["qid"], "q": p["q"], "targets": p["targets"], "category": p.get("category") or "real"}
                for p in probes], {}

    rd.open_provider, rd.build = open_copy, build_real
    sys.dont_write_bytecode = True
    logging.disable(logging.CRITICAL)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    args.out.mkdir(parents=True, exist_ok=True)
    rd.run(args)


if __name__ == "__main__":
    main()
