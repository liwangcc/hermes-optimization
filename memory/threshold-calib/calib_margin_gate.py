"""The four guards of the upstream margin gate over rows of tools/provenance_probe.py, for a pair the patched
gate refuses: two runs with the same margin that differ only in margin_shown. See UPSTREAM-MARGIN-GATE-RESULTS.md.

Noise, confusion and the exact McNemar p are the upstream tool's own functions (loaded from --gate); only the
pairing of the two sides is done here. Run it on a pair the upstream tool accepts first: the numbers must agree.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path


def load(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    keyed = {(r["set"], r["lang"], r["qid"]): r for r in rows}
    if len(keyed) != len(rows):
        raise SystemExit(f"duplicated rows in {path}")
    return keyed


def compare(gate, base, arm):
    """Counts of one pooled comparison; the rows of the two sides must be the same questions."""
    if set(base) != set(arm):
        raise SystemExit("the two sides hold different questions")
    out = Counter()
    gained, noisy = [], []
    for key, before in base.items():
        after = arm[key]
        if before["q"] != after["q"] or set(before["targets"]) != set(after["targets"]):
            raise SystemExit(f"{key}: the two sides disagree on the question or its targets")
        real = before["kind"] == "real"
        out.update(rows=1, real=real, hit_base=bool(real and before["hit5"]), hit_arm=bool(real and after["hit5"]),
                   b=bool(real and after["hit5"] and not before["hit5"]),
                   c=bool(real and before["hit5"] and not after["hit5"]),
                   lost_targets=len((set(before["targets"]) & set(before["keys"][:5])) - set(after["keys"][:5])),
                   noise_base=gate._noise(before), noise_arm=gate._noise(after),
                   confused_base=bool(real and gate._confused(before)), confused_arm=bool(real and gate._confused(after)))
        if real and after["hit5"] and not before["hit5"]:
            gained.append("/".join(map(str, key)))
        if gate._noise(after) and not gate._noise(before):
            noisy.append("/".join(map(str, key)))
    p = gate.mcnemar(out["b"], out["c"])
    guards = {"no target lost": out["lost_targets"] == 0, "noise not higher": out["noise_arm"] <= out["noise_base"],
              "confusion not higher": out["confused_arm"] <= out["confused_base"],
              "McNemar p < 0.05 with b > c": p < 0.05 and out["b"] > out["c"]}
    return {**dict(out), "p": round(p, 4), "guards": guards, "passes": all(guards.values()), "gained": gained,
            "new_noise_rows": noisy}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gate", type=Path, required=True, help="tools/mcnemar_gate.py of the plugin checkout")
    ap.add_argument("--rows", type=Path, required=True, help="directory of provenance_<set><suffix>_on.jsonl files")
    ap.add_argument("--sets", nargs="+", required=True, help="set names as in the file names, e.g. household_test")
    ap.add_argument("--base", default="_m1.0", help="file suffix of the default side")
    ap.add_argument("--arm", required=True, help="file suffix of the proposal, e.g. _m1.0_s0.5")
    ap.add_argument("--tail", default="", help="what follows the margin in the file name, e.g. _kwall")
    args = ap.parse_args()
    spec = importlib.util.spec_from_file_location("upstream_mcnemar_gate", args.gate)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    base, arm = {}, {}
    per_set = {}
    for name in args.sets:
        one = load(args.rows / f"provenance_{name}{args.base}{args.tail}_on.jsonl")
        two = load(args.rows / f"provenance_{name}{args.arm}{args.tail}_on.jsonl")
        per_set[name] = compare(gate, one, two)
        base.update(one)
        arm.update(two)
    print(json.dumps({"base": args.base, "arm": args.arm, "sets": args.sets, "pooled": compare(gate, base, arm),
                      "per_set": {k: {f: v[f] for f in ("real", "hit_base", "hit_arm", "b", "c", "noise_base",
                                                        "noise_arm", "confused_base", "confused_arm")}
                                  for k, v in per_set.items()}}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
