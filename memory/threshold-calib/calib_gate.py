"""The working-point curve and the PR #17 gate over a calibration run.

    python calib_gate.py RUN_DIR      # reads manifest.json, probes.jsonl, rows.jsonl; writes summary.json, report.md

Every point of every rule is judged against the upstream default (zbar at the plugin's RECALL_MARGIN, no floor) on
the four conditions of PR #17, as the vendored tools/mcnemar_gate.py (report_margins) states them: no target lost
from the top five, noise not higher, confusion not higher, exact McNemar p < 0.05 on hit@5. The p-value and the
noise definition are that file's own functions, called, not copied. A point that fails is written out exactly like
one that passes; nothing here picks a point.

What is measured is the meaning channel alone: a row's keys are the facts admitted on meaning, so hit@5 is "a target
was admitted". Words, entities and names_fit are not in it (see DESIGN.md, limits).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

import calib_vendor

CAVEAT_EXPLORATORY = ("Every point is judged on the probes the sweep ran on: choosing the best of many points "
                      "inflates significance. A value becomes a reference value only after a confirmation run of that "
                      "single value on other probes (another --seed, or a labelled set).")
CAVEAT_AUTO = ("auto probes are the middle half of a stored fact: they share words with their target, so recall here "
               "is optimistic for real paraphrases. Noise (holdout, chit) and confusion are the dependable side.")
CAVEAT_FLOOR = ("floor is an experimental admission mode, not an upstream default and not proposed as one; its "
                "values do not carry over between models.")


def load(run_dir: Path) -> tuple[dict, list[dict], list[dict]]:
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    def jsonl(name):
        return [json.loads(line) for line in (run_dir / name).read_text(encoding="utf-8").splitlines() if line.strip()]

    return manifest, jsonl("probes.jsonl"), jsonl("rows.jsonl")


def points(manifest: dict, probes: list[dict], rows: list[dict]) -> dict[tuple, dict]:
    """{(rule, value): {qid: keys}}; refuses duplicates, unknown probes and points that do not cover every probe."""
    qids = [p["qid"] for p in probes]
    dup = sorted(q for q, n in collections.Counter(qids).items() if n > 1)
    if dup:
        raise SystemExit(f"duplicate probes {dup[:5]}: the report is impossible")
    known, out = set(qids), {}
    for r in rows:
        if r["rule"] not in calib_vendor.RULES or r["qid"] not in known:
            raise SystemExit(f"row off the run: rule {r['rule']!r}, probe {r['qid']!r}")
        point = out.setdefault((r["rule"], r["value"]), {})
        if r["qid"] in point:
            raise SystemExit(f"duplicate rows for {r['rule']} {r['value']} {r['qid']}: the report is impossible")
        point[r["qid"]] = r["keys"]
    for (rule, value), point in out.items():
        if len(point) != len(qids):
            raise SystemExit(f"unpaired: {rule} {value} has {len(point)} of {len(qids)} probes")
    if ("zbar", manifest["recall_margin"]) not in out:
        raise SystemExit("the default point (zbar at RECALL_MARGIN) is missing: nothing to judge against")
    return out


def _measure(v, probes: list[dict], keys: dict) -> dict:
    """hit@5, confusion and noise of one point, and which probes carry them."""
    lab = [p for p in probes if p["kind"] == "real" and p["targets"]]
    hit = {p["qid"]: bool(set(p["targets"]) & set(keys[p["qid"]][:5])) for p in lab}
    by_cat: dict[str, list[int]] = {}
    for p in lab:
        cat = by_cat.setdefault(p["category"], [0, 0])
        cat[0] += hit[p["qid"]]
        cat[1] += 1
    return {
        "hit": hit,
        # the closest fact admitted on meaning is not a target: a wrong answer instead of, or above, the right one
        "confused": {p["qid"] for p in lab if keys[p["qid"]] and keys[p["qid"]][0] not in p["targets"]},
        # every non-target admitted on a labelled probe (keep > 1: also those below a right one); shown, not gated
        "extra": sum(len(set(keys[p["qid"]][:5]) - set(p["targets"])) for p in lab),
        # upstream's noise: chit-chat with output, or a real question no fact answers (holdout) with output
        "noise": {p["qid"] for p in probes
                  if v.mcnemar_gate._noise({"out_n": len(keys[p["qid"]]), "kind": p["kind"], "targets": p["targets"]})},
        "by_category": {cat: f"{h}/{n}" for cat, (h, n) in sorted(by_cat.items())},
    }


def judge(v, probes: list[dict], base: dict, point: dict) -> dict:
    """*point* ({qid: keys}) against *base*, the default, on the conditions of PR #17."""
    mb, mp = _measure(v, probes, base), _measure(v, probes, point)
    n = len(mb["hit"])
    b = sum(1 for q in mb["hit"] if not mb["hit"][q] and mp["hit"][q])  # rescued by the point
    c = sum(1 for q in mb["hit"] if mb["hit"][q] and not mp["hit"][q])  # lost by the point
    p_value = v.mcnemar_gate.mcnemar(b, c)
    lost, gained = [], []
    for p in probes:
        if p["kind"] == "real" and p["targets"]:
            top_b, top_p = set(base[p["qid"]][:5]), set(point[p["qid"]][:5])
            lost += [f"{p['qid']}:{t}" for t in sorted(set(p["targets"]) & (top_b - top_p))]
            gained += [f"{p['qid']}:{t}" for t in sorted(set(p["targets"]) & (top_p - top_b))]
    hits = sum(mp["hit"].values())
    noise = {"base": len(mb["noise"]), "point": len(mp["noise"]),
             "added": sorted(mp["noise"] - mb["noise"]), "removed": sorted(mb["noise"] - mp["noise"])}
    confusion = {"base": len(mb["confused"]), "point": len(mp["confused"]),
                 "added": sorted(mp["confused"] - mb["confused"]), "removed": sorted(mb["confused"] - mp["confused"])}
    for d in (noise, confusion):
        d["net"] = len(d["added"]) - len(d["removed"])
    conditions = {"no_target_lost": not lost, "noise_not_higher": noise["point"] <= noise["base"],
                  "confusion_not_higher": confusion["point"] <= confusion["base"], "mcnemar_p_below_0.05": p_value < 0.05}
    return {"labelled": n, "hit5": hits, "recall5": round(hits / n, 4) if n else None,
            "points_vs_default": round(100.0 * (hits - sum(mb["hit"].values())) / n, 1) if n else 0.0,
            "b_rescued": b, "c_lost": c, "p": round(p_value, 6), "noise": noise, "confusion": confusion,
            "extra_admitted": {"base": mb["extra"], "point": mp["extra"]},
            "lost_targets": lost, "gained_targets": gained, "by_category": mp["by_category"],
            "conditions": conditions, "passes": all(conditions.values())}


