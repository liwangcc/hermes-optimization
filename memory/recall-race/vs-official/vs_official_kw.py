"""The daily version against the official plugin's main arm with the same blind keywords in the facts.
Usage (from memory/recall-race):
    python -X utf8 -B vs-official/vs_official_kw.py vs-official/rows          # every shared row
    python -X utf8 -B vs-official/vs_official_kw.py vs-official/rows test     # the pool the daily rule was not fitted on
The first argument is official_kw_run.py's output. The daily side reads round 2's frozen scores (round2/, not in
the public repository); the official side needs only the rows here and pack/labels.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "round2")
import combine as C
import recall_rule as RR
from build_big import RENAMED
from judge_lib import R, counts, load_all

RUN = Path(sys.argv[1])
A = load_all()
C.add_streams(A)


def rows_of(folder, pattern):
    out, meta = {}, set()
    for p in sorted(Path(folder).glob(pattern)):
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            out[f"{r['set']}|{r['lang']}|{r['qid']}"] = [RENAMED.get(k, k) for k in r.get("keys") or []]
            meta.add((r["git_sha"][:12], r["emb"], r["margin"], r["check_margin"], r["kw_coverage"], r["embed_text"]))
    return out, meta


stored, m0 = rows_of("../threshold-calib/upstream-check/repro/rows", "*_coff_on.jsonl")
rerun, m1 = rows_of(RUN / "nokw", "*.jsonl")
kw, m2 = rows_of(RUN / "kw", "*.jsonl")
keys = [k for k in A.rows if not k.startswith("multi|") and k in kw]
if len(sys.argv) > 2:  # one pool only: the daily rule was fitted on dev and judged once on test
    keys = [k for k in keys if A.rows[k].pool == sys.argv[2]]
print("shared rows", len(keys))
print("stored official rows:", sorted(m0))
print("rerun, no keywords:  ", sorted(m1), "| same facts shown as stored:", sum(stored[k] == rerun[k] for k in keys), "of", len(keys))
print("rerun, keywords:     ", sorted(m2))


def block_plus_one(x, d0):
    return RR.decide([c for c in x.cands if c.base or (x.ask and c.cos_rank == 0)], d0, x.ask)[0]


subs = {
    "official main, no keywords": {k: stored[k] for k in keys},
    "official main, keywords": {k: kw[k] for k in keys},
    "daily, no judge (D0)": {k: A.d0[k] for k in keys},
    "daily, judge on CUDA": {k: RR.decide(A.rows[k].cands, A.d0[k], A.rows[k].ask)[0] for k in keys},
    "daily, judge off CUDA": {k: block_plus_one(A.rows[k], A.d0[k]) for k in keys},
}
ref = subs["official main, keywords"]
base = {k: A.base[k] for k in keys}
print(f"\n{'':28s} {'hit@5':>9s} {'found':>6s} {'shown':>6s} {'non-answers':>11s} {'precision':>9s} {'noise rows':>10s} "
      f"{'confused':>8s} | against official with keywords: {'rescued/lost':>12s} {'p':>7s} {'answers lost':>12s}")
for name, sub in subs.items():
    g, c, m = R.gate(sub, ref, keys), counts(sub, keys), R.metrics(sub, keys, base)
    print(f"{name:28s} {m['hit5']:5d}/{m['answerable']:3d} {c['found']:6d} {c['shown']:6d} {c['nontarget']:11d} "
          f"{c['precision']:9.2f} {g['noise'][1]:10d} {g['confused'][1]:8d} | {'':30s} "
          f"{str(g['b_rescued']) + ' / ' + str(g['c_lost']):>12s} {g['p']:7.4f} {len(g['lost_targets']):12d}")
by_set = {}
for k in keys:
    by_set.setdefault(k.split("|")[0], []).append(k)
print("\nhit@5 by set (answerable):", "  ".join(
    f"{s} {R.metrics(subs['official main, keywords'], ks, base)['hit5']}/{R.metrics(subs['daily, judge on CUDA'], ks, base)['hit5']}"
    f"/{R.metrics(ref, ks, base)['answerable']}" for s, ks in by_set.items()), " (official with keywords / daily with judge / questions)")
