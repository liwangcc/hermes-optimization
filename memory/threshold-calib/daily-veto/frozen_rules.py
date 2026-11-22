"""Frozen daily-shape recall rules (chosen on dev only; see PLAN-FREEZE.md and its addendum).

All rules use only what the daily plugin already computes per message: the base block and which of its facts came
from the lexical stream, and the one bge-m3 query vector's cosines to the facts' daily-view vectors
(content + " " + tags). Non-askable messages (no query vector) keep daily's block.

Components
- semantic step: daily's append; on a silent base block (nothing lexical or entity) optionally
  S: withdraw the append when the closest fact does not stand out: standout = z(cos among trusted facts)
     - sqrt(2 ln N) < Z_SILENT;
  R: also append a closest fact with RESCUE_TAU <= cos < TAU when standout >= Z_RESCUE and it leads the runner-up
     by >= LEAD.
- veto V: drop a shown fact whose cosine is below FLOOR, or more than GAP below the best fact of the base block
  (before the append); the lexical rank-1 fact is exempt from the gap test (not the floor). The semantic append is
  the global top-1, so the veto never drops it.
- E: an entity-stream fact also needs cos >= ENTITY_TAU while the lexical stream kept at least one fact.
"""
from __future__ import annotations

import numpy as np

import daily_eval as d

TAU = d.TAU          # 0.55, shipped
Z_SILENT = -0.5
RESCUE_TAU = 0.45
Z_RESCUE = 1.0
LEAD = 0.02
GAP = 0.20
FLOOR = 0.35
ENTITY_TAU = 0.55


def standout(fx, i, fid):
    c = fx.cos(i)
    t = c[fx.trusted]
    n, sd = len(t), float(t.std())
    if n < 2 or sd == 0:
        return None
    return (float(c[fx.pos[fid]]) - float(t.mean())) / sd - float(np.sqrt(2 * np.log(n)))


def _fits(fx, i, fid):
    try:
        return fx.fits(i, fid)
    except KeyError:
        return False


def semantic(fx, i, silent_standout, rescue):
    block = d.base(fx, i)
    ids, cs = fx.ranked(i)
    if not ids or len(block) >= d.CAP:
        return block
    top, c = ids[0], cs[0]
    if block:  # non-silent: exactly daily
        return block + [top] if top not in block and c >= TAU and _fits(fx, i, top) else block
    z = standout(fx, i, top) if (silent_standout or rescue) else None
    ok = c >= TAU
    if silent_standout and ok and z is not None and z < Z_SILENT:
        ok = False
    if rescue and not ok and c >= RESCUE_TAU and z is not None and z >= Z_RESCUE \
            and c - (cs[1] if len(cs) > 1 else 0.0) >= LEAD and (not silent_standout or z >= Z_SILENT):
        ok = True
    return [top] if ok and _fits(fx, i, top) else block


def veto(fx, i, block, entity_bar):
    base = d.base(fx, i)
    c = fx.cos(i)
    if c is None or not base:
        return block
    q = fx.q[i]
    cos = {f: float(c[fx.pos[f]]) for f in block}
    top = max(cos[f] for f in base)
    rank1 = q["fresh"][:1]
    barred = set(q["entity"]) if entity_bar and q["fresh"] else set()
    return [f for f in block
            if cos[f] >= FLOOR and (top - cos[f] <= GAP or f in rank1)
            and (f not in barred or cos[f] >= ENTITY_TAU)]


def make(silent_standout=True, rescue=False, entity_bar=False):
    def rule(fx, i):
        if not fx.q[i]["askable"]:
            return d.daily(fx, i)
        return veto(fx, i, semantic(fx, i, silent_standout, rescue), entity_bar)
    return rule


RULES = {
    "P1": make(True, False, False),
    "P2": make(True, True, False),
    "P1E": make(True, False, True),
    "P2E": make(True, True, True),
}
PRIMARY = ("P1", "P2")
