"""Replay admission rules over a score dump (calib_dump.py), on top of what the words already showed.

    python calib_replay.py --dump D.json --lexical rows_ZC.jsonl \
        --check content/zbar=rows_ZC.jsonl content/floor=rows_FC.jsonl [--out summary.json]

--lexical is the rows of one KG-1 cell (qid, keys, by_meaning, targets): keys without by_meaning is what the words
and the entity stream showed. An arm adds at most KEEP facts on meaning after the first five of them, where prefetch
puts them (fresh + meaning + entity). names_fit and the repeat window are not replayed: --check says how many rows
of a measured cell the replay reproduces.

Every cell is judged against content/zbar, upstream's default, on the four conditions of PR #17. Confusion is
upstream's for a set without curated confusers (synthetic_zh's wrong5): a labelled row with a non-target in its top
five. The arms and their numbers are fixed here and nothing picks one: the first six before any dump was read, H5 and
H6 after the synthetic dump and before a real store's results on them. What is printed is counts only, so a real
store's summary may leave the machine; its dump may not.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import calib_vendor

KEEP = 1  # the plugin's default embedding_prefetch_facts
# The two cells carried forward after both stores were read (2026-11-21); the table marks them.
NAMED = {("content+keywords", "H1"): "pure gain",  # nothing gets worse on either store; +1 hit each
         ("content+keywords", "H3"): "trade-off"}  # the most hits with no target lost; three non-targets added
BEAT = 0.06  # upstream's SEARCH_BEAT_WORDS: how much closer than the words' best fact (fact_store search, beyond_words)
# arm -> (scale, its value when nothing was shown, its value when something was, only the closest fact is considered
#         [, beat: with something shown, the fact must be this much closer than the closest shown one
#          , agree: with nothing shown, this vector text must have the same closest fact])
ARMS = {
    "zbar": ("z", 1.0, 1.0, False),         # upstream's default: the baseline
    "floor": ("floor", 0.55, 0.55, False),  # the local rule as KG-1 measured it (FC, FK)
    "H1": ("z", 0.7, 0.5, False),           # strict when the words found nothing, looser when they found something
    "H3": ("floor", 0.55, 0.55, True),      # the closest fact or none: no walking down past a fact already shown
    "H4": ("robust", 1.0, 1.0, False),      # the default margin on a median/MAD scale
    "H1+H4": ("robust", 0.7, 0.5, False),
    "H5": ("floor", 0.55, 0.55, True, BEAT, None),       # H3, and clearly closer than what the words found
    "H6": ("floor", 0.55, 0.55, True, None, "content"),  # H3, and the content-only vectors agree when words are silent
    "H5+H6": ("floor", 0.55, 0.55, True, BEAT, "content"),
}


def admit(v, ids, cos, shown, scale, value, top1, eligible, recallable) -> list[int]:
    """The facts one rule adds on meaning: Retriever.by_meaning over what is not shown yet, then prefetch's cut."""
    meaning = {"z": v.emb.Meaning, "floor": v.FloorMeaning, "robust": v.RobustMeaning}[scale](ids, cos, 0.0)
    if scale == "floor":
        meaning.floor = value
    ranked = meaning.ranked()
    return calib_vendor.walk(meaning, ranked[:1] if top1 else ranked, value, None, KEEP, eligible - set(shown),
                             recallable)


def with_meaning(shown: list[int], added: list[int]) -> list[int]:
    return shown[:5] + added + shown[5:]


def cell(v, dump, lexical, variant, scale, silent, found, top1, beat=None, agree=None) -> dict:
    """{qid: keys} of one rule on one vector text."""
    ids, eligible, recallable = dump["fact_ids"], set(dump["eligible"]), set(dump["recallable"])
    out = {}
    for p in dump["probes"]:
        shown = lexical[p["qid"]]
        added = [] if p["meaning_call"] != "ok" else admit(
            v, ids, p["cos"][variant], shown, scale, found if shown else silent, top1, eligible, recallable)
        if added and shown and beat is not None:
            cos = dict(zip(ids, p["cos"][variant]))
            if cos[added[0]] - max((cos[k] for k in shown if k in cos), default=-1.0) < beat:
                added = []
        if added and not shown and agree:
            other = p["cos"][agree]
            if ids[other.index(max(other))] != added[0]:
                added = []
        out[p["qid"]] = with_meaning(shown, added)
    return out


