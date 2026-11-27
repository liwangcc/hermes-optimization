"""Self-check of the catalog, write routing, settings, and local semantic recall in holographic-semantic,
against a stub of the base provider (the real one needs a Hermes checkout).
Run: python memory/plugin/test_catalog.py"""
import importlib.util
import json
import logging
import re
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unicodedata
from pathlib import Path
from unittest.mock import Mock, patch

_BASE_SCHEMA = {"name": "fact_store", "description": "d",
                "parameters": {"properties": {"action": {"enum": ["search"]}}}}


class _Store:
    def __init__(self, facts):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("CREATE TABLE facts (fact_id INTEGER PRIMARY KEY, content TEXT, trust_score REAL, tags TEXT)")
        self._conn.executemany("INSERT INTO facts VALUES (?, ?, ?, ?)", facts)

    def read(self, sql, params=()):
        return self._conn.execute(sql, params).fetchall()

    def origins(self, fact_ids):
        return {2: {"origin": "inferred", "confirmations": 0}, 5: {"origin": None, "confirmations": 0}}


class _Base:
    _block = "# Holographic Memory"

    def __init__(self, config=None):
        self._store, self._retriever, self._op_lock, self._min_trust = None, None, threading.RLock(), 0.3
        self._config, self._scope = config or {}, "profile"

    def _db_path(self, hermes_home):  # as the base: db_path with $HERMES_HOME expanded
        return self._config.get("db_path", "$HERMES_HOME/memory_store.db").replace("$HERMES_HOME", hermes_home)

    def system_prompt_block(self):
        return self._block

    def get_tool_schemas(self):
        return [_BASE_SCHEMA, {"name": "fact_feedback"}]

    def handle_tool_call(self, tool_name, args, **kwargs):
        return "base"

    def _counted(self, results):
        return results

    def on_turn_start(self, turn_number, message, **kwargs):
        pass


