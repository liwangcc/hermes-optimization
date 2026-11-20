"""The Desktop job "Index facts for semantic recall": the local sidecar embeds every stored fact it holds no current
vector for, in batches, and the job says where it stands. The sidecar (memory/sidecar) owns the model and the index.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Optional

JOB_ID = "semantic-index"
_BATCH = 64
_PROBE_TIMEOUT_S = 1.0  # the job list is read when the settings page opens
_BATCH_TIMEOUT_S = 600.0  # 64 facts through bge-m3 on a CPU
_DESCRIPTION = ("The local sidecar embeds every stored fact it has no current vector for, so semantic recall covers "
                "the facts stored before it ran. Nothing leaves this machine.")


def _call(url: str, path: str, body: Optional[dict] = None, timeout: float = _PROBE_TIMEOUT_S) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # localhost never goes through a proxy
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read())


def action(url: str, enabled: bool, facts: Optional[int]) -> dict[str, Any]:
    """The job as the Desktop lists it. *facts*: what this profile's store holds (None: no single store file)."""
    job = {"id": JOB_ID, "label": "Index facts for semantic recall", "description": _DESCRIPTION}
    try:
        health = _call(url, "/health")
    except (OSError, ValueError):
        return {**job, "ready": False,
                "status": f"The sidecar at {url} is not answering. Start it (memory/sidecar), then open this page again."}
    if not health.get("ok"):
        return {**job, "ready": False,
                "status": f"The sidecar answers but its model is not loaded: {health.get('error') or 'still loading'}."}
    indexed, total = health.get("facts_indexed"), health.get("facts")
    if facts is not None and total is not None and total != facts:
        return {**job, "ready": False,
                "status": f"The sidecar reads a store of {total} facts; this profile holds {facts}. Point its "
                          "SEMANTIC_DB at this profile's memory_store.db."}
    off = "" if enabled else " Semantic recall is off: turn it on above to use the index."
    return {**job, "ready": True,
            "status": f"{indexed} of {total} facts indexed ({health.get('model')} on {health.get('device')}).{off}"}


def step(url: str, run: dict[str, int]) -> dict[str, Any]:
    """One batch. *run* carries this run's count from one step to the next."""
    out = _call(url, "/sync", {"limit": _BATCH}, timeout=_BATCH_TIMEOUT_S)
    run["embedded"] = run.get("embedded", 0) + int(out.get("embedded") or 0)
    total, remaining = int(out.get("facts") or 0), int(out.get("remaining") or 0)
    status = f"{total - remaining} of {total} facts indexed"
    if remaining == 0:
        return {"done": True, "status": status,
                "result": f"All {total} facts are indexed; this run embedded {run['embedded']}."}
    return {"done": False, "status": status}
