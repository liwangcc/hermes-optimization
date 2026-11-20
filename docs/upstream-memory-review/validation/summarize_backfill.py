"""Extract only non-sensitive aggregates from the supplied Windows embedding backfill evidence zip."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def summarize(source):
    with zipfile.ZipFile(source) as z:
        if z.testzip() is not None:
            raise ValueError("damaged evidence zip")
        manifest = json.loads(z.read("manifest.json"))
        measurements = json.loads(z.read("serial-results.json"))
        qwen = json.loads(z.read("qwen3-initial.json"))

        def submitted(key):
            rows = [json.loads(line) for line in z.read(f"requests/{key}.jsonl").splitlines()]
            return [h for row in rows if row["stage"] == "backfill" and row["status"] == 200
                    for h in row["input_hashes"]]

        first = submitted("qwen3-06b-initial")
        remaining = submitted("qwen3-06b")
    total = manifest[0]["seed_facts"]
    assert all(m["seed_facts"] == total and m["trigger"] == manifest[0]["trigger"] for m in manifest)
    assert len(first) == len(set(first)) == qwen["active_vectors"] == 28
    assert len(remaining) == len(set(remaining)) == qwen["remaining"] == 12
    assert not set(first).intersection(remaining) and len(first) + len(remaining) == total == 40
    assert len(measurements) == len({r["model"] for r in measurements}) == 5
    rows = []
    for m in measurements:
        assert m["index_pass"] and m["vectors"] == total and m["facts_unchanged"]
        assert sum(p["semantic_only"] for p in m["recall"]) == m["semantic_probes"]
        rows.append({k: m[k] for k in ("model", "dimensions", "vectors", "semantic_probes", "backfill_s", "backfill_sent")})
    return {
        "source_zip_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        **{k: manifest[0][k] for k in ("core_base", "upstream_plugin", "device", "trigger", "seed_facts")},
        "semantic_probe_total": len(measurements[0]["recall"]), "models": rows,
        "qwen3_continuation": {"initial": len(first), "submitted_after_restart": len(remaining), "overlap": 0},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.zip), indent=2))