def _approx_tokens(text):  # as the base: ASCII 4 per token, a wide character 1, any other 2 per token
    ascii_n = sum(ch < "\x80" for ch in text)
    wide = sum(unicodedata.east_asian_width(ch) in ("W", "F") for ch in text)
    return -(-ascii_n // 4) + wide + -(-(len(text) - ascii_n - wide) // 2)


def _split_tags(stored):  # as the base: (the user's tags, the keywords after the marker line)
    head, mark, tail = (stored or "").rpartition("keywords: ")
    return (head.strip(), [k.strip() for k in tail.split(",")]) if mark else (stored or "", [])


def _provider(config, facts):
    holo = types.ModuleType("fakeholo")
    holo.HolographicMemoryProvider = _Base
    holo.approx_tokens = _approx_tokens
    holo._recall_problem = lambda t: "a credential" if "password" in t else None
    holo._role_prompt = lambda t: False
    holo._split_tags = _split_tags
    holo._one_line = lambda t: " ".join(t.split())
    holo._dumps = lambda v: json.dumps(v, ensure_ascii=False)
    holo.tool_error = lambda m: json.dumps({"error": m})
    holo.is_truthy_value = lambda v: v is True or str(v).lower() == "true"
    holo.embeddings = types.SimpleNamespace(worth_asking=lambda q, *, before_turn: before_turn and q != "short")
    holo_text = types.ModuleType("fakeholo.text")
    holo_text.is_greeting = lambda q: q == "Hello"
    memory = types.ModuleType("plugins.memory")
    memory.import_provider_module = lambda name: holo
    sys.modules.update({"fakeholo": holo, "fakeholo.text": holo_text,
                        "plugins": types.ModuleType("plugins"), "plugins.memory": memory})
    package = Path(__file__).parent / "holographic-semantic"
    # as Hermes loads a plugin: a package, so its own modules import relatively
    spec = importlib.util.spec_from_file_location(
        "holographic_semantic", package / "__init__.py", submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(spec)
    sys.modules["holographic_semantic"] = module
    spec.loader.exec_module(module)
    provider = module.SemanticHolographicProvider(config)
    provider._store = _Store(facts)
    return provider


FACTS = [(1, "short", 0.5, "keywords: brief"), (2, "a long fact about config", 0.9, "mine\nkeywords: settings, setup"),
         (3, "the password is x", 0.9, ""), (4, "low trust", 0.1, ""),
         (5, "another long one here", 0.4, "keywords: password hint"),
         (6, "数据库最终用 PostgreSQL 而不是 MySQL", 0.3, "keywords: 数据库选型, 存储")]


def test_catalog_lists_by_id_within_the_budget():
    p = _provider({"catalog_enabled": True, "catalog_label_tokens": 3, "catalog_max_tokens": 7}, FACTS)
    block = p.system_prompt_block()
    assert "\n\n## Fact catalog" in block
    # trust decides who fits (#2, #1; #5 and #6 are over the budget), the id decides the order; a fact that fits is
    # listed in full (#1), a longer one by its keywords (#2)
    assert block.endswith("#1=short\n#2=settings…\n(+2 more not listed: fact_store list)")
    assert "#3=" not in block and "#4=" not in block  # screened / below the trust floor
    roomy = _provider({"catalog_enabled": True, "catalog_label_tokens": 3}, FACTS).system_prompt_block()
    assert "#5=another…" in roomy  # keywords recall would refuse are not shown: the opening words stand in
    assert "#6=数据…" in roomy  # the same 3 tokens: 8 letters of English (#2), 2 characters of Chinese
    whole = _provider({"catalog_enabled": True, "catalog_label_tokens": 10}, FACTS).system_prompt_block()
    assert "#6=数据库选型, 存储…" in whole  # keywords that fit whole still end in …: they are not the fact
    assert "#2=a long fact about config\n" in whole  # and a fact that fits is the fact, without one


def test_get_reads_by_id_and_names_what_is_missing():
    p = _provider({"catalog_enabled": True}, FACTS)
    answer = json.loads(p.handle_tool_call("fact_store", {"action": "get", "fact_ids": [2, "5", 99]}))
    assert [f["content"] for f in answer["facts"]] == ["a long fact about config", "another long one here"]
    assert answer["count"] == 2 and answer["missing"] == [99]
    assert [f.get("origin") for f in answer["facts"]] == ["inferred", None]  # unknown origin: no field
    assert "error" in json.loads(p.handle_tool_call("fact_store", {"action": "get"}))
    assert "error" in json.loads(p.handle_tool_call("fact_store", {"action": "get", "fact_ids": ["#2"]}))
    assert p.handle_tool_call("fact_store", {"action": "search", "query": "x"}) == "base"
    schema = p.get_tool_schemas()[0]
    assert "get" in schema["parameters"]["properties"]["action"]["enum"]
    assert "fact_ids" in schema["parameters"]["properties"]
    assert _BASE_SCHEMA["parameters"]["properties"]["action"]["enum"] == ["search"]  # the base's is untouched


def test_get_stops_at_its_budget_until_the_next_user_message():
    p = _provider({"catalog_enabled": True}, FACTS)
    get = lambda ids: json.loads(p.handle_tool_call("fact_store", {"action": "get", "fact_ids": ids}))  # noqa: E731
    assert get(list(range(100, 108)))["count"] == 0  # a sweep of ids that do not exist spends the budget too
    answer = get([1, 2, 5])  # two left
    assert [f["fact_id"] for f in answer["facts"]] == [1, 2] and answer["not_read"] == [5]
    spent = get([5])
    assert spent["facts"] == [] and spent["not_read"] == [5] and "returns no facts" in spent["note"]
    search = {"action": "search", "query": "x"}
    assert json.loads(p.handle_tool_call("fact_store", search))["note"] == spent["note"]  # the sweep cannot move on
    assert p.handle_tool_call("fact_store", {"action": "add", "content": "short"}) == "base"  # writing stays open
    p.on_turn_start(2, "next question")
    assert get([5])["count"] == 1 and p.handle_tool_call("fact_store", search) == "base"


def test_catalog_off_by_default_adds_no_catalog_and_no_get():
    p = _provider({"catalog_enabled": "false", "semantic_enabled": "false"}, FACTS)
    assert p._sem_enabled is False  # the string "false" is off, for both switches
    assert "## Fact catalog" not in p.system_prompt_block()
    assert p.get_tool_schemas()[0] is _BASE_SCHEMA
    assert p.handle_tool_call("fact_store", {"action": "get", "fact_ids": [1]}) == "base"


def test_write_routing_is_the_same_with_the_catalog_on_or_off():
    off = _provider({}, FACTS).system_prompt_block()  # the catalog is off by default
    on = _provider({"catalog_enabled": True}, FACTS).system_prompt_block()
    assert off.startswith("# Holographic Memory\n\n## Where a new memory goes\n")
    assert on.startswith(off + "\n\n## Fact catalog")  # the same text; the catalog only follows it
    routing = off.partition("\n\n")[2]
    assert on.count(routing) == 1
    for place in ("fact_store (the default)", "USER.md", "MEMORY.md"):
        assert place in routing
    assert "→ MEMORY.md" not in routing  # nothing is routed there: the design has it off
    assert "If USER.md is turned off, use fact_store" in routing  # each built-in store is switched on its own
    # a write policy that leans on nothing the catalog switch adds, and carries no fact id of its own
    assert "catalog" not in routing.lower() and "fact_ids" not in routing and not re.search(r"#\d", routing)
    assert "update" not in routing  # the base's update edits keywords only: a fact's text is revised
    assert routing in (Path(__file__).parent / "README.md").read_text(encoding="utf-8")  # the README quotes it
    # the routing stays when the catalog cannot be built, and when the base says nothing (fact_store is down)
    broken = _provider({"catalog_enabled": True}, FACTS)
    broken._catalog = lambda: 1 / 0
    logging.disable(logging.WARNING)  # the catalog left out is logged: expected here
    assert broken.system_prompt_block() == off
    logging.disable(logging.NOTSET)
    silent = _provider({"catalog_enabled": True}, FACTS)
    silent._block, silent._store = "", None
    assert silent.system_prompt_block() == routing


def _stored(home: Path, facts, inferred=(), confirmed=()) -> None:
    """A store file with the base's columns: (fact_id, content, trust_score, tags, retrieval_count, age in days)."""
    conn = sqlite3.connect(home / "memory_store.db")
    conn.execute("CREATE TABLE facts (fact_id INTEGER PRIMARY KEY, content TEXT, tags TEXT, trust_score REAL, "
                 "retrieval_count INTEGER, created_at TIMESTAMP)")
    conn.execute("CREATE TABLE fact_versions (fact_id INTEGER, status TEXT, src_origin TEXT)")
    conn.execute("CREATE TABLE fact_confirmations (fact_id INTEGER)")
    for fact_id, content, trust, tags, uses, age_days in facts:
        created = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - age_days * 86400))
        conn.execute("INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?)", (fact_id, content, tags, trust, uses, created))
    conn.executemany("INSERT INTO fact_versions VALUES (?, 'current', 'inferred')", [(i,) for i in inferred])
    conn.executemany("INSERT INTO fact_confirmations VALUES (?)", [(i,) for i in confirmed])
    conn.commit()
    conn.close()


