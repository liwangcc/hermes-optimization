"""Self-check of the sidecar's index sync, with a fake model (the real one needs bge-m3 on disk).

Run: python memory/sidecar/test_sync.py   (needs numpy)
"""
import hashlib
import importlib.util
import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock, patch

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


def test_judge_reads_the_block_and_the_closest_facts_as_text_with_keywords():
    _reset()
    _store([(1, "a", "keywords: one, two"), (2, "b", "mine\nkeywords: three"), (3, "c", "mine")])
    server.sync()
    read = []

    def fake(query, docs):
        read.extend(docs)
        return {"strict": [float(len(d)) for d in docs], "generic": [0.0] * len(docs)}

    with patch.object(server, "judge_scores", fake):
        rows = server.rank_and_judge("q", [3], 1, 0.3)[0]  # the block's fact #3, then the one closest fact
        assert [r["fact_id"] for r in rows][0] == 3 and len(rows) in (1, 2)  # the closest may be #3 itself
        assert sorted(r["rank"] for r in server.rank_and_judge("q", [1, 2, 3], 0, 0.3)[0]) == [0, 1, 2]
        assert {"a\nKeywords: one, two", "b\nKeywords: three", "c"} == set(read)  # user tags are not keywords
        assert all(set(r) == {"fact_id", "cos", "rank", "strict", "generic"} for r in rows)
        assert server.rank_and_judge("q", [99], 0, 0.3)[0] == []  # an id the store does not hold is not judged


def test_judge_skips_stale_vectors_until_the_background_job_catches_up():
    _reset()
    _store([(1, "old", ""), (2, "deleted", ""), (4, "unchanged", "")])
    server.sync()
    server.STATE["model"].encoded.clear()
    _store([(1, "changed", ""), (3, "new", ""), (4, "unchanged", "")])

    with patch.object(server, "judge_scores", return_value={"strict": [1.0] * 3}) as judge:
        rows, total = server.rank_and_judge("q", [1, 3], 10, 0.3)
    assert total == 3 and [r["fact_id"] for r in rows] == [1, 3, 4]
    assert all(r["cos"] is None and r["rank"] is None for r in rows[:2])
    assert rows[2]["rank"] == 0
    judge.assert_called_once_with("q", ["changed", "new", "unchanged"])
    assert server.STATE["model"].encoded == ["q"]

    stop = Mock()
    stop.wait.side_effect = [False, True]
    server.index_in_background(stop)
    assert server.STATE["model"].encoded == ["q", "changed ", "new "]
    assert set(server.STATE["vecs"]) == {1, 3, 4}
    with patch.object(server, "judge_scores", return_value={"strict": [1.0] * 3}):
        rows, _ = server.rank_and_judge("q", [], 10, 0.3)
    assert [row["rank"] for row in rows] == [0, 1, 2]


def test_background_index_yields_to_the_model_and_uses_small_batches():
    _reset()
    _store([(i, f"fact {i}", "") for i in range(6)])
    attempts = []
    with server.LOCK:
        attempt = threading.Thread(target=lambda: attempts.append(server.sync(server._INDEX_BATCH, background=True)))
        attempt.start()
        attempt.join(timeout=2)
        assert not attempt.is_alive()
    assert attempts[0][1:] == (0, 6)
    stop = Mock()
    stop.wait.side_effect = [False, True]
    server.index_in_background(stop)
    assert len(server.STATE["model"].encoded) == 4


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
