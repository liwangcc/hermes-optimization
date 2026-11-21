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
_BATCH_TIMEOUT_S = 600.0  # 64 facts through the largest model on a CPU
_DESCRIPTION = ("The local sidecar embeds every stored fact it has no current vector for, so semantic recall covers "
                "the facts stored before it ran. Nothing leaves this machine.")


def _call(url: str, path: str, body: Optional[dict] = None, timeout: float = _PROBE_TIMEOUT_S) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # localhost never goes through a proxy
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read())


def _action_status(ready: bool, status: str, chinese_status: str) -> dict[str, Any]:
    return {
        "id": JOB_ID, "label": "Index facts for semantic recall", "description": _DESCRIPTION,
        "ready": ready, "status": status,
        "translations": {"zh": {
            "label": "为已有事实建立语义索引",
            "description": "用本机模型为尚未覆盖的事实生成向量，数据留在本机。",
            "status": chinese_status,
        }},
    }


def action(url: str, enabled: bool, facts: Optional[int], store_id: Optional[str] = None) -> dict[str, Any]:
    """The job as the Desktop lists it. *facts*: what this profile's store holds (None: no single store file)."""
    try:
        health = _call(url, "/health")
    except (OSError, ValueError):
        return _action_status(False,
                              f"The sidecar at {url} is not answering. Start it (memory/sidecar), then open this page again.",
                              f"侧车 {url} 无响应。启动侧车后重新打开此页。")
    if not health.get("ok"):
        error = health.get("error")
        return _action_status(False, f"The sidecar answers but its model is not loaded: {error or 'still loading'}.",
                              f"侧车已连接，模型尚未就绪（{error or '正在加载'}）。")
    if store_id is not None and health.get("store_id") != store_id:
        return _action_status(False, "The local endpoint no longer belongs to this profile. Deploy it again.",
                              "本地端口已由其他服务占用，请重新部署本地模型。")
    indexed, total = health.get("facts_indexed"), health.get("facts")
    if facts is not None and total is not None and total != facts:
        return _action_status(
            False,
            f"The sidecar reads a store of {total} facts; this profile holds {facts}. Point its "
            "SEMANTIC_DB at this profile's memory_store.db.",
            f"侧车读到 {total} 条事实，当前配置有 {facts} 条。请将侧车的 SEMANTIC_DB 指向此配置的 memory_store.db。",
        )
    model, device = health.get("model"), health.get("device")
    off = "" if enabled else " Semantic recall is off: turn it on above to use the index."
    off_zh = "" if enabled else " 在上方开启语义召回后即可使用索引。"
    return _action_status(True, f"{indexed} of {total} facts indexed ({model} on {device}).{off}",
                          f"已索引 {indexed}/{total} 条事实（{model}，{device}）。{off_zh}")


def step(url: str, run: dict[str, int]) -> dict[str, Any]:
    """One batch. *run* carries this run's count from one step to the next."""
    out = _call(url, "/sync", {"limit": _BATCH}, timeout=_BATCH_TIMEOUT_S)
    run["embedded"] = run.get("embedded", 0) + int(out.get("embedded") or 0)
    total, remaining = int(out.get("facts") or 0), int(out.get("remaining") or 0)
    indexed = total - remaining
    status = f"{indexed} of {total} facts indexed"
    zh = {"status": f"已索引 {indexed}/{total} 条事实"}
    if remaining == 0:
        embedded = run["embedded"]
        zh["result"] = f"全部 {total} 条事实已建立索引，本次新增 {embedded} 条。"
        return {"done": True, "status": status, "result": f"All {total} facts are indexed; this run embedded {embedded}.",
                "translations": {"zh": zh}}
    return {"done": False, "status": status, "translations": {"zh": zh}}