def judge(v, probes, lexical, base, point) -> dict:
    lab = [p for p in probes if p["kind"] == "real" and p["targets"]]

    def hit(keys, p):
        return bool(set(p["targets"]) & set(keys[p["qid"]][:5]))

    def confused(keys):
        return {p["qid"] for p in lab if set(keys[p["qid"]][:5]) - set(p["targets"])}

    def noise(keys):
        return {p["qid"] for p in probes if v.mcnemar_gate._noise(
            {"out_n": len(keys[p["qid"]]), "kind": p["kind"], "targets": p["targets"]})}

    b = sum(1 for p in lab if not hit(base, p) and hit(point, p))
    c = sum(1 for p in lab if hit(base, p) and not hit(point, p))
    lost = sum(len(set(p["targets"]) & (set(base[p["qid"]][:5]) - set(point[p["qid"]][:5]))) for p in lab)
    new = [(k in p["targets"]) for p in probes for k in point[p["qid"]] if k not in lexical[p["qid"]]]
    p_value = v.mcnemar_gate.mcnemar(b, c)
    conditions = {"no_target_lost": lost == 0, "noise_not_higher": len(noise(point)) <= len(noise(base)),
                  "confusion_not_higher": len(confused(point)) <= len(confused(base)),
                  "mcnemar_p_below_0.05": p_value < 0.05}
    return {"labelled": len(lab), "hit5": sum(hit(point, p) for p in lab), "b_rescued": b, "c_lost": c,
            "p": round(p_value, 4), "noise": [len(noise(base)), len(noise(point))],
            "confusion": [len(confused(base)), len(confused(point))],
            "added_target": sum(new), "added_other": len(new) - sum(new),
            "conditions": conditions, "passes": all(conditions.values())}


def separation(dump, variant) -> dict:
    """The meaning channel alone, no threshold: how often the closest fact is a target, and how well its cosine tells
    a right closest fact from a wrong one or from a question nothing answers (1.0 = one threshold splits them)."""
    right, wrong = [], []
    for p in dump["probes"]:
        if p["meaning_call"] == "ok":
            cos = p["cos"][variant]
            top = max(cos)
            (right if dump["fact_ids"][cos.index(top)] in p["targets"] else wrong).append(top)
    pairs = len(right) * len(wrong)
    auc = sum((r > w) + 0.5 * (r == w) for r in right for w in wrong) / pairs if pairs else None
    return {"closest_is_target": len(right), "closest_is_not": len(wrong), "auc": None if auc is None else round(auc, 3)}


def oracle(v, dump, lexical, base, variant) -> dict:
    """The most targets a closest-fact floor on this vector text could rescue at no cost to the other conditions.
    The threshold is chosen on these very rows: an upper bound for comparing vector texts, not a result."""
    best = {"b_rescued": 0, "floor": None}
    for t in sorted({max(p["cos"][variant]) for p in dump["probes"] if p["meaning_call"] == "ok"}, reverse=True):
        j = judge(v, dump["probes"], lexical, base, cell(v, dump, lexical, variant, "floor", t, t, True))
        free = all(ok for name, ok in j["conditions"].items() if name != "mcnemar_p_below_0.05")
        if free and j["b_rescued"] > best["b_rescued"]:  # strictest first: of equal rescues, the strictest floor
            best = {"b_rescued": j["b_rescued"], "floor": round(t, 4), "added_target": j["added_target"],
                    "added_other": j["added_other"]}
    return best


def _rows(path) -> dict:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return {r["qid"]: r for r in rows}


