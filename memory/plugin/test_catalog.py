"""Self-check of the write routing, the fact catalog and `fact_store get` in holographic-semantic, against a stub
of the base provider (the real one needs a Hermes checkout). Run: python memory/plugin/test_catalog.py"""
import importlib.util
import json
import logging
import re
import sqlite3
import sys
import threading
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
    spec = importlib.util.spec_from_file_location(
        "holographic_semantic", Path(__file__).parent / "holographic-semantic" / "__init__.py")
    module = importlib.util.module_from_spec(spec)
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


if __name__ == "__main__":
    for name, check in list(globals().items()):
        if name.startswith("test_"):
            check()
            print("ok", name)