def summary(v, manifest: dict, probes: list[dict], rows: list[dict]) -> dict:
    pts = points(manifest, probes, rows)
    base = pts[("zbar", manifest["recall_margin"])]
    rules: dict[str, list] = {}
    for (rule, value), point in pts.items():  # rows come in grid order, so do the points
        rules.setdefault(rule, []).append({"value": value, **judge(v, probes, base, point)})
    kinds = collections.Counter(p["category"] for p in probes)
    return {"run": manifest, "probes_by_category": dict(sorted(kinds.items())),
            "default": {"rule": "zbar", "value": manifest["recall_margin"]}, "rules": rules,
            "passing": {rule: [pt["value"] for pt in pts_ if pt["passes"]] for rule, pts_ in rules.items()}}


def markdown(s: dict, digest: str) -> str:
    run = s["run"]
    lines = [f"# Threshold calibration: {run['emb']}, {run['probe_source']} probes, keep {run['keep']}", "",
             "run: " + ", ".join(f"{k}={run[k]}" for k in sorted(run) if not k.startswith("grid_")), "",
             f"summary.json sha256: `{digest}`", "",
             "probes: " + ", ".join(f"{k} {n}" for k, n in s["probes_by_category"].items()), "",
             f"- {CAVEAT_EXPLORATORY}"]
    if run["probe_source"] == "auto":
        lines.append(f"- {CAVEAT_AUTO}")
    lines += ["- measured: the meaning channel alone (facts admitted on meaning, at most `keep` per probe); words, "
              "entities and names_fit are outside it.",
              "- confusion: a labelled probe whose closest admitted fact is not a target (gated); extra: every "
              "non-target fact admitted on labelled probes (shown, not gated).", ""]
    for rule, pts in s["rules"].items():
        lines += [f"## {rule}: {calib_vendor.RULES[rule]}", ""]
        if rule == "floor":
            lines += [f"> {CAVEAT_FLOOR}", ""]
        lines += ["| value | recall@5 | pts | noise (net) | confusion (net) | extra | b | c | p | lost | gate | "
                  "by category |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for pt in pts:
            default = rule == "zbar" and pt["value"] == s["default"]["value"]
            failed = ",".join(k for k, ok in pt["conditions"].items() if not ok)
            gate = "default" if default else "PASS" if pt["passes"] else f"fail: {failed}"
            lines.append(f"| {pt['value']} | {pt['hit5']}/{pt['labelled']} | {pt['points_vs_default']:+.1f} | "
                         f"{pt['noise']['point']} ({pt['noise']['net']:+d}) | "
                         f"{pt['confusion']['point']} ({pt['confusion']['net']:+d}) | "
                         f"{pt['extra_admitted']['point']} | {pt['b_rescued']} | "
                         f"{pt['c_lost']} | {pt['p']:.4f} | {len(pt['lost_targets'])} | {gate} | "
                         f"{', '.join(f'{k} {x}' for k, x in pt['by_category'].items())} |")
        lines.append("")
    lines += ["## Points that pass the gate (exploratory)", ""]
    lines += [f"- {rule}: {', '.join(map(str, vals)) or 'none'}" for rule, vals in s["passing"].items()]
    return "\n".join(lines) + "\n"


def write(run_dir: Path, v) -> tuple[dict, str]:
    """summary.json and report.md of *run_dir*; returns the summary and the sha256 of summary.json."""
    run_dir = Path(run_dir)
    s = summary(v, *load(run_dir))
    data = (json.dumps(s, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    (run_dir / "summary.json").write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (run_dir / "report.md").write_text(markdown(s, digest), encoding="utf-8", newline="\n")
    return s, digest


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description="working-point curve and PR #17 gate over a calibration run")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--plugin-src", default=calib_vendor.DEFAULT_SRC, help="the plugin snapshot (read only)")
    args = ap.parse_args(argv)
    s, digest = write(args.run_dir, calib_vendor.load(args.plugin_src))
    sys.stdout.write((args.run_dir / "report.md").read_text(encoding="utf-8"))
    return s


if __name__ == "__main__":
    main()
