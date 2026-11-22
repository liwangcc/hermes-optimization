"""Counts and the PLAN-FREEZE verdict of the frozen rules against daily 0.6.0 for one dump directory.

    python -X utf8 -B report.py dump/test [--json out.json]
"""
import argparse
import json
from collections import Counter

import daily_eval as d
import frozen_rules as fr

KEYS = ("labelled", "hit", "rescued", "lost_targets", "negatives", "noise", "confusion", "shown_other",
        "added_wrong", "removed_other")


def family(name):
    return name.split("-")[0].split("_")[0] if not name.startswith("two_topics") else "two_topics"


def families(result):
    out = {}
    for name, counts in result.items():
        if name != "ALL":
            out.setdefault(family(name), Counter()).update(counts)
    return out


def verdict(rule_all, daily_all, rule_fam, daily_fam):
    pure = (rule_all["lost_targets"] == 0 and rule_all["hit"] >= daily_all["hit"]
            and rule_all["shown_other"] < daily_all["shown_other"] and rule_all["noise"] <= daily_all["noise"]
            and rule_all["confusion"] <= daily_all["confusion"]
            and all(rule_fam[f]["hit"] >= daily_fam[f]["hit"] for f in rule_fam))
    return "PURE GAIN" if pure else "TRADE"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dump")
    ap.add_argument("--json")
    args = ap.parse_args()
    fxs = d.load(args.dump)
    base = d.evaluate(fxs, d.daily)
    print("daily 0.6.0:", {k: base["ALL"][k] for k in ("labelled", "hit", "negatives", "noise", "confusion",
                                                        "shown_other")})
    out = {"daily": base, "rules": {}}
    for name, rule in fr.RULES.items():
        res = d.evaluate(fxs, rule)
        fam = families(res)
        v = verdict(res["ALL"], base["ALL"], fam, families(base))
        print(f"{name} ({'primary' if name in fr.PRIMARY else 'secondary'}): {v}")
        print("  ALL".ljust(14), "  ".join(f"{k}={res['ALL'][k]}" for k in KEYS))
        for f, c in fam.items():
            print(f"  {f}".ljust(14), "  ".join(f"{k}={c[k]}" for k in KEYS))
        out["rules"][name] = {"verdict": v, "ALL": res["ALL"], "families": {f: dict(c) for f, c in fam.items()},
                              "fixtures": {n: c for n, c in res.items() if n != "ALL"}}
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
