"""Facts and probes: fragments, the auto draw, labelled files, and the plugin's own send screens on the way out."""
import json
import sqlite3

import pytest

import calib_probes
import calib_run
from conftest import EVAL, HERE

SECRET = "数据库连接 password=Zq8vN3xK7mP2wR 已经配好"


def facts(n=20):
    return [{"fact_id": i, "content": f"第{i}条事实：这里写着一段足够长的项目说明文字", "trust_score": 0.5}
            for i in range(1, n + 1)]


def test_fragment_is_the_middle_half_cut_from_the_text():
    assert calib_probes.fragment("一二三四五六七八") == "三四五六"
    assert calib_probes.fragment("the backend uses FastAPI for async requests") == "backend uses FastAPI for"
    assert calib_probes.fragment("后端用 FastAPI 框架，异步处理请求。") == "FastAPI 框架，异步处"  # spaces kept
    assert calib_probes.fragment("x") == "x" and calib_probes.fragment("  ") == ""


def test_the_auto_draw_is_seeded_and_splits_a_quarter_into_holdouts():
    a = calib_probes.auto_probes(facts(), 8, 1, lambda t: True)
    assert a == calib_probes.auto_probes(facts(), 8, 1, lambda t: True)
    assert a != calib_probes.auto_probes(facts(), 8, 2, lambda t: True)
    pos = [p for p in a if p["category"] == "fragment"]
    hold = [p for p in a if p["category"] == "holdout"]
    chit = [p for p in a if p["category"] == "chit"]
    assert (len(pos), len(hold), len(chit)) == (6, 2, len(calib_probes.CHIT))
    assert all(p["targets"] == [int(p["qid"][5:])] and p["holdout"] is None for p in pos)
    assert all(p["targets"] == [] and p["holdout"] == int(p["qid"][5:]) and p["kind"] == "real" for p in hold)
    assert not {p["targets"][0] for p in pos} & {p["holdout"] for p in hold}
    assert all(p["kind"] == "chit" and not p["targets"] for p in chit)


def test_a_small_store_still_gets_holdouts_and_unembeddable_fragments_are_skipped():
    small = [{"fact_id": i, "content": f"项目说明{str(i) * 4}其余内容", "trust_score": 0.5} for i in range(1, 7)]
    assert calib_probes.fragment(small[2]["content"]) == "说明3333其余"
    got = calib_probes.auto_probes(small, 40, 1, lambda t: "3333" not in t and "4444" not in t)
    real = [p for p in got if p["kind"] == "real"]
    assert sorted(p["category"] for p in real) == ["fragment"] * 3 + ["holdout"]
    used = [p["targets"][0] if p["targets"] else p["holdout"] for p in real]
    assert sorted(used) == [1, 2, 5, 6]


def test_the_builtin_chit_chat_is_embedded_by_the_plugin(v):
    for text in calib_probes.CHIT:
        assert v.emb.worth_asking(text, before_turn=True) and not v.screen._secret_in(text)


def test_labelled_files_of_both_formats(tmp_path):
    ids = {1, 2, 3}
    (tmp_path / "eval.json").write_text(json.dumps({"queries": [
        {"id": "P1", "category": "paraphrase", "query": "数据存在哪里", "expected": [2]},
        {"id": "N1", "category": "negative", "query": "今天天气怎么样", "expected": []}]}), encoding="utf-8")
    (tmp_path / "kg.json").write_text(json.dumps({"queries": [
        {"qid": "R1", "kind": "real", "category": "no_answer", "lang": "en", "q": "which queue", "targets": []}]}),
        encoding="utf-8")
    a = calib_probes.labelled_probes(tmp_path / "eval.json", ids)
    assert [(p["qid"], p["kind"], p["lang"], p["targets"]) for p in a] == [("P1", "real", "zh", [2]), ("N1", "chit", "zh", [])]
    b = calib_probes.labelled_probes(tmp_path / "kg.json", ids)
    assert [(p["qid"], p["kind"], p["category"], p["lang"]) for p in b] == [("R1", "real", "no_answer", "en")]
    (tmp_path / "bad.json").write_text(json.dumps([{"id": "X", "query": "q", "expected": [9]}]), encoding="utf-8")
    with pytest.raises(SystemExit, match="not a fact of this store"):
        calib_probes.labelled_probes(tmp_path / "bad.json", ids)


def test_the_synthetic_query_file_reads_as_36_labelled_and_6_chit():
    facts_ = calib_probes.load_facts(EVAL / "facts.json")
    probes = calib_probes.labelled_probes(EVAL / "queries.json", {f["fact_id"] for f in facts_})
    assert len(facts_) == 30 and len(probes) == 42
    assert sum(p["kind"] == "chit" for p in probes) == 6 and sum(bool(p["targets"]) for p in probes) == 36


