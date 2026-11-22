"""Replay of "a lower margin only before a turn that already shows a fact" over the plugin's committed margin rows.

    python replay_margin_shown.py <plugin clone> [silent margin] [shown margin]      # default 0.7 0.5

No model and no endpoint: the rows are results/provenance_<set>_m<margin>_on.jsonl of the plugin repository. Per
(set, lang, qid) the proposal takes the row of the shown margin when the margin-1.0 row shows a fact whose sources
are not meaning alone (the words found it, or an entity the message names has it), else the row of the silent
margin. Hits, noise, confusion and p come from the repository's own tools/mcnemar_gate.py.

This is not the gate: the committed rows are from two commits, so `mcnemar_gate.py --pair margin` refuses to pair
them. The check printed first (the 0.95 rows against the 1.0 rows) is why the replay is still worth reading.
"""
import json
import sys
from pathlib import Path

SETS = ("contrast_en", "contrast_ru", "contrast_zh", "household_test", "multi")


def main(repo: str, silent: str = "0.7", shown: str = "0.5") -> None:
    root = Path(repo)
    sys.path.insert(0, str(root / "tools"))
    import mcnemar_gate as gate

    def load(margin: str) -> dict:
        out = {}
        for name in SETS:
            for line in (root / "results" / f"provenance_{name}_m{margin}_on.jsonl").read_text("utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    out[(r["set"], r["lang"], r["qid"])] = r
        return out

    base, at_silent, at_shown, near = load("1"), load(silent), load(shown), load("0.95")
    print(f"rows {len(base)}; identical at margin 0.95 and 1.0: {sum(base[k]['keys'] == near[k]['keys'] for k in base)}; "
          f"commits {sorted({r['git_sha'][:7] for rows in (base, at_silent, at_shown) for r in rows.values()})}")

    def shows_a_fact(r: dict) -> bool:
        return any(set(sources) - {"meaning"} for sources in r.get("sources", {}).values())

    arms = {f"{shown} before every turn": at_shown,
            f"{silent} silent / {shown} shown": {k: (at_shown if shows_a_fact(base[k]) else at_silent)[k] for k in base}}
    real = [k for k, r in base.items() if r["kind"] == "real"]
    for name, arm in arms.items():
        b = [k for k in real if not base[k]["hit5"] and arm[k]["hit5"]]
        c = [k for k in real if base[k]["hit5"] and not arm[k]["hit5"]]
        noise = [sum(gate._noise(r) for r in rows.values()) for rows in (base, arm)]
        confusion = [sum(gate._confused(rows[k]) for k in real) for rows in (base, arm)]
        print(f"\n== 1.0 (default) vs {name} | rows {len(real)} real")
        print(f"hit5 {sum(bool(base[k]['hit5']) for k in real)} -> {sum(bool(arm[k]['hit5']) for k in real)}; "
              f"b={len(b)}, c={len(c)}, exact McNemar p={gate.mcnemar(len(b), len(c)):.4f}")
        print(f"noise {noise[0]} -> {noise[1]}; confusion {confusion[0]} -> {confusion[1]}")
        print("rescued: " + ("; ".join(f"{k[0]}/{k[1]} {k[2]}" for k in sorted(b, key=str)) or "-"))
        flipped = sorted((k for k in base if not gate._noise(base[k]) and gate._noise(arm[k])), key=str)
        print("silent rows that got output: " + ("; ".join(f"{k[0]}/{k[1]} {k[2]}" for k in flipped) or "-"))


if __name__ == "__main__":
    main(*sys.argv[1:])
