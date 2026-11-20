"""The committed dry run is reproduced byte for byte under two hash seeds, and the snapshot is never written to."""
import hashlib
import subprocess
import sys

import pytest

import calib_vendor
from conftest import HERE, child_env

DRY = {"auto": ["--stub", "--facts", "../eval/facts.json"],
       "labelled": ["--stub", "--facts", "../eval/facts.json", "--queries", "../eval/queries.json"]}


def _run(out, args, hash_seed):
    done = subprocess.run([sys.executable, "calib_run.py", *args, "--out", str(out)], cwd=HERE,
                          env=child_env(hash_seed), capture_output=True, text=True, encoding="utf-8", check=True)
    return done.stdout, {p.name: p.read_bytes() for p in sorted(out.iterdir())}


@pytest.mark.parametrize("name", DRY)
def test_two_hash_seeds_give_the_same_bytes_and_they_are_the_committed_dry_run(v, tmp_path, name):
    out_a, files_a = _run(tmp_path / "a", DRY[name], "0")
    _, files_b = _run(tmp_path / "b", DRY[name], "4242")
    assert files_a == files_b
    committed = {p.name: p.read_bytes() for p in sorted((HERE / "dryrun" / name).iterdir())}
    assert files_a == committed
    digest = hashlib.sha256(files_a["summary.json"]).hexdigest()
    assert f"summary sha256 {digest}" in out_a and digest in files_a["report.md"].decode("utf-8")


def test_loading_the_snapshot_writes_nothing_into_it(v):
    def listing():
        return sorted((str(p.relative_to(calib_vendor.DEFAULT_SRC)), p.stat().st_mtime_ns)
                      for p in calib_vendor.DEFAULT_SRC.rglob("*"))

    before = listing()
    subprocess.run([sys.executable, "-c", "import calib_vendor; calib_vendor.load()"], cwd=HERE,
                   env=child_env("0"), check=True)
    assert listing() == before
