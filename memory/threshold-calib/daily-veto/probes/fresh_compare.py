"""daily_eval.row_counts of new blocks against daily blocks (fresh session per question). argv: scratchpad daily.json new.json"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import daily_eval as d  # noqa: E402

old, new = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:4])
KEYS = ("hit", "base_hit", "rescued", "lost_targets", "noise", "base_noise", "confusion", "shown_other",
        "base_shown_other", "added_wrong")
for split in ("dev", "test"):
    tot, lost = Counter(), []
    for name in (n for n in old if n.startswith(split)):
        fx = d.Fixture(Path(sys.argv[1]) / "dump" / name)
        for t, q in enumerate(fx.q):
            c = d.row_counts(q, old[name][t], new[name][t])
            tot.update({k: c[k] for k in KEYS})
            if c["lost_targets"]:
                lost.append((name, q["qid"], old[name][t], new[name][t], q["targets"]))
    print(split, "(base_* = daily)", dict(tot))
    for row in lost[:8]:
        print("   lost:", row)
