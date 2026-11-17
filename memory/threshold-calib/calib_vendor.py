"""The plugin's own admission code, loaded read-only: every rule this tool sweeps runs on it.

Nothing here re-implements a formula. The z-score rules call the vendored ``embeddings.Meaning.standout``; the
experimental floor is a subclass whose ``standout`` is the one changed line of KG-1's ``admission_floor.diff``; the
walk over the ranked facts is ``Retriever.by_meaning`` (retrieval.py:708-714) without the SQL, followed by prefetch's
own cut (__init__.py:1362-1371). The plugin's
``__init__`` (it needs Hermes core) never runs: only the modules admission needs are imported, from the snapshot as
it is, and no bytecode is written into it.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import tomllib
import types
from pathlib import Path

DEFAULT_SRC = Path(__file__).resolve().parents[2] / "vendor" / "holographic-0.27.0"
_PKG = "holographic_calib_vendor"

# rule -> what its value is. zbar and zbar_floor are upstream's own knobs (light path); floor is the experimental
# admission mode (heavy path), never a default.
RULES = {
    "zbar": "RECALL_MARGIN: z >= sqrt(2 ln N) + value (upstream admission, value 1.0 is the default)",
    "zbar_floor": "embedding_min_score: cosine >= value AND the default z_bar (upstream optional floor, unset by default)",
    "floor": "experimental: cosine >= value alone admits, z_bar is not consulted (KG-1 admission_floor.diff)",
}


def load(src: Path | str = DEFAULT_SRC) -> types.SimpleNamespace:
    """embeddings, screen and tools/mcnemar_gate of the snapshot at *src*, plus the floor subclass."""
    src = Path(src).resolve()
    if not (src / "embeddings.py").is_file() or not (src / "tools" / "mcnemar_gate.py").is_file():
        raise SystemExit("no plugin snapshot at --plugin-src (see README, Setup)")
    pkg = sys.modules.get(_PKG)
    if pkg is None:
        pkg = types.ModuleType(_PKG)
        pkg.__path__ = [str(src)]  # a package without running its __init__
        sys.modules[_PKG] = pkg
    elif pkg.__path__ != [str(src)]:
        raise SystemExit("another plugin snapshot is already loaded in this process")
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # the snapshot is read-only: no __pycache__ appears in it
    try:
        emb = importlib.import_module(f"{_PKG}.embeddings")
        screen = importlib.import_module(f"{_PKG}.screen")
        gate = sys.modules.get(f"{_PKG}_mcnemar_gate")
        if gate is None:
            spec = importlib.util.spec_from_file_location(f"{_PKG}_mcnemar_gate", src / "tools" / "mcnemar_gate.py")
            gate = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gate)
            sys.modules[spec.name] = gate
    finally:
        sys.dont_write_bytecode = saved

    class FloorMeaning(emb.Meaning):
        """admission_floor.diff as a subclass: the cosine alone admits, z_bar is not consulted."""

        __slots__ = ("floor",)

        def standout(self, fact_id, margin, min_score):
            s = self.sims.get(fact_id)
            return s is not None and s >= self.floor

    with open(src / "pyproject.toml", "rb") as fh:
        version = tomllib.load(fh)["project"]["version"]
    return types.SimpleNamespace(emb=emb, screen=screen, mcnemar_gate=gate, FloorMeaning=FloorMeaning,
                                 version=version)


def standout_args(v, rule: str, value: float) -> tuple[float, float | None]:
    """(margin, min_score) that Meaning.standout gets under *rule* at *value*."""
    if rule == "zbar":
        return value, None
    if rule in ("zbar_floor", "floor"):  # floor ignores both; its value lives on the FloorMeaning
        return v.emb.RECALL_MARGIN, value if rule == "zbar_floor" else None
    raise SystemExit(f"unknown rule {rule!r}: the rules are {', '.join(RULES)}")


def walk(meaning, ranked, margin: float, min_score: float | None, keep: int, eligible, recallable=None) -> list[int]:
    """The facts admitted on meaning, closest first, in prefetch's two steps: Retriever.by_meaning's loop over
    *eligible* facts (trust) with limit embedding_prefetch_facts + 3 (__init__.py:1363-1366), then the first *keep* of
    those that are *recallable* (_recallable, __init__.py:1367-1368). *ranked* is meaning.ranked(), computed once."""
    picked = []
    for fact_id, _ in ranked:  # standout falls with similarity: the first miss ends the list
        if not meaning.standout(fact_id, margin, min_score):
            break
        if fact_id in eligible:
            picked.append(fact_id)
            if len(picked) >= keep + 3:
                break
    return [f for f in picked if recallable is None or f in recallable][:keep]
