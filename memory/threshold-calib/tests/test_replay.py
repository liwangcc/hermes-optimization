"""The replayed arms (calib_replay.py) on hand-made scores, and the dump (calib_dump.py) on the stub embedder."""
import json
import sqlite3
import subprocess
import sys

import pytest

import calib_dump
import calib_replay
from conftest import EVAL, HERE, child_env

IDS = list(range(1, 31))  # 30 facts: enough vectors for the plugin's z (MIN_VECTORS_FOR_Z)
ALL = set(IDS)


def scores(top: dict, bulk=(0.0, 0.0)) -> list[float]:
    """A cosine per fact: *top* for the named facts, the two *bulk* values in turn for the rest."""
    return [top.get(i, bulk[i % 2]) for i in IDS]


def add(v, cos, shown, arm):
    scale, silent, found, top1 = calib_replay.ARMS[arm]
    return calib_replay.admit(v, IDS, cos, shown, scale, found if shown else silent, top1, ALL, ALL)


def test_the_meaning_fact_goes_after_the_first_five_shown():
    assert calib_replay.with_meaning([1, 2, 3, 4, 5, 6, 7], [9]) == [1, 2, 3, 4, 5, 9, 6, 7]
    assert calib_replay.with_meaning([1, 2], [9]) == [1, 2, 9]
    assert calib_replay.with_meaning([], [9]) == [9]


def test_the_floor_walks_past_a_shown_fact_and_the_closest_only_arm_does_not(v):
    cos = scores({1: 0.9, 2: 0.7}, bulk=(0.3, 0.3))
    assert add(v, cos, [1], "floor") == [2]  # the words already show the closest: the next one above 0.55 is added
    assert add(v, cos, [1], "H3") == []  # the closest or none
    assert add(v, cos, [], "H3") == [1]
    assert add(v, scores({1: 0.5}, bulk=(0.3, 0.3)), [], "H3") == []  # below the floor


def test_the_two_tier_arm_takes_its_margin_from_whether_anything_was_shown(v):
    cos = scores({1: 1.0, 2: 1.0, 3: 0.8})
    z = v.emb.Meaning(IDS, cos, 0.0).z(1)
    assert v.emb.z_bar(30, 0.5) <= z < v.emb.z_bar(30, 0.7)  # between the two tiers
    assert add(v, cos, [], "zbar") == [] and add(v, cos, [9], "zbar") == []
    assert add(v, cos, [], "H1") == []  # nothing shown: the strict tier
    assert add(v, cos, [9], "H1") == [1]  # something shown: the looser one


def test_three_close_facts_mask_the_plain_z_and_not_the_robust_one(v):
    cos = scores({1: 1.0, 2: 0.99, 3: 0.98}, bulk=(0.28, 0.32))
    assert add(v, cos, [], "zbar") == []  # sqrt((30 - 3) / 3) = 3.0 is under any z_bar of 30 vectors
    assert add(v, cos, [], "H4") == [1]
    assert add(v, scores({}, bulk=(0.3, 0.3)), [], "H4") == []  # a flat store: no scale, nothing stands out


def _dump(probes):
    return {"fact_ids": IDS, "eligible": IDS, "recallable": IDS, "probes": probes}


def test_a_cell_adds_nothing_to_a_probe_the_plugin_would_not_embed(v):
    cos = {"content": scores({1: 0.9}, bulk=(0.3, 0.3))}
    dump = _dump([{"qid": "a", "meaning_call": "ok", "cos": cos}, {"qid": "b", "meaning_call": "skipped", "cos": {}}])
    got = calib_replay.cell(v, dump, {"a": [], "b": [4]}, "content", *calib_replay.ARMS["floor"])
    assert got == {"a": [1], "b": [4]}


def test_the_judge_counts_rescues_noise_and_non_targets_in_the_top_five(v):
    probes = [{"qid": "hit", "kind": "real", "targets": [1]}, {"qid": "miss", "kind": "real", "targets": [2]},
              {"qid": "none", "kind": "real", "targets": []}, {"qid": "chat", "kind": "chit", "targets": []}]
    lexical = {"hit": [1], "miss": [], "none": [], "chat": []}
    base = dict(lexical)
    point = {"hit": [1, 7], "miss": [2], "none": [8], "chat": []}
    j = calib_replay.judge(v, probes, lexical, base, point)
    assert (j["b_rescued"], j["c_lost"], j["hit5"]) == (1, 0, 2)
    assert j["noise"] == [0, 1] and j["confusion"] == [0, 1]  # a no-answer row got output; a hit row a non-target
    assert (j["added_target"], j["added_other"]) == (1, 2)
    assert j["conditions"]["no_target_lost"] and not j["passes"]


