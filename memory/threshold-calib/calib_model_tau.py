"""semantic_tau for a local embedding model nobody measured, from the labelled question bank (rule P10L).

The bank holds the sets written in the languages the user writes in: zh is the synthetic set and household zh, en
and ru are household en and ru. The value is the lowest threshold at which, on every one of those sets, the
closest-fact admission appends a wrong fact to at most 10% of the no-answer questions. A model that rescues fewer
than 5 questions there adds nothing. With --store and --queries the value is also read on a frozen store with its
own labels, counts only. The rules are frozen in cloud-floor-freeze.json and the results are in
CLOUD-FLOOR-RESULTS.md. Each set runs through calib_cloud_floor.py with a local model, so nothing leaves the machine.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from calib_cloud_floor import GRID
from calib_lexical_levers import REPO

SETS = {"zh": (("synthetic", "zh"), ("household", "zh")), "en": (("household", "en"),), "ru": (("household", "ru"),)}
CAP = 0.10
MIN_RESCUED = 5


def part(out: dict) -> dict:
    """What the rule reads from one calib_cloud_floor run."""
    asked = out["step1"]["off"]
    return {"events": out["step3"]["local"]["events"], "answerable": asked["labelled"],
            "no_answer": asked["rows"] - asked["labelled"]}


def counts(one: dict, k: int) -> tuple[int, int]:
    """(questions rescued, no-answer questions given a wrong fact) at k hundredths."""
    hit = [(kind, answerable) for cos, kind, answerable in one["events"] if cos >= k / 100]
    return sum(kind == "rescue" for kind, _ in hit), sum(kind == "wrong" and not a for kind, a in hit)


def pick(parts: dict[str, dict], every_set: bool = False) -> dict | None:
    """The lowest threshold within the cap over the whole bank, or over every set on its own. None: no value on
    the grid stays within it."""
    for k in GRID:
        got = {name: counts(one, k) for name, one in parts.items()}
        if every_set:
            within = all(got[name][1] <= CAP * one["no_answer"] for name, one in parts.items())
        else:
            within = sum(w for _, w in got.values()) <= CAP * sum(one["no_answer"] for one in parts.values())
        if within:
            rescued = sum(r for r, _ in got.values())
            return {"tau": k / 100, "rescued": rescued, "wrong_no_answer": sum(w for _, w in got.values()),
                    "adds_something": rescued >= MIN_RESCUED, "per_set": {name: list(rw) for name, rw in got.items()}}
    return None


def report(model: str, parts: dict[str, dict]) -> dict:
    chosen = pick(parts, every_set=True)
    return {"model": model, "cap": CAP,
            "bank": {key: sum(one[key] for one in parts.values()) for key in ("answerable", "no_answer")},
            "every_set": chosen, "pooled": pick(parts),  # pooled: rule P10 as first frozen, for comparison
            # None: leave the closest-fact admission off for this model
            "semantic_tau": chosen["tau"] if chosen and chosen["adds_something"] else None}


def on_store(real: dict, picked: dict) -> dict:
    """The picked values read on a frozen store's own labels: rule_P10L_store_check in cloud-floor-freeze.json."""
    local, asked = real["step3"]["local"], real["step1"]["off"]
    quiet = asked["rows"] - asked["labelled"]

    def at(choice):
        if choice is None:
            return None
        key = f"{choice['tau']:.2f}"
        rescued, wrong = local["curve"][key]
        return {"tau": choice["tau"], "rescued": rescued, "wrong": wrong,
                "wrong_no_answer": local["wrong_no_answer"][key]}

    got, own = at(picked["every_set"]), local["choice_m2"]  # own: what the store's labels pick, None: nothing
    adds = picked["semantic_tau"] is not None
    return {"answerable": asked["labelled"], "no_answer": quiet, "every_set": got, "pooled": at(picked["pooled"]),
            "own_choice": own, "cap_holds": None if got is None else got["wrong_no_answer"] <= CAP * quiet,
            "verdict_holds": (got["rescued"] >= 1 and got["wrong"] <= got["rescued"]) if adds else own is None}


def run_set(args, folder: str, name: str, *suite: str) -> dict:
    target = Path(folder) / f"{name}.json"
    subprocess.run([sys.executable, "-X", "utf8", "-B", str(Path(__file__).with_name("calib_cloud_floor.py")),
                    *suite, "--modes", "local", "--floors", "--st-model", args.st_model,
                    "--core-src", str(args.core_src), "--plugin-src", str(args.plugin_src), "--out", str(target)],
                   check=True)
    return json.loads(target.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--st-model", required=True, help="a local sentence-transformers model directory")
    ap.add_argument("--langs", nargs="+", choices=list(SETS), default=list(SETS),
                    help="the languages the user writes in: the bank's sets in other languages are left out")
    ap.add_argument("--store", type=Path, help="a frozen SQLite copy to read the value on, opened read-only")
    ap.add_argument("--queries", type=Path, nargs="+", help="labelled questions for --store")
    ap.add_argument("--core-src", type=Path, required=True, help="Hermes core or the KG-1 core_shim")
    ap.add_argument("--plugin-src", type=Path, default=REPO / "vendor" / "holographic-0.30.0")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if bool(args.store) != bool(args.queries):
        ap.error("--store and --queries go together")
    parts, model = {}, ""
    with tempfile.TemporaryDirectory(prefix="model-tau-") as td:
        for suite, lang in dict.fromkeys(pair for chosen in args.langs for pair in SETS[chosen]):
            name = suite if suite == "synthetic" else f"{suite}_{lang}"
            out = run_set(args, td, name, "--suite", suite, "--lang", lang)
            parts[name], model = part(out), out["model"]
            print(f"{name}: {len(parts[name]['events'])} candidates", file=sys.stderr)
        result = report(model, parts)
        if args.store:  # the per-threshold counts of the store stay in the temporary folder
            real = run_set(args, td, "store", "--suite", "real", "--store", str(args.store),
                           "--queries", *map(str, args.queries))
            result["store"] = on_store(real, result)
    payload = json.dumps(result, ensure_ascii=True, indent=1)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
