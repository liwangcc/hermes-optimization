"""The opaque export: no text leaves, a stamp carrying prose refuses the whole export, the gate runs on what does."""
import json

import pytest

import calib_gate
import calib_opaque
import calib_run
from conftest import EVAL

CANARY = "CANARY 这是一段不该离开本机的原文"


@pytest.fixture
def run(v, tmp_path):
    """A stub run on the synthetic set whose probes then carry the canary in their text and in an extra field."""
    out = tmp_path / "run"
    calib_run.main(["--stub", "--facts", str(EVAL / "facts.json"), "--queries", str(EVAL / "queries.json"),
                    "--out", str(out)])
    probes = [json.loads(x) for x in (out / "probes.jsonl").read_text(encoding="utf-8").splitlines()]
    with open(out / "probes.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for p in probes:
            fh.write(json.dumps({**p, "q": CANARY + p["q"], "note": CANARY, "texts": [CANARY]}, ensure_ascii=False)
                     + "\n")
    return out


def test_the_probe_text_and_any_other_text_field_are_stripped(run, tmp_path):
    calib_opaque.main([str(run), str(tmp_path / "out")])
    exported = {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "out").iterdir()}
    assert sorted(exported) == sorted(calib_opaque.FILES)
    raw = "".join(exported.values())
    assert "CANARY" not in raw and raw.isascii()
    probes = [json.loads(x) for x in exported["probes.jsonl"].splitlines()]
    assert len(probes) == 42 and not {"q", "note", "texts"} & set().union(*probes)
    assert all(isinstance(t, int) for p in probes for t in p["targets"])  # ids stay, as integers


def _numbers(summary):
    """A summary without the probe ids (the export renames them): every count, p and verdict."""
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(y) for k, y in x.items()}
        if isinstance(x, list):
            return len(x) if any(isinstance(y, str) for y in x) else [strip(y) for y in x]
        return x
    return strip(summary)


def test_the_gate_gives_the_same_numbers_on_the_export(v, run, tmp_path):
    calib_opaque.export(run, tmp_path / "out")
    exported, local = calib_gate.summary(v, *calib_gate.load(tmp_path / "out")), calib_gate.summary(v, *calib_gate.load(run))
    assert _numbers(exported) == _numbers(local)
    assert exported["rules"]["zbar"][0]["noise"]["added"][0].startswith("q0")  # ids renamed, counts unchanged


def _edit_probe(run, field, value):
    lines = (run / "probes.jsonl").read_text(encoding="utf-8").splitlines()
    bad = json.loads(lines[3])
    bad[field] = value
    lines[3] = json.dumps(bad, ensure_ascii=False)
    (run / "probes.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_probe_ids_and_unknown_categories_are_renamed(run, tmp_path):
    _edit_probe(run, "category", "lena-oncology-appointment")
    calib_opaque.export(run, tmp_path / "out")
    probes = [json.loads(x) for x in (tmp_path / "out" / "probes.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = [json.loads(x) for x in (tmp_path / "out" / "rows.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [p["qid"] for p in probes] == [f"q{k:04d}" for k in range(1, 43)]
    assert {r["qid"] for r in rows} == {p["qid"] for p in probes}
    assert probes[3]["category"] == "cat1" and {p["category"] for p in probes} - {"cat1"} <= calib_opaque.CATEGORIES


@pytest.mark.parametrize("file, field", [("probes.jsonl", "lang"), ("manifest.json", "emb")])
def test_text_inside_a_stamp_field_refuses_the_whole_export(run, tmp_path, file, field):
    if file == "probes.jsonl":
        _edit_probe(run, field, CANARY)
    else:
        manifest = json.loads((run / file).read_text(encoding="utf-8"))
        (run / file).write_text(json.dumps({**manifest, field: CANARY}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit) as refused:
        calib_opaque.export(run, tmp_path / "out")
    assert field in str(refused.value) and "CANARY" not in str(refused.value)  # named, never quoted
    assert not (tmp_path / "out").exists()  # nothing was written, not even the clean files


def test_the_leak_scan_rejects_what_opaque_would_never_emit():
    for leak in ({"note": "plain"}, {"keys": [1, "two"]}, {"nested": {"a": 1}}, {"category": "two words"},
                 {"keys": [True]}):
        with pytest.raises(SystemExit):
            calib_opaque.leak_scan([leak])
    calib_opaque.leak_scan([{"category": "no_answer", "keys": [1, 2], "holdout": None, "value": 0.55,
                             "grid_floor": [0.5, 0.6], "est_usd": None}])