STORED = [(1, "short", 0.5, "keywords: brief", 4, 90), (2, "a long fact about config", 0.9, "mine, Protected\nkeywords: settings", 0, 400),
          (3, "the password is x", 0.9, "", 0, 50), (4, "low trust", 0.1, "", 0, 50),
          (5, "another long one here", 0.4, "keywords: hint", 2, 2)]


def test_usage_report_counts_the_catalog_the_way_the_system_prompt_builds_it():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        _stored(home, STORED)
        config = {"catalog_enabled": True, "catalog_label_tokens": 3, "catalog_max_tokens": 7}
        report = _provider(config, FACTS).usage_report(tmp)  # never initialized: it opens the file itself
        assert report["items"] == 5  # every stored fact, listed or not
        assert report["storage_bytes"] == (home / "memory_store.db").stat().st_size
        [catalog] = report["budgets"]
        # the same rows through the catalog the agent is given: what is listed there is what is counted here
        live = _provider(config, [(i, c, t, tags) for i, c, t, tags, _, _ in STORED])
        lines = [line for line in live.system_prompt_block().splitlines() if re.match(r"#\d+=", line)]
        assert catalog["listed"] == len(lines) == 2 and catalog["eligible"] == 3  # #3 screened, #4 below the trust floor
        assert catalog["used"] == sum(_approx_tokens(line + "\n") for line in lines) <= catalog["limit"] == 7
        assert catalog["enabled"] is True and catalog["unit"] == "estimated tokens"
        assert "limit" not in report  # the store itself has no ceiling
        # read-only: SQLite refuses a write on the connection the report uses
        read_only = live.usage_report.__func__.__globals__["_read_only"]
        with read_only(home / "memory_store.db") as read:
            try:
                read("DELETE FROM facts")
                raise AssertionError("the review connection accepted a write")
            except sqlite3.OperationalError as refused:
                assert "readonly" in str(refused)


def test_usage_report_tells_off_empty_and_unsupported_apart():
    with tempfile.TemporaryDirectory() as tmp:
        off = _provider({"catalog_max_tokens": 50}, FACTS).usage_report(tmp)  # no store file yet, catalog off
        assert off == {"items": 0, "budgets": [{"key": "catalog", "label": "Fact catalog", "enabled": False,
                                                "used": 0, "field": "catalog_max_tokens", "limit": 50,
                                                "unit": "estimated tokens", "overlaps": ["memory"],
                                                "translations": {"zh": {"label": "事实目录", "unit": "估算 token"}}}]}
        assert not (Path(tmp) / "memory_store.db").exists()  # reading created nothing
        _stored(Path(tmp), STORED)
        assert "listed" not in _provider({}, FACTS).usage_report(tmp)["budgets"][0]  # off: nothing is listed
        scoped = _provider({"catalog_enabled": True}, FACTS)
        scoped._scope = "user"  # one store per user: not one file to report
        assert scoped.usage_report(tmp) == {} and scoped.review_items(tmp) == {}
        assert _provider({"db_path": ":memory:"}, FACTS).usage_report(tmp) == {}