def test_the_stub_dump_has_four_vector_texts_and_no_text_and_replays(v, tmp_path):
    keywords = tmp_path / "kw.json"
    keywords.write_text(json.dumps({"1": ["python", "web"], "2": ["数据库"]}), encoding="utf-8")
    out = tmp_path / "dump.json"
    dump = calib_dump.main(["--stub", "--facts", str(EVAL / "facts.json"), "--keywords", str(keywords),
                            "--queries", str(EVAL / "queries.json"), "--out", str(out)])
    asked = [p for p in dump["probes"] if p["meaning_call"] == "ok"]
    assert asked and all(set(p["cos"]) == set(calib_dump.VARIANTS) for p in asked)
    assert all(len(xs) == len(dump["fact_ids"]) for p in asked for xs in p["cos"].values())
    assert sorted(set(dump["fact_ids"]) - set(dump["no_keywords"])) == [1, 2]
    # a fact without keywords keeps its content in every vector text; one with keywords does not
    k3, k1 = dump["fact_ids"].index(3), dump["fact_ids"].index(1)
    assert len({p["cos"][name][k3] for name in calib_dump.VARIANTS for p in asked[:1]}) == 1
    assert len({asked[0]["cos"][name][k1] for name in calib_dump.VARIANTS}) > 1
    text = out.read_text(encoding="utf-8")
    facts = json.loads((EVAL / "facts.json").read_text(encoding="utf-8"))
    queries = json.loads((EVAL / "queries.json").read_text(encoding="utf-8"))
    queries = queries["queries"] if isinstance(queries, dict) else queries
    assert not any(f["content"] in text for f in facts) and not any(q["query"] in text for q in queries)

    rows = tmp_path / "rows.jsonl"
    rows.write_text("".join(json.dumps({"qid": p["qid"], "keys": [], "by_meaning": [], "targets": p["targets"]}) + "\n"
                            for p in dump["probes"]), encoding="utf-8")
    s = calib_replay.main(["--dump", str(out), "--lexical", str(rows), "--check", f"content/zbar={rows}"])
    assert set(s["variants"]) == set(calib_dump.VARIANTS)
    assert set(s["variants"]["content"]["arms"]) == set(calib_replay.ARMS)
    assert s["variants"]["content"]["arms"]["zbar"]["b_rescued"] == 0  # the baseline against itself


def test_a_store_gives_its_keywords_from_its_tags_when_the_snapshot_splits_them(tmp_path):
    src = HERE.parent.parent / "vendor" / "holographic-0.30.0"  # the default 0.27.0 has no keywords in tags
    if not (src / "embeddings.py").is_file():
        pytest.skip("no 0.30.0 snapshot checked out")
    con = sqlite3.connect(tmp_path / "store.db")
    con.execute("CREATE TABLE facts (fact_id INTEGER PRIMARY KEY, content TEXT, trust_score REAL, tags TEXT)")
    tags = {1: "keywords: python, web", 2: "mine\nkeywords: db", 3: "only a tag of the person"}
    for f in json.loads((EVAL / "facts.json").read_text(encoding="utf-8")):
        con.execute("INSERT INTO facts VALUES (?,?,?,?)", (f["fact_id"], f["content"], 0.5, tags.get(f["fact_id"])))
    con.commit()
    con.close()

    def dump(*more):
        return subprocess.run([sys.executable, "calib_dump.py", "--stub", "--store", str(tmp_path / "store.db"),
                               "--queries", str(EVAL / "queries.json"), "--out", str(tmp_path / "d.json"), *more],
                              cwd=HERE, env=child_env("0"), capture_output=True, text=True, encoding="utf-8")

    assert dump("--plugin-src", str(src)).returncode == 0
    d = json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))
    assert sorted(set(d["fact_ids"]) - set(d["no_keywords"])) == [1, 2]
    assert "does not split keywords from tags" in dump().stderr  # the default snapshot refuses, it does not guess


def test_a_shown_fact_almost_as_close_and_a_disagreeing_content_view_each_stop_the_added_fact(v):
    near = scores({1: 0.70, 2: 0.66}, bulk=(0.3, 0.3))  # fact 2, shown by the words, is 0.04 behind fact 1
    far = scores({1: 0.70, 2: 0.60}, bulk=(0.3, 0.3))  # 0.10 behind
    other = scores({3: 0.70}, bulk=(0.3, 0.3))  # the content-only vectors put fact 3 first
    probes = [{"qid": q, "meaning_call": "ok", "cos": {"kw": cos, "content": view}}
              for q, cos, view in (("near", near, near), ("far", far, far), ("agree", far, far), ("differ", far, other))]
    lexical = {"near": [2], "far": [2], "agree": [], "differ": []}

    def keys(arm):
        return calib_replay.cell(v, _dump(probes), lexical, "kw", *calib_replay.ARMS[arm])

    assert keys("H3") == {"near": [2, 1], "far": [2, 1], "agree": [1], "differ": [1]}
    assert keys("H5") == {"near": [2], "far": [2, 1], "agree": [1], "differ": [1]}  # only where something is shown
    assert keys("H6") == {"near": [2, 1], "far": [2, 1], "agree": [1], "differ": []}  # only where nothing is
    assert keys("H5+H6") == {"near": [2], "far": [2, 1], "agree": [1], "differ": []}
