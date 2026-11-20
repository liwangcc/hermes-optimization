"""Test bootstrap: the tool's modules on the path, the vendored snapshot, and no network for any test.

numpy and pytest only. Tests that run the plugin's code skip when the snapshot is not checked out.
"""
import os
import socket
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
EVAL = HERE.parent / "eval"
sys.path.insert(0, str(HERE))

import calib_vendor  # noqa: E402

EMBED_ENV = ("EMBED_URL", "EMBED_MODEL", "EMBED_KEY_ENV", "EMBED_DIMENSIONS")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any attempt to open a connection fails the test that made it; no endpoint comes from the caller's shell."""
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    for name in EMBED_ENV:
        monkeypatch.delenv(name, raising=False)


def child_env(hash_seed: str) -> dict:
    """The environment for a child interpreter: what this one sees (started with -E: no PYTHON* variables), a fixed
    hash seed, no endpoint."""
    env = dict(os.environ)
    if sys.flags.ignore_environment:
        env = {k: x for k, x in env.items() if not k.upper().startswith("PYTHON")}
    for name in EMBED_ENV:
        env.pop(name, None)
    env.update(PYTHONHASHSEED=hash_seed, PYTHONIOENCODING="utf-8")
    return env


@pytest.fixture(scope="session")
def v():
    if not (calib_vendor.DEFAULT_SRC / "embeddings.py").is_file():
        pytest.skip("the vendored plugin snapshot is not checked out (see README, Setup)")
    return calib_vendor.load()


MANIFEST = {"recall_margin": 1.0}


def rows_of(points: dict) -> list[dict]:
    """{(rule, value): {qid: keys}} -> rows, in the order given."""
    return [{"rule": rule, "value": value, "qid": qid, "keys": keys}
            for (rule, value), point in points.items() for qid, keys in point.items()]