def test_review_items_carry_what_a_review_weighs_and_leave_out_what_recall_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        assert _provider({}, FACTS).review_items(tmp) == {"items": []}  # supported, and nothing stored
        _stored(Path(tmp), STORED, inferred=(1, 5), confirmed=(5,))
        items = {i["id"]: i for i in _provider({}, FACTS).review_items(tmp)["items"]}
        assert sorted(items) == ["1", "2", "4", "5"]  # the credential (#3) is not sent to a model; low trust is
        assert items["2"]["text"] == "a long fact about config" and items["2"]["protected"] is True  # the user's tag
        assert not any(items[i]["protected"] for i in ("1", "4", "5"))  # "keywords: ..." is not a user tag
        assert (items["1"]["uses"], items["1"]["score"]) == (4, 0.5)
        assert items["1"]["unconfirmed"] is True and items["5"]["unconfirmed"] is False  # #5 was confirmed since
        assert abs(time.time() - items["5"]["created_at"] - 2 * 86400) < 120  # UTC timestamps, as epoch seconds


def _settings_env(section):
    """The base's config reader and Hermes' home override, recorded: (homes read, values saved)."""
    homes, saved = [], []
    constants = types.ModuleType("hermes_constants")
    constants.set_hermes_home_override = lambda home: homes.append(home) or len(homes)
    constants.reset_hermes_home_override = lambda token: None
    constants.mkdir_under_hermes_home = lambda path: Path(path).mkdir(parents=True, exist_ok=True)
    config = types.ModuleType("hermes_cli.config")
    config.load_env = dict
    config.load_config_readonly = lambda: {"memory": {"provider": "holographic-semantic"}}
    cli = types.ModuleType("hermes_cli")
    cli.config = config
    sys.modules.update({"hermes_constants": constants, "hermes_cli": cli, "hermes_cli.config": config})
    sys.modules["fakeholo"]._load_plugin_config = lambda: dict(section)

    def save_config(self, values, hermes_home):
        saved.append((values, hermes_home))
        section.update(values)

    _Base.save_config = save_config
    return homes, saved


def test_the_desktop_panel_reads_and_writes_the_profile_it_is_given():
    p = _provider({}, FACTS)
    homes, saved = _settings_env({"semantic_enabled": True, "semantic_tau": 0.6, "scope": "profile"})
    assert p.read_config_fields("/homes/work") == {"values": {"semantic_enabled": True, "semantic_tau": 0.6},
                                                   "placeholders": {}, "connection_state": "local"}  # only our keys; absent = the default
    assert homes == ["/homes/work"]  # the profile being configured, not this process's own
    p.write_config_fields({"catalog_enabled": True, "semantic_tau": None, "scope": "user"}, "/homes/work")
    # a cleared field goes back to its default; a key that is not ours is never written from this panel
    assert saved == [({"catalog_enabled": True, "semantic_tau": 0.55}, "/homes/work")]


class _FakeSidecar:
    """/health and /sync over 127.0.0.1, at most `per_call` facts a call, as the real one answers."""

    def __init__(self, total, per_call=2, ok=True):
        import http.server
        state = self
        self.total, self.indexed, self.per_call, self.ok = total, 0, per_call, ok

        class Handler(http.server.BaseHTTPRequestHandler):
            def _send(self, obj):
                body = json.dumps(obj).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._send({"ok": state.ok, "model": "bge-m3", "device": "cpu", "facts_indexed": state.indexed,
                            "facts": state.total, "error": "" if state.ok else "no weights"})

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                embedded = min(state.per_call, state.total - state.indexed)
                state.indexed += embedded
                self._send({"embedded": embedded, "remaining": state.total - state.indexed, "facts": state.total})

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


def test_the_index_job_says_where_it_stands_and_runs_batch_by_batch():
    with tempfile.TemporaryDirectory() as tmp:
        _stored(Path(tmp), STORED)  # 5 facts
        sidecar = _FakeSidecar(total=5)
        p = _provider({}, FACTS)
        _settings_env({"semantic_url": sidecar.url})
        job = next(j for j in p.maintenance_actions(tmp) if j["id"] == "semantic-index")
        assert job["ready"] is True
        assert job["status"].startswith("0 of 5 facts indexed (bge-m3 on cpu).") and "turn it on above" in job["status"]
        steps = [p.run_maintenance_step("semantic-index", tmp) for _ in range(3)]
        assert [s["status"] for s in steps] == ["2 of 5 facts indexed", "4 of 5 facts indexed", "5 of 5 facts indexed"]
        assert [s["done"] for s in steps] == [False, False, True]
        assert steps[-1]["result"] == "All 5 facts are indexed; this run embedded 5."
        try:
            p.run_maintenance_step("other", tmp)
            raise AssertionError("an unknown job ran")
        except ValueError:
            pass
        sidecar.server.shutdown()