def run(args) -> dict:
    v = calib_vendor.load(args.plugin_src)
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    rows = _rows(args.lexical)
    for p in dump["probes"]:
        r = rows.get(p["qid"])
        if r is None or sorted(r.get("targets") or []) != sorted(p["targets"]):
            raise SystemExit(f"probe {p['qid']}: no lexical row with the same targets — another store or query set")
    lexical = {q: [k for k in r["keys"] if k not in (r.get("by_meaning") or [])] for q, r in rows.items()}
    base = cell(v, dump, lexical, "content", *ARMS["zbar"])

    summary = {"run": dump["manifest"], "lexical": Path(args.lexical).name, "keep": KEEP, "arms": ARMS,
               "baseline": "content/zbar", "checks": {}, "variants": {}}
    for spec in args.check or []:
        name, _, path = spec.partition("=")
        variant, _, arm = name.rpartition("/")
        got, want = cell(v, dump, lexical, variant, *ARMS[arm]), _rows(path)
        differ = sorted(q for q in got if got[q] != want[q]["keys"])
        summary["checks"][name] = {"reproduced": len(got) - len(differ), "of": len(got), "differ": differ[:10]}
    for variant in dump["manifest"]["variants"]:
        summary["variants"][variant] = {
            "separation": separation(dump, variant),
            "oracle_floor": oracle(v, dump, lexical, base, variant),
            "arms": {arm: judge(v, dump["probes"], lexical, base, cell(v, dump, lexical, variant, *spec))
                     for arm, spec in ARMS.items()}}
    print(markdown(summary))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return summary


def markdown(s: dict) -> str:
    run_ = s["run"]
    lines = [f"# Replay: {run_['emb']} ({run_['endpoint']}), {run_['fact_n']} facts "
             f"({run_['keywords_fact_n']} with keywords), {run_['probes_n']} probes, keep {s['keep']}", "",
             f"baseline {s['baseline']}; lexical rows {s['lexical']}", ""]
    lines += [f"- check {name}: reproduced {c['reproduced']} of {c['of']}" + (f", differ {c['differ']}" if c["differ"] else "")
              for name, c in s["checks"].items()]
    for variant, data in s["variants"].items():
        sep, orc = data["separation"], data["oracle_floor"]
        lines += ["", f"## {variant}", "",
                  f"closest fact is a target on {sep['closest_is_target']} probes, is not on {sep['closest_is_not']}; "
                  f"AUC {sep['auc']}; oracle floor (upper bound): {orc['b_rescued']} rescued at {orc['floor']}"
                  + (f", added {orc['added_target']} target / {orc['added_other']} other" if orc["floor"] is not None else ""),
                  "", "| arm | hit@5 | b | c | p | noise | confusion | added target / other | gate |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for arm, j in data["arms"].items():
            failed = ",".join(k for k, ok in j["conditions"].items() if not ok)
            gate = "baseline" if (variant, arm) == ("content", "zbar") else "PASS" if j["passes"] else f"fail: {failed}"
            name = f"{arm} ({NAMED[variant, arm]})" if (variant, arm) in NAMED else arm
            lines.append(f"| {name} | {j['hit5']}/{j['labelled']} | {j['b_rescued']} | {j['c_lost']} | {j['p']:.4f} | "
                         f"{j['noise'][0]} -> {j['noise'][1]} | {j['confusion'][0]} -> {j['confusion'][1]} | "
                         f"{j['added_target']} / {j['added_other']} | {gate} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description="replay admission rules over a score dump")
    ap.add_argument("--dump", required=True, help="calib_dump.py's file")
    ap.add_argument("--lexical", required=True, help="KG-1 rows of one cell: what the words showed (keys - by_meaning)")
    ap.add_argument("--check", nargs="*", help="VARIANT/ARM=ROWS.jsonl: a measured cell the replay must reproduce")
    ap.add_argument("--out", help="write the summary (counts only) as JSON")
    ap.add_argument("--plugin-src", default=calib_vendor.DEFAULT_SRC, help="the plugin snapshot (read only)")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
