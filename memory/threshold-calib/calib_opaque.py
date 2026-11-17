"""Opaque export of a calibration run: the only form in which a run on a real store may leave the machine.

    python calib_opaque.py RUN_DIR OUT_DIR      # then: python calib_gate.py OUT_DIR

The manifest, the probes and the rows keep their numbers, booleans, lists of numbers and run stamps; the probe text
(`q`) and every other text field are dropped, and probe ids and unknown category names are replaced by neutral ones.
A leak scan then refuses the whole export if any string is left that is not a stamp made of identifier characters: a
stamp field carrying prose is a leak too, named, never quoted. Nothing is written unless every file passes.
calib_gate.py runs on the export unchanged, with the same numbers. (The KG-1 kg_opaque.py pattern.)
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# The only fields that may hold a string, and only as a token.
STAMPS = frozenset({"tool", "harness_version", "plugin_version", "emb", "endpoint", "endpoint_id", "probe_source",
                    "rule", "qid", "kind", "category", "lang", "meaning_call"})
_TOKEN = re.compile(r"[A-Za-z0-9_.:@/+-]{1,64}")
FILES = ("manifest.json", "probes.jsonl", "rows.jsonl")
# Category names anyone may read: this tool's auto probes, ../eval/queries.json, KG-1's unified format.
CATEGORIES = frozenset({"fragment", "holdout", "chit", "direct", "paraphrase", "crosslingual", "colloquial",
                        "negative", "no_answer", "real"})


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _opaque_value(value) -> bool:
    return value is None or isinstance(value, bool) or _number(value) or (
        isinstance(value, list) and all(_number(x) for x in value))


def opaque(row: dict) -> dict:
    """*row* without its text: stamps, numbers, booleans and lists of numbers only."""
    return {k: v for k, v in row.items() if (isinstance(v, str) and k in STAMPS) or _opaque_value(v)}


def leak_scan(rows: list[dict]) -> None:
    """SystemExit if anything in *rows* could carry text. Names the field, never its value."""
    for number, row in enumerate(rows, 1):
        for key, value in row.items():
            if not (_opaque_value(value) or (key in STAMPS and isinstance(value, str) and _TOKEN.fullmatch(value))):
                raise SystemExit(f"record {number}: field {key!r} would carry text out; nothing was exported")


def renamed(probes: list[dict], rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """qids become q0001... in probe order, and a category outside CATEGORIES becomes cat1..., alike in both files:
    the ids and category names of a labelled file are words someone wrote."""
    qid = {p["qid"]: f"q{k:04d}" for k, p in enumerate(probes, 1)}
    cats: dict = {}
    for p in probes:
        if p.get("category") not in CATEGORIES:
            cats.setdefault(p.get("category"), f"cat{len(cats) + 1}")
    if any(r.get("qid") not in qid for r in rows):
        raise SystemExit("a row names a probe the run does not have; nothing was exported")
    return ([{**p, "qid": qid[p["qid"]], "category": cats.get(p.get("category"), p.get("category"))} for p in probes],
            [{**r, "qid": qid[r["qid"]]} for r in rows])


def export(run_dir: Path, out_dir: Path) -> int:
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    files = {}
    for name in FILES:
        text = (run_dir / name).read_text(encoding="utf-8")
        files[name] = [json.loads(text)] if name.endswith(".json") else [json.loads(x) for x in text.splitlines()
                                                                         if x.strip()]
    files["probes.jsonl"], files["rows.jsonl"] = renamed(files["probes.jsonl"], files["rows.jsonl"])
    for name, records in files.items():
        files[name] = [opaque(r) for r in records]
        leak_scan(files[name])
    out_dir.mkdir(parents=True, exist_ok=True)  # only now: every file passed the scan
    for name, records in files.items():
        with open(out_dir / name, "w", encoding="utf-8", newline="\n") as fh:
            if name.endswith(".json"):
                fh.write(json.dumps(records[0], indent=1, sort_keys=True) + "\n")  # ASCII only
            else:
                fh.writelines(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records)
    return sum(len(r) for r in files.values())


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="opaque export of a calibration run: no text leaves")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("out_dir", type=Path)
    args = ap.parse_args(argv)
    print(f"{export(args.run_dir, args.out_dir)} opaque records -> {args.out_dir}")


if __name__ == "__main__":
    main()