def test_the_index_job_cannot_start_while_the_sidecar_cannot_do_it():
    with tempfile.TemporaryDirectory() as tmp:
        _stored(Path(tmp), STORED)
        p = _provider({}, FACTS)
        for sidecar, why in ((_FakeSidecar(total=9), "holds 5"), (_FakeSidecar(total=5, ok=False), "no weights")):
            _settings_env({"semantic_url": sidecar.url, "semantic_enabled": True})
            job = next(j for j in p.maintenance_actions(tmp) if j["id"] == "semantic-index")
            assert job["ready"] is False and why in job["status"], job  # another store; a model not loaded
            sidecar.server.shutdown()
        _settings_env({"semantic_url": "http://127.0.0.1:9"})  # nothing listens there
        job = next(j for j in p.maintenance_actions(tmp) if j["id"] == "semantic-index")
        assert job["ready"] is False and "not answering" in job["status"]


_QUERY = "Where are the database settings?"
_RANKED = [{"fact_id": 1, "cos": 0.8}, {"fact_id": 2, "cos": 0.7}]


def _semantic_provider():
    p = _provider({"semantic_enabled": True}, FACTS)
    p._session_id, p._scope_key = "test", ""
    p._turns, p._last_recall = {"test|": 1}, 0
    p._not_recent = Mock(return_value=True)
    p._recallable = Mock(return_value=True)
    p._retriever = types.SimpleNamespace(names_fit=Mock(return_value=True))
    p._remember = Mock()
    p._counted = Mock()
    return p


def _semantic_prefetch(p, *, query=_QUERY, base="", candidates=_RANKED):
    with patch.object(_Base, "prefetch", return_value=base, create=True), patch("urllib.request.build_opener") as http:
        response = http.return_value.open.return_value.__enter__.return_value
        response.read.return_value = json.dumps({"candidates": candidates}).encode("utf-8")
        result = p.prefetch(query, session_id="test")
    assert not p._sem_warned
    return result, http


def test_semantic_adds_only_the_closest_fact():
    p = _semantic_provider()
    block, http = _semantic_prefetch(p)
    assert re.findall(r"^- #\d+ .*", block, re.MULTILINE) == ["- #1 [0.5] short"]
    http.return_value.open.assert_called_once()
    request = http.return_value.open.call_args.args[0]
    assert json.loads(request.data) == {"query": _QUERY, "tau": 0.55, "limit": 1, "min_trust": 0.3}
    fact = {"fact_id": 1, "content": "short", "trust_score": 0.5, "tags": "keywords: brief"}
    p._retriever.names_fit.assert_called_once_with(_QUERY, fact)
    p._remember.assert_called_once_with("test|", fact, 1)
    p._counted.assert_called_once_with([fact])
    assert p._last_recall == 1


def test_semantic_skips_a_top_fact_already_shown():
    p = _semantic_provider()
    base = "# Holographic Memory\n- #1 [0.5] short"
    assert _semantic_prefetch(p, base=base)[0] == base
    p._remember.assert_not_called()


def test_semantic_skips_a_top_fact_rejected_by_any_base_check():
    p = _semantic_provider()
    for check in (p._not_recent, p._recallable, p._retriever.names_fit):
        check.return_value = False
        assert _semantic_prefetch(p)[0] == ""
        p._remember.assert_not_called()
        check.return_value = True


def test_semantic_skips_a_top_fact_below_threshold():
    p = _semantic_provider()
    assert _semantic_prefetch(p, candidates=[{"fact_id": 1, "cos": 0.54}])[0] == ""
    p._remember.assert_not_called()


def test_semantic_does_not_request_the_sidecar_for_short_messages_or_greetings():
    p = _semantic_provider()
    for query in ("short", "Hello"):
        block, http = _semantic_prefetch(p, query=query)
        assert block == ""
        http.assert_not_called()


def _layout_prefetch(self, query, *, session_id=""):
    """The base's shape with rerank off: its layout picks the facts (the wrapper's hook), then it writes them."""
    lexical = [dict(r) for r in self._store.read("SELECT * FROM facts WHERE fact_id IN (2, 5)")]
    facts, by_meaning = self._off_layout(query, None, "test|", 1, lexical)
    return "\n".join(["# Holographic Memory", *(
        f"- #{f['fact_id']} [{f['trust_score']:.1f}] {f['content']}" + (" (by meaning)" * (f["fact_id"] in by_meaning))
        for f in facts)]) if facts else ""


def _judged_provider():
    p = _semantic_provider()
    p._judge, p._min_coverage = True, 0.3
    p._judge_health = {"ok": True, "judge": True, "device": "cpu"}
    p._judge_health_until = float("inf")
    p._retriever.relevant = lambda query, candidates, coverage: candidates[:1]  # the words admitted #2 only
    return p


