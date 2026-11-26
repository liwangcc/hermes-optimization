"""Compare two directories of provenance rows question by question: hit@5, how many facts were shown, and which
facts came by meaning — the fields the gate reads. Fact keys are compared by position only, because upstream 0.31.3
and 0.31.4 renamed the people of the languages corpus and its keys (anton_bike -> leon_bike), so the old rows and the
new ones name the same facts differently.

    python -I compare_rows.py <old rows dir> <new rows dir> <old suffix> <new suffix>

e.g. old `provenance_multi_on.jsonl` against new `provenance_multi_coff_on.jsonl`: suffixes `on` and `coff_on`.
"""
import json
import sys
from pathlib import Path

old_dir, new_dir, old_sfx, new_sfx = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
SETS = ["multi", "contrast_en", "contrast_ru", "contrast_zh", "household_test", "household_dev", "synthetic_zh"]


def rows(path):
    return {(r["set"], r["lang"], r["qid"]): r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def meaning(r):
    return sorted(i for i, tags in enumerate((r.get("sources") or {}).values()) if "meaning" in tags)


total = 0
for name in SETS:
    old_p, new_p = old_dir / f"provenance_{name}_{old_sfx}.jsonl", new_dir / f"provenance_{name}_{new_sfx}.jsonl"
    if not (old_p.exists() and new_p.exists()):
        print(f"{name}: missing {old_p.name if not old_p.exists() else new_p.name}")
        continue
    old, new = rows(old_p), rows(new_p)
    diffs = []
    for key in sorted(set(old) | set(new), key=str):
        a, b = old.get(key), new.get(key)
        if a is None or b is None:
            diffs.append(f"  {key}: only in {'new' if a is None else 'old'}")
            continue
        for field in ("kind", "hit5", "out_n", "wrong", "wrong5", "confused"):
            if a.get(field) != b.get(field):
                diffs.append(f"  {key} {field}: {a.get(field)!r} -> {b.get(field)!r}  (q old {a['q'][:60]!r} new {b['q'][:60]!r})")
        if meaning(a) != meaning(b):
            diffs.append(f"  {key} by-meaning positions: {meaning(a)} -> {meaning(b)}")
    total += len(diffs)
    print(f"{name}: {len(new)} rows, {len(diffs)} differences")
    print("\n".join(diffs[:40]))
print(f"total differences: {total}")