def test_a_secret_looking_fact_is_never_sent_and_an_unworthy_probe_is_never_embedded(v, tmp_path, monkeypatch):
    assert not v.screen._sendable(SECRET)
    store = facts(24) + [{"fact_id": 99, "content": SECRET, "trust_score": 0.9}]
    (tmp_path / "facts.json").write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "q.json").write_text(json.dumps([{"id": "G", "query": "hello", "expected": []},
                                                 {"id": "S", "query": SECRET, "expected": [99]},
                                                 {"id": "P", "query": "第5条事实写着什么项目说明", "expected": [5]}],
                                                ensure_ascii=False), encoding="utf-8")
    sent = []
    real = calib_run.stub_vector
    monkeypatch.setattr(calib_run, "stub_vector", lambda t: sent.append(t) or real(t))
    calib_run.main(["--stub", "--facts", str(tmp_path / "facts.json"), "--queries", str(tmp_path / "q.json"),
                    "--out", str(tmp_path / "run")])
    assert len(sent) == 24 + 1 and not any("Zq8vN3xK7mP2wR" in t or t == "hello" for t in sent)
    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text(encoding="utf-8"))
    assert (manifest["fact_n"], manifest["vec_n"], manifest["unsendable_n"], manifest["probes_skipped_n"]) == (25, 24, 1, 2)
    probes = {p["qid"]: p for p in map(json.loads, (tmp_path / "run" / "probes.jsonl").read_text(encoding="utf-8").splitlines())}
    assert probes["G"]["meaning_call"] == probes["S"]["meaning_call"] == "skipped"
    rows = [json.loads(x) for x in (tmp_path / "run" / "rows.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["keys"] == [] for r in rows if r["qid"] in ("G", "S"))
    assert not any(99 in r["keys"] for r in rows)  # no vector, never admitted


def test_duplicate_fact_ids_and_duplicate_qids_are_refused_before_anything_is_sent(tmp_path):
    (tmp_path / "f.json").write_text(json.dumps(facts(3) + facts(1)), encoding="utf-8")
    with pytest.raises(SystemExit, match="share a fact_id"):
        calib_probes.load_facts(tmp_path / "f.json")
    (tmp_path / "q.json").write_text(json.dumps([{"id": "P1", "query": "a b", "expected": []}] * 2), encoding="utf-8")
    with pytest.raises(SystemExit, match="share a qid"):
        calib_probes.labelled_probes(tmp_path / "q.json", {1})


def test_only_facts_prefetch_could_admit_are_admitted_or_drawn(v, tmp_path):
    role = "You are the assistant of Ada. You have received a new task: summarise the project notes."
    assert v.screen._sendable(role) and v.screen._role_prompt(role)
    store = facts(24) + [{"fact_id": 50, "content": role, "trust_score": 0.9},
                         {"fact_id": 51, "content": "第51条事实：信任分太低的一段项目说明文字", "trust_score": 0.1}]
    (tmp_path / "facts.json").write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "q.json").write_text(json.dumps([{"id": "R", "query": role, "expected": [50]}]), encoding="utf-8")
    for extra in ([], ["--queries", str(tmp_path / "q.json")]):
        out = tmp_path / f"run{len(extra)}"
        calib_run.main(["--stub", "--facts", str(tmp_path / "facts.json"), "--out", str(out), *extra])
        rows = [json.loads(x) for x in (out / "rows.jsonl").read_text(encoding="utf-8").splitlines()]
        assert not any({50, 51} & set(r["keys"]) for r in rows)  # sent and ranked, never admitted
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert (manifest["vec_n"], manifest["below_trust_n"], manifest["role_prompt_n"]) == (26, 1, 1)
    probes = (tmp_path / "run0" / "probes.jsonl").read_text(encoding="utf-8")
    assert '"frag-50"' not in probes and '"frag-51"' not in probes and '"hold-50"' not in probes


def test_a_probe_set_the_plugin_would_never_embed_is_refused_before_the_estimate(v, tmp_path, capsys):
    (tmp_path / "q.json").write_text(json.dumps([{"id": "G", "query": "hello", "expected": []}]), encoding="utf-8")
    with pytest.raises(SystemExit, match="none of these probes"):
        calib_run.main(["--stub", "--facts", str(EVAL / "facts.json"), "--queries", str(tmp_path / "q.json"),
                        "--out", str(tmp_path / "run")])
    assert "estimate" not in capsys.readouterr().out


def test_a_null_trust_in_a_store_is_never_eligible(tmp_path):
    _sqlite(tmp_path / "store.db", [{"fact_id": 1, "content": "x", "trust_score": None}])
    assert calib_probes.load_facts(store=str(tmp_path / "store.db"))[0]["trust_score"] is None
    (tmp_path / "f.json").write_text(json.dumps([{"fact_id": 1, "content": "x"}]), encoding="utf-8")
    assert calib_probes.load_facts(tmp_path / "f.json")[0]["trust_score"] == 0.5  # a JSON fact: the default trust


def _sqlite(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE facts (fact_id INTEGER PRIMARY KEY, content TEXT, trust_score REAL)")
    con.executemany("INSERT INTO facts VALUES (?, ?, ?)", [(f["fact_id"], f["content"], f["trust_score"]) for f in rows])
    con.commit()
    con.close()


def test_a_store_copy_reads_like_the_json_and_its_run_stays_out_of_the_repository(v, tmp_path):
    _sqlite(tmp_path / "store.db", facts(24))
    assert calib_probes.load_facts(store=str(tmp_path / "store.db")) == facts(24)
    inside = HERE / "run-on-a-real-store"
    with pytest.raises(SystemExit, match="outside the repository"):
        calib_run.main(["--stub", "--store", str(tmp_path / "store.db"), "--out", str(inside)])
    assert not inside.exists()
    calib_run.main(["--stub", "--store", str(tmp_path / "store.db"), "--out", str(tmp_path / "run")])
    raw = (tmp_path / "run" / "manifest.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in raw and str(tmp_path).replace("\\", "/") not in raw  # no path is written