def _judged_prefetch(p, answers, query=_QUERY):
    """prefetch over the stub layout; *answers*: what each sidecar call returns (a dict) or raises."""
    layout = lambda self, query, meaning, key, turn, candidates=None: (candidates, set())  # noqa: E731
    with patch.object(_Base, "prefetch", _layout_prefetch, create=True), \
            patch.object(_Base, "_off_layout", layout, create=True), patch("urllib.request.build_opener") as http:
        opened = http.return_value.open
        opened.side_effect = [a if isinstance(a, Exception) else Mock(__enter__=Mock(return_value=Mock(
            read=Mock(return_value=json.dumps(a).encode("utf-8")))), __exit__=Mock(return_value=False))
            for a in answers]
        block = p.prefetch(query, session_id="test")
        bodies = [c.args[0].data for c in opened.call_args_list]
        return block, [json.loads(body) if body is not None else None for body in bodies]


def test_judged_recall_drops_what_is_off_the_message_adds_what_is_confirmed_and_lists_the_close():
    p = _judged_provider()
    assert "get" in p.get_tool_schemas()[0]["parameters"]["properties"]["action"]["enum"]  # the pointers' reader
    rows = [{"fact_id": 2, "cos": 0.5, "rank": 2, "strict": 1.0, "generic": 2.0},   # in the block, by words: stays
            {"fact_id": 5, "cos": 0.3, "rank": 5, "strict": -8.0, "generic": -9.0},  # in the block, off: dropped
            {"fact_id": 6, "cos": 0.6, "rank": 0, "strict": 3.0, "generic": 4.0},    # the closest, confirmed: added
            {"fact_id": 1, "cos": 0.45, "rank": 1, "strict": -6.0, "generic": -2.0}]  # not confirmed: only listed
    block, sent = _judged_prefetch(p, [{"facts": rows}])
    assert block.splitlines() == [
        "# Holographic Memory", "- #6 [0.3] 数据库最终用 PostgreSQL 而不是 MySQL (by meaning)",
        "- #2 [0.9] a long fact about config",
        "Close, not recalled (read one in full: fact_store get {fact_ids}):", "#1=short"]
    assert sent == [{"query": _QUERY, "ids": [2, 5], "k": 10, "min_trust": 0.3}]  # one call a turn, no /candidates
    p._retriever.names_fit.return_value = False  # the base's name check stands for a fact the block did not hold
    assert "#6" not in _judged_prefetch(p, [{"facts": rows}])[0].split("Close")[0]


def test_judged_recall_lists_every_pointer_by_cosine_when_the_sidecar_sends_no_generic_reading():
    _judged_provider()  # loads the package
    decide = sys.modules["holographic_semantic"].judged_recall.decide
    rows = [{"fact_id": n, "cos": 0.9 - n / 10, "rank": n, "strict": -9.0, "generic": g}  # none is shown in full
            for n, g in enumerate([-9.0, -9.0, -9.0, 3.0, 2.0, -9.0])]
    # a CUDA sidecar: the generic reading's best two, then the two closest of the rest
    assert decide(rows, [], set(), True, 0.55, 7, lambda fact_id: True) == ([], [3, 4, 0, 1])
    strict_only = [{k: v for k, v in f.items() if k != "generic"} for f in rows]
    assert decide(strict_only, [], set(), True, 0.55, 7, lambda fact_id: True) == ([], [0, 1, 2, 3])
    # off CUDA the judge reads the block (#5 here) and the closest fact: the others come with their cosine only
    read = [{"fact_id": 5, "cos": 0.4, "rank": 5, "strict": 4.0}, {"fact_id": 0, "cos": 0.9, "rank": 0, "strict": 9.0},
            *({"fact_id": n, "cos": 0.9 - n / 10, "rank": n} for n in range(1, 5))]
    assert decide(read, [5], set(), True, 0.55, 7, lambda fact_id: True) == ([0, 5], [])  # #0 is a sure answer
    read[1]["strict"] = -9.0
    assert decide(read, [5], set(), True, 0.55, 7, lambda fact_id: True) == ([5], [0, 1, 2, 3])
    try:  # a block fact the judge did not read is not the protocol: the caller falls back to the base's block
        decide([{"fact_id": 5, "cos": 0.4, "rank": 5}], [5], set(), True, 0.55, 7, lambda fact_id: True)
        raise AssertionError("an unread block fact was decided")
    except KeyError:
        pass


