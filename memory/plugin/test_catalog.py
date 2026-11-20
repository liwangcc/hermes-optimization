"""Self-check of the write routing, the fact catalog, `fact_store get` and the memory-checkup reads in
holographic-semantic, against a stub of the base provider (the real one needs a Hermes checkout).
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
    holo._dumps = lambda v: json.dumps(v, ensure_ascii=False)
    holo.tool_error = lambda m: json.dumps({"error": m})
    holo.is_truthy_value = lambda v: v is True or str(v).lower() == "true"
    memory = types.ModuleType("plugins.memory")
    memory.import_provider_module = lambda name: holo
    sys.modules.update({"fakeholo": holo, "fakeholo.text": types.ModuleType("fakeholo.text"),
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
                                                "used": 0, "limit": 50, "unit": "estimated tokens",
                                                "overlaps": ["memory"]}]}
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
    sys.modules["hermes_constants"] = constants
    sys.modules["fakeholo"]._load_plugin_config = lambda: dict(section)
    _Base.save_config = lambda self, values, hermes_home: saved.append((values, hermes_home))
    return homes, saved


def test_the_desktop_panel_reads_and_writes_the_profile_it_is_given():
    p = _provider({}, FACTS)
    homes, saved = _settings_env({"semantic_enabled": True, "semantic_tau": 0.6, "scope": "profile"})
    assert p.read_config_fields("/homes/work") == {"values": {"semantic_enabled": True, "semantic_tau": 0.6},
                                                   "placeholders": {}}  # only our keys; absent = the default
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
        [job] = p.maintenance_actions(tmp)
        assert job["id"] == "semantic-index" and job["ready"] is True
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
            [job] = p.maintenance_actions(tmp)
            assert job["ready"] is False and why in job["status"], job  # another store; a model not loaded
            sidecar.server.shutdown()
        _settings_env({"semantic_url": "http://127.0.0.1:9"})  # nothing listens there
        [job] = p.maintenance_actions(tmp)
        assert job["ready"] is False and "not answering" in job["status"]


if __name__ == "__main__":
    for name, check in list(globals().items()):
        if name.startswith("test_"):
            check()
            print("ok", name)
