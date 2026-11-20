"""Verify the result of the real-sidecar demo without letting a read trigger implicit backfill."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path)
    parser.add_argument("cache", type=Path)
    args = parser.parse_args()
    with closing(sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        expected = {
            str(fid): hashlib.sha256(((text or "") + "\x00" + (tags or "")).encode("utf-8")).hexdigest()[:16]
            for fid, text, tags in conn.execute("SELECT fact_id, content, tags FROM facts")
        }
    if len(expected) != 12:
        raise ValueError(f"expected 12 synthetic facts, got {len(expected)}")
    hashes = json.loads((args.cache / "hashes.json").read_text(encoding="utf-8"))
    if hashes != expected:
        raise ValueError("cached hashes do not match the current synthetic facts")
    vector_file = args.cache / "vectors.npz"
    with np.load(vector_file, allow_pickle=False) as vectors:
        if set(vectors.files) != set(expected):
            raise ValueError("cached vector IDs do not match the current synthetic facts")
        for fid in vectors.files:
            vector = vectors[fid]
            if (vector.shape != (1024,) or vector.dtype != np.float32 or not np.isfinite(vector).all()
                    or not np.isclose(np.linalg.norm(vector), 1, atol=0.005)):
                raise ValueError(f"bad BGE-M3 vector for synthetic fact {fid}")
    print(json.dumps({"facts": len(expected), "vectors": len(hashes), "dimensions": 1024,
                      "vector_file_sha256": hashlib.sha256(vector_file.read_bytes()).hexdigest(),
                      "runtime": {name: metadata.version(name) for name in (
                          "torch", "sentence-transformers", "transformers", "numpy")}}))


if __name__ == "__main__":
    main()