def test_judged_recall_falls_back_to_the_unjudged_append_or_to_the_base_block():
    import urllib.error
    base = "# Holographic Memory\n- #2 [0.9] a long fact about config\n- #5 [0.4] another long one here"
    p = _judged_provider()
    no_judge = urllib.error.HTTPError("http://sidecar/judge", 404, "no judge model", None, None)
    block, sent = _judged_prefetch(p, [no_judge, {"candidates": _RANKED}])  # a sidecar started without a judge
    assert block == base + "\n- #1 [0.5] short" and "tau" in sent[1]  # recall as without the switch
    p = _judged_provider()
    block, sent = _judged_prefetch(p, [OSError("timed out")])  # asked and not answered: no second call this turn
    assert block == base and len(sent) == 1 and p._sem_warned
    block, sent = _judged_prefetch(p, [{"candidates": []}])  # and the judge is left alone for a while after
    assert block == base and "ids" not in sent[0]
    p = _judged_provider()
    p._rescorer = object()  # rerank on: the judge was measured without it
    assert _judged_prefetch(p, [{"candidates": []}])[0] == base


def test_judge_timeout_uses_a_shorter_pause_on_cuda():
    for device, pause in (("cuda", 12), ("cpu", 60), (None, 60)):
        p = _judged_provider()
        p._judge_health["device"] = device
        with patch("time.monotonic", return_value=100) as clock:
            _judged_prefetch(p, [TimeoutError("judge timed out")])
            assert p._judge_paused == 100 + pause
            clock.return_value = 100 + pause - 1
            _, sent = _judged_prefetch(p, [{"candidates": []}])
            assert len(sent) == 1 and "tau" in sent[0]
            clock.return_value = 100 + pause
            _, sent = _judged_prefetch(p, [{"facts": [{"fact_id": i, "cos": 0.6, "rank": n,
                                                    "strict": 2.0, "generic": 2.0}
                                                   for n, i in enumerate((2, 5))]}])
            assert len(sent) == 1 and sent[0]["ids"] == [2, 5]


def test_judge_uses_the_base_during_startup_and_resumes_on_readiness():
    import urllib.error
    p = _judged_provider()
    p._judge_health_until = 0
    healthy = {"ok": True, "judge": True, "device": "cuda"}
    judged = {"facts": [{"fact_id": i, "cos": 0.6, "rank": n, "strict": 2.0, "generic": 2.0}
                        for n, i in enumerate((2, 5))]}
    with patch("time.monotonic", return_value=100) as clock:
        base, sent = _judged_prefetch(p, [urllib.error.URLError(ConnectionRefusedError())])
        assert sent == [None] and p._judge_paused == 0
        assert _judged_prefetch(p, []) == (base, [])
        clock.return_value = 101
        _, sent = _judged_prefetch(p, [healthy, judged])
        assert sent[0] is None and sent[1]["ids"] == [2, 5]
        # A restart can happen while the ready status is still cached.
        warming = urllib.error.HTTPError("http://sidecar/judge", 503, "model not ready", None, None)
        assert _judged_prefetch(p, [warming])[0] == base
        assert _judged_prefetch(p, []) == (base, [])
        clock.return_value = 102
        _, sent = _judged_prefetch(p, [healthy, judged])
        assert sent[0] is None and sent[1]["ids"] == [2, 5] and p._judge_paused == 0


def test_legacy_semantic_max_extra_is_ignored():
    legacy = {"semantic_max_extra": "unused", "semantic_enabled": True}
    p = _provider(legacy, FACTS)
    _, saved = _settings_env(legacy)
    assert p.read_config_fields("/homes/work")["values"] == {"semantic_enabled": True}
    p.write_config_fields(legacy, "/homes/work")
    assert saved == [({"semantic_enabled": True}, "/homes/work")]


def _service_record(home, **fields):
    path = Path(home) / "services" / "memory-embeddings" / "service.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


def _run_local_setup(p, home, option):
    for _ in range(8):
        step = p.run_maintenance_step("semantic-setup-local", home, option=option)
        if step.get("done"):
            return
    raise AssertionError("local setup did not finish")


def test_switching_the_local_model_sets_tau_and_redeploying_it_preserves_tau():
    p = _provider({}, FACTS)
    from holographic_semantic import managed_local

    section = {"semantic_enabled": True, "semantic_tau": 0.71}
    _, saved = _settings_env(section)

    def prepare_model(profile, root, model):
        yield {"status": "weights ready"}
        return managed_local.managed_dir(root, model)

    with tempfile.TemporaryDirectory() as home, patch.multiple(
        managed_local, _ready=Mock(return_value={}), _check_embedding=Mock(), _stop_replaced=Mock(),
        _free_port=Mock(side_effect=(8811, 8812)), _launch=Mock(), _stop_started=Mock(),
        _wait_ready=Mock(return_value={"device": "cpu"}), prepare_model=prepare_model,
        prepare_runtime=lambda root: root / "runtime-test" / "Scripts" / "python.exe",
    ):
        _service_record(home, url="http://127.0.0.1:8791")  # pre-model-choice receipts identify BGE-M3
        _run_local_setup(p, home, "bge-small-zh")
        assert saved[-1][0]["semantic_tau"] == section["semantic_tau"] == 0.64
        assert managed_local.deployed(home, section["semantic_url"]).id == "bge-small-zh"

        p.write_config_fields({"semantic_tau": "0.67"}, home)
        _run_local_setup(p, home, "bge-small-zh")  # another port, same model
        assert section["semantic_url"] == "http://127.0.0.1:8812"
        assert "semantic_tau" not in saved[-1][0] and section["semantic_tau"] == 0.67


