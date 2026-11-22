"""Scheme three on fresh probe rows: the one fact a uniform 0.5 margin adds is kept only when a small local
cross-encoder says it answers the question. See UPSTREAM-VERIFY-GATE-RESULTS.md.

The two sides are rows of tools/provenance_probe.py at the default margin and at 0.5. A row is taken from the 0.5
side only when it adds exactly one fact, on meaning alone, after everything the default side shows, and the
check approves it; every other row stays as the default side has it. The guards are the upstream gate's own
functions (calib_margin_gate.compare). --approve all and --approve oracle bound what any check could reach.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import time
from pathlib import Path

from calib_margin_gate import compare, load
from calib_margin_verify import documents_for, new_candidate, public_facts


def facts_name(name):
    return "household_test" if name.startswith("household") else name  # both splits share the household facts


def candidates(root, name, base, wide):
    """{row key: (fact key, the fact line as prefetch shows it)} for rows whose only change is one fact by meaning."""
    facts = public_facts(root, facts_name(name))
    found = {}
    for key, before in base.items():
        docs = documents_for(facts, facts_name(name), before["lang"])
        fact = new_candidate(before, wide[key], docs)
        if fact is not None:
            flat = " ".join(docs[fact][0].split())
            found[key] = (fact, flat if len(flat) <= 300 else flat[:299] + "…")
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plugin", type=Path, required=True, help="the plugin checkout the rows came from")
    ap.add_argument("--rows", type=Path, required=True, help="directory of provenance_<set><suffix>_on.jsonl files")
    ap.add_argument("--sets", nargs="+", required=True)
    ap.add_argument("--base", default="_m1.0")
    ap.add_argument("--wide", default="_m0.5")
    ap.add_argument("--approve", nargs="+", default=["all", "oracle"], choices=["all", "oracle", "verifier"])
    ap.add_argument("--verifier", type=Path, help="local Qwen3-Reranker-0.6B directory, for --approve verifier")
    ap.add_argument("--model-card-instruction", action="store_true", help="the reranker's published search prompt")
    args = ap.parse_args()
    if "verifier" in args.approve and not args.verifier:
        ap.error("--approve verifier needs --verifier")
    spec = importlib.util.spec_from_file_location("upstream_mcnemar_gate", args.plugin / "tools" / "mcnemar_gate.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    base, wide, single = {}, {}, {}
    for name in args.sets:
        one = load(args.rows / f"provenance_{name}{args.base}_on.jsonl")
        two = load(args.rows / f"provenance_{name}{args.wide}_on.jsonl")
        single.update(candidates(args.plugin, name, one, two))
        base.update(one)
        wide.update(two)
    changed = sum(base[k]["keys"] != wide[k]["keys"] for k in base)
    right = sum(fact in base[k]["targets"] for k, (fact, _) in single.items())
    out = {"sets": args.sets, "rows": len(base), "rows_changed_at_0.5": changed, "single_candidates": len(single),
           "candidates_that_are_targets": right, "uniform_0.5": compare(gate, base, wide), "approved": {}}
    scores, times = {}, []
    if "verifier" in args.approve:
        from calib_answerability import INSTRUCTION, MODEL_CARD_INSTRUCTION, AnswerVerifier
        model = AnswerVerifier(args.verifier, MODEL_CARD_INSTRUCTION if args.model_card_instruction else INSTRUCTION)
        for key, (_, text) in single.items():
            start = time.perf_counter()
            scores[key] = model.score(base[key]["q"], text)
            times.append(1000 * (time.perf_counter() - start))
    rules = {"all": lambda k: True, "oracle": lambda k: single[k][0] in base[k]["targets"],
             "verifier": lambda k: scores[k] > 0}
    for mode in args.approve:
        taken = {k for k in single if rules[mode](k)}
        result = compare(gate, base, {k: (wide[k] if k in taken else base[k]) for k in base})
        result["approved"] = len(taken)
        result["approved_targets"] = sum(single[k][0] in base[k]["targets"] for k in taken)
        out["approved"][mode] = result
    if times:
        out["verifier_calls"], out["verifier_median_ms"] = len(times), round(statistics.median(times), 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
