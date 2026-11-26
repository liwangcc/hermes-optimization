"""What the rows of both arms say about the check and its cost: stamps, calls, outcomes and times, every turn counted
(also those that showed nothing). python -I row_stats.py <rows dir>"""
import collections
import json
import sys
from pathlib import Path

for arm in ("coff", "c0.5"):
    rows = [json.loads(line) for p in sorted(Path(sys.argv[1]).glob(f"provenance_*_{arm}_on.jsonl"))
            for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    stamps = collections.Counter((r["git_sha"], r["margin"], r["check_margin"], r["check_model"],
                                  r["check_instruction_sha256"], r["endpoint"], r["scale"], r["emb_model"])
                                 for r in rows)
    calls = [r for r in rows if r["check_calls"]]
    silent = [r for r in calls if not r["out_n"]]
    outcomes = collections.Counter(r["check_outcome"] for r in rows if r["check_outcome"])
    check_ms = sorted(r["check_ms"] for r in calls)
    turn_ms = sorted(r["ms"] for r in rows if r.get("ms") is not None)
    print(f"== arm {arm}: {len(rows)} turns in {len({r['set'] + r.get('split', '') for r in rows})} set/split files")
    for stamp, n in stamps.items():
        print(f"   {n} rows stamped git_sha, margin, check_margin, check_model, instruction sha256, endpoint, scale, "
              f"emb_model = {stamp}")
    print(f"   check calls {len(calls)} ({len(silent)} of them on turns that showed nothing), outcomes "
          f"{dict(sorted(outcomes.items()))}, rows missing the check fields: "
          f"{sum(1 for r in rows if 'check_calls' not in r)}")
    if check_ms:
        print(f"   check ms: median {check_ms[len(check_ms) // 2]}, max {check_ms[-1]}")
    print(f"   prefetch ms of timed turns: {len(turn_ms)} timed, median {turn_ms[len(turn_ms) // 2]}, max {turn_ms[-1]}")