def test_reusing_a_verified_sidecar_records_the_model_for_the_next_deploy():
    p = _provider({}, FACTS)
    from holographic_semantic import managed_local

    section = {"semantic_tau": 0.67}
    _, saved = _settings_env(section)
    with tempfile.TemporaryDirectory() as home, patch.multiple(
        managed_local, _ready=Mock(return_value={"device": "cuda"}), _check_embedding=Mock(), _stop_replaced=Mock(),
    ):
        _run_local_setup(p, home, "bge-m3")
        url = section["semantic_url"]
        assert saved[-1][0]["semantic_tau"] == section["semantic_tau"] == 0.55
        assert managed_local.deployed(home, url).id == "bge-m3"
        assert managed_local.expected_store(home, url) is None  # the verified legacy service has no store ID

        p.write_config_fields({"semantic_tau": "0.60"}, home)
        _run_local_setup(p, home, "bge-m3")
        assert "semantic_tau" not in saved[-1][0] and section["semantic_tau"] == 0.60


def test_reusing_a_sidecar_restores_the_previous_record_if_saving_fails():
    p = _provider({}, FACTS)
    from holographic_semantic import managed_local

    section = {"semantic_url": "http://127.0.0.1:8811", "semantic_tau": 0.64, "semantic_enabled": True}
    _, saved = _settings_env(section)
    with tempfile.TemporaryDirectory() as home, patch.multiple(
        managed_local, _ready=Mock(return_value={"device": "cuda"}), _check_embedding=Mock(), _stop_replaced=Mock(),
    ), patch.object(p, "_save_connection", side_effect=ValueError("config write failed")):
        path = _service_record(home, url=section["semantic_url"], model_id="bge-small-zh", store_id="previous")
        previous = json.loads(path.read_text(encoding="utf-8"))
        try:
            _run_local_setup(p, home, "bge-m3")
            raise AssertionError("the failed config write went unnoticed")
        except ValueError as exc:
            assert str(exc) == "config write failed"
        assert json.loads(path.read_text(encoding="utf-8")) == previous
        assert not saved and section["semantic_tau"] == 0.64
        managed_local._stop_replaced.assert_not_called()


def _listed_threshold(p, home):
    from holographic_semantic import sidecar_index

    with patch.object(sidecar_index, "action", return_value={"id": "semantic-index"}):
        return next(job for job in p.maintenance_actions(home) if job["id"] == "semantic-threshold")


def test_the_local_threshold_job_suggests_the_model_value_without_fact_probes():
    p = _provider({}, FACTS)
    from holographic_semantic import threshold_job

    section = {"semantic_enabled": True, "semantic_tau": 0.71, "semantic_url": "http://127.0.0.1:8820"}
    _, saved = _settings_env(section)
    with tempfile.TemporaryDirectory() as home, patch.object(threshold_job, "_proposal") as old_proposal:
        _service_record(home, url=section["semantic_url"], model_id="multilingual-minilm")
        job = _listed_threshold(p, home)
        assert job["field"] == "semantic_tau" and job["ready"] and job["suggestion"] == "0.58"
        assert "Multilingual MiniLM-L12 v2" in job["status"] and "BUILTIN-QUESTIONS-RESULTS.md" in job["status"]

        step = p.run_maintenance_step("semantic-threshold", home)  # no fact DB or listening sidecar
        assert step["done"] and step["result"] == job["status"]
        old_proposal.assert_not_called()
        assert not saved and section["semantic_tau"] == 0.71

        p.write_config_fields({"semantic_tau": job["suggestion"]}, home)
        job = _listed_threshold(p, home)
        assert job["ready"] and "suggestion" not in job and "0.58" in job["status"]


def test_the_local_threshold_job_explains_an_unrecognized_manual_sidecar():
    p = _provider({}, FACTS)
    _settings_env({"semantic_enabled": True, "semantic_url": "http://127.0.0.1:8791", "semantic_tau": 0.71})
    with tempfile.TemporaryDirectory() as home:
        job = _listed_threshold(p, home)
        assert not job["ready"] and "suggestion" not in job and "unrecognized" in job["status"]
        step = p.run_maintenance_step("semantic-threshold", home)
        assert step["done"] and step["result"] == job["status"]


if __name__ == "__main__":
    for name, check in list(globals().items()):
        if name.startswith("test_"):
            check()
            print("ok", name)
