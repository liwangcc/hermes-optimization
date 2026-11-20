"""Self-check of the sidecar's index sync, with a fake model (the real one needs bge-m3 on disk).

Run: python memory/sidecar/test_sync.py   (needs numpy)
"""
import hashlib
import importlib.util
import os
import sqlite3
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="sidecar-sync-"))
os.environ["SEMANTIC_DB"] = str(TMP / "memory_store.db")
os.environ["SEMANTIC_CACHE"] = str(TMP / "cache")

_spec = importlib.util.spec_from_file_location("sidecar_server", Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


class FakeModel:
    """Deterministic unit vectors from the text; counts what it was asked to embed."""

    def __init__(self):
        self.encoded = []

    def encode(self, texts, **_):
        import numpy as np
        self.encoded += list(texts)
        out = []
        for t in texts:
            v = np.frombuffer(hashlib.sha256(t.encode("utf-8")).digest(), dtype=np.uint8).astype(np.float32)
            out.append(v / np.linalg.norm(v))
        return out


def _store(rows):
    path = Path(os.environ["SEMANTIC_DB"])
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE facts (fact_id INTEGER PRIMARY KEY, content TEXT, tags TEXT, trust_score REAL)")
    con.executemany("INSERT INTO facts VALUES (?, ?, ?, 0.5)", rows)
    con.commit()
    con.close()


def _reset():
    server.STATE.update(model=FakeModel(), vecs={}, hashes={}, ready=True)


def test_sync_indexes_in_batches_until_nothing_remains():
    _reset()
    _store([(i, f"fact {i}", "") for i in range(1, 6)])
    facts, embedded, remaining = server.sync(2)
    assert (len(facts), embedded, remaining) == (5, 2, 3)
    assert server.sync(2)[1:] == (2, 1)
    assert server.sync(2)[1:] == (1, 0)
    assert server.sync(2)[1:] == (0, 0)  # nothing new: nothing embedded
    assert len(server.STATE["model"].encoded) == 5 and len(server.STATE["vecs"]) == 5


def test_sync_reembeds_a_changed_fact_and_drops_a_deleted_one():
    _reset()
    _store([(1, "a", ""), (2, "b", "")])
    server.sync()
    _store([(1, "a changed", "")])
    facts, embedded, remaining = server.sync()
    assert (len(facts), embedded, remaining) == (1, 1, 0)
    assert set(server.STATE["vecs"]) == {1}


def test_a_failed_encode_leaves_the_fact_to_index_again():
    _reset()
    _store([(1, "a", "")])

    class Broken(FakeModel):
        def encode(self, texts, **_):
            raise RuntimeError("out of memory")

    server.STATE["model"] = Broken()
    try:
        server.sync()
    except RuntimeError:
        pass
    server.STATE["model"] = FakeModel()
    assert server.sync()[1:] == (1, 0)  # no hash was recorded for a vector never made


def test_the_cache_goes_where_it_is_told():
    _reset()
    _store([(1, "a", "")])
    server.sync()
    assert (TMP / "cache" / "vectors.npz").is_file()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
