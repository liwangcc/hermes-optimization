"""Export the decision and aggregate counts. No model calls, raw queries or vectors."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from calib_novel_decision import HERE, RULE, read, save, verify_lock


def total(counts):
    result = Counter()
    for group in counts:
        result.update(group)
    return result


def verdict(independent, frozen, h1):
    tied = all(frozen[k] == h1[k] for k in ("rescued", "added_wrong"))
    if independent["rescued"] <= 1 or tied:
        return "不值得要"
    better = frozen["added_wrong"] < h1["added_wrong"] or frozen["rescued"] > h1["rescued"]
    if (independent["rescued"] >= 6 and independent["lost_targets"] == 0
            and independent["added_wrong"] == 0 and better):
        return "值得要"
    return "未达到采用条件"


def export(work):
    verify_lock()
    published = read(HERE / "consensus-results.json")
    frozen, limits, controls, independent, ablation, slim = [
        read(work / (name + ".json"))
        for name in ("freeze", "ceiling", "controls", "independent", "ablate", "simplified")
    ]
    if not all(data.keys() == published["runs"].keys() for data in (frozen, limits, controls, slim)):
        raise ValueError("different pool across stages")
    runs, suites = {}, defaultdict(list)
    names = ("baseline", RULE, "H1", "H3")
    for label, source in published["runs"].items():
        group = source["suite"].split("_")[0]
        points = {**controls[label], **frozen[label]}
        arms = {a: total(points[a].values()) for a in names}
        miss = limits[label]["missed"]
        if miss != arms[RULE]["labelled"] - arms[RULE]["base_hit"] or not (
            arms[RULE]["rescued"] <= limits[label]["overlap"] <= miss
        ):
            raise ValueError("inconsistent miss ceiling")
        runs[label] = dict(ceiling=limits[label], arms=arms)
        suites[group].append(label)

    def combine(keys):
        keys = list(keys)
        return dict(ceiling=total(limits[k] for k in keys),
                    arms={a: total(runs[k]["arms"][a] for k in keys) for a in names})

    pool = combine(runs)
    for k, v in published["totals"][RULE].items():
        if pool["arms"][RULE][k] != v:
            raise ValueError("report totals differ")
    if pool["arms"][RULE] != ablation["full"]:
        raise ValueError("inconsistent frozen arm in ablations")
    blind = total(point["counts"] for point in independent.values())
    plan = read(HERE / "novel-independent-plan.json")
    seal = read(HERE / "novel-independent-seal.json")
    if (work / "independent-started").read_text(encoding="ascii").strip() != seal["fixture_sha256"]:
        raise ValueError("independent run and fixture seal differ")
    expected = total(plan["strata"].values())
    if (blind["labelled"], blind["negatives"]) != (expected["positive"], expected["negative"]):
        raise ValueError("independent set size differs from registration")
    return dict(
        verdict=verdict(blind, pool["arms"][RULE], pool["arms"]["H1"]),
        original_pool=dict(reproduced_runs=len(runs), **pool, by_suite={k: combine(v) for k, v in suites.items()},
                           by_run=runs),
        independent=dict(paired_passes=1, counts=blind, ceiling=total(i["ceiling"] for i in independent.values()),
                         by_suite=independent),
        ablations=ablation,
        simplified_verification=dict(rows=pool["arms"][RULE]["rows"],
                                     unchanged_from_frozen=sum(r["same_as_frozen"] for r in slim.values()),
                                     independent_rows=0),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=HERE / "novel-decision-counts.json")
    args = parser.parse_args()
    save(args.out, export(args.work))
