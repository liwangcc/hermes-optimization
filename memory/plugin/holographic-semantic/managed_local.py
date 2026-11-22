"""Deploy a profile-scoped embedding sidecar for one of the pinned models (local_models.py). Setup sends a
synthetic probe only."""
from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Generator
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from .cloud_setup import TEST_TEXT, _NoRedirect
from .local_artifacts import fresh_install_supported, prepare_model, prepare_runtime, runtime_env, runtime_space
from .local_models import DEFAULT, MODELS, LocalModel, cache, find, index_dir, legacy_dir, managed_dir
from .setup_common import message, progress, result, setup_lock

JOB_ID = "semantic-setup-local"
_HOST = "127.0.0.1"
_SERVER = Path(__file__).with_name("managed_server.py")
_LEGACY = Path("services") / "semantic-memory"
_LEGACY_URL = "http://127.0.0.1:8791"  # where the manual sidecar listens
_GIB = 1 << 30


def _root(home: Path) -> Path:
    return home / "services" / "memory-embeddings"


def _store_id(db: Path) -> str:
    return hashlib.sha256(os.path.normcase(str(db.resolve())).encode("utf-8")).hexdigest()


def _port(url: str) -> int | None:
    try:
        parsed = urlsplit(url)
        if (parsed.scheme == "http" and parsed.hostname in (_HOST, "localhost")
                and parsed.path in ("", "/") and not (parsed.query or parsed.fragment or parsed.username is not None)):
            return parsed.port or None
    except ValueError:
        pass
    return None


def _request(url: str, route: str, body: dict | None = None, timeout: float = 1.0) -> dict:
    client = build_opener(_NoRedirect(), ProxyHandler({}))
    request = Request(url.rstrip("/") + route, None if body is None else json.dumps(body).encode(),
                      {"Content-Type": "application/json"})
    with client.open(request, timeout=timeout) as response:
        parsed = json.loads(response.read(262_145))
    return parsed if isinstance(parsed, dict) else {}


def _legacy_owns(port: int, db: Path, home: Path) -> bool:
    """The existing manual service has no store ID in /health. Match its actual listener and script."""
    import psutil

    script = (home / _LEGACY / "server.py").resolve()
    try:
        for hit in psutil.net_connections("tcp4"):
            if hit.status != psutil.CONN_LISTEN or hit.laddr != (_HOST, port) or hit.pid is None:
                continue
            proc = psutil.Process(hit.pid)
            env = proc.environ()
            args = proc.cmdline()[1:]
            cwd = Path(proc.cwd())
            target = str(env.get("SEMANTIC_DB") or script.parent / "memory_store.db")
            return (any((cwd / arg).resolve() == script for arg in args if arg.endswith(".py"))
                    and (cwd / target).resolve() == db.resolve())
    except (OSError, psutil.Error):
        return False
    return False


def _ready(url: str, db: Path, home: Path, model: LocalModel) -> dict:
    """/health of a service at *url* that serves *model* for this store, or {}."""
    port = _port(url)
    if port is None:
        return {}
    try:
        health = _request(url, "/health")
    except (OSError, URLError, ValueError):
        return {}
    if health.get("ok") is not True or health.get("model") != model.id:
        return {}
    owner = health.get("store_id")
    if owner == _store_id(db):
        # a managed service from before /health named its version only ever served the first BGE-M3 pin
        return health if health.get("revision", model.rev) == model.rev else {}
    if owner is None and model.id == DEFAULT and _legacy_owns(port, db, home):
        return health
    return {}


def _check_embedding(url: str, model: LocalModel) -> None:
    """The service embeds, and its vectors have the size the picked model has."""
    try:
        vector = _request(url, "/embed", {"texts": [TEST_TEXT]}, timeout=45)["vectors"][0]
        if (not isinstance(vector, list)
                or not all(type(number) in (float, int) and math.isfinite(number) for number in vector)
                or not any(vector)):
            raise ValueError("invalid vector")
    except (OSError, URLError, KeyError, IndexError, TypeError, ValueError, OverflowError):
        raise ValueError(message(f"The local service did not return a valid {model.label} vector.",
                                 f"本地服务未返回有效的 {model.label} 向量。")) from None
    if len(vector) != model.dim:
        raise ValueError(message(
            f"The local service returns {len(vector)}-dimensional vectors; {model.label} has {model.dim}.",
            f"本地服务返回 {len(vector)} 维向量，{model.label} 应为 {model.dim} 维。"))


def _launch(root: Path, python: Path, weights: Path, db: Path, port: int, model: LocalModel) -> subprocess.Popen:
    env = runtime_env(root)
    env.update(SEMANTIC_DB=str(db), SEMANTIC_MODEL=str(weights), SEMANTIC_PORT=str(port),
               SEMANTIC_CACHE=str(index_dir(root, model)), SEMANTIC_STORE_ID=_store_id(db),
               SEMANTIC_MODEL_ID=model.id, SEMANTIC_MODEL_REV=model.rev, SEMANTIC_DIM=str(model.dim),
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS="4")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    with (root / "service.log").open("ab") as log:
        return subprocess.Popen([str(python), "-I", "-B", "-u", str(_SERVER)], cwd=root, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, env=env, creationflags=flags)


def _wait_ready(proc: subprocess.Popen, url: str, db: Path, home: Path, model: LocalModel) -> dict:
    until = time.monotonic() + 150
    while proc.poll() is None and time.monotonic() < until:
        if health := _ready(url, db, home, model):
            return health
        time.sleep(0.5)
    raise ValueError(message(f"{model.label} could not start. Details: {_root(home) / 'service.log'}",
                             f"{model.label} 无法启动。详见 {_root(home) / 'service.log'}"))


def _stop_started(proc: subprocess.Popen) -> None:
    import psutil

    try:
        own = psutil.Process(proc.pid)
        for child in reversed(own.children(recursive=True)):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                continue
        proc.terminate()
    except psutil.NoSuchProcess:
        pass


def _stop_replaced(receipt: dict, keep: str) -> None:
    """Stop the managed service a new connection replaces: two models must not stay loaded. Only a listener on the
    receipt's own port that runs this plugin's server; a manual sidecar is never touched."""
    import psutil

    url, owner = receipt.get("url"), receipt.get("store_id")
    port = _port(url) if isinstance(url, str) and url != keep else None
    if port is None or not isinstance(owner, str):
        return
    try:
        if _request(url, "/health").get("store_id") != owner:
            return  # the port went to something else since: not ours to stop
        for hit in psutil.net_connections("tcp4"):
            if hit.status != psutil.CONN_LISTEN or hit.laddr != (_HOST, port) or hit.pid is None:
                continue
            proc = psutil.Process(hit.pid)
            if any(Path(arg) == _SERVER for arg in proc.cmdline()[1:]):
                proc.terminate()
            return
    except (OSError, ValueError, psutil.Error):
        return


def _receipt(root: Path) -> dict:
    try:
        raw = json.loads((root / "service.json").read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def deployed(home: str, url: str) -> LocalModel | None:
    """The model setup verified at *url* for this profile, if recorded."""
    receipt = _receipt(_root(Path(home)))
    if receipt.get("url") != url:
        return None
    model = find(str(receipt.get("model_id") or DEFAULT))  # a receipt from before the choice: BGE-M3
    return model if model is not None and receipt.get("rev", model.rev) == model.rev else None


def expected_store(home: str, url: str) -> str | None:
    receipt = _receipt(_root(Path(home)))
    identity = receipt.get("store_id")
    return identity if receipt.get("url") == url and isinstance(identity, str) else None


def responds_for_store(url: str, identity: str, *, timeout: float = 0.2) -> bool:
    if _port(url) is None:
        return False
    try:
        health = _request(url, "/health", timeout=timeout)
        return health.get("ok") is True and health.get("store_id") == identity
    except (OSError, ValueError):
        return False


def _write_receipt(root: Path, receipt: dict) -> None:
    from utils import atomic_json_write

    atomic_json_write(root / "service.json", receipt, mode=0o600)


def _occupied(port: int) -> bool:
    with socket.socket() as client:
        client.settimeout(0.1)
        return client.connect_ex((_HOST, port)) == 0


def _free_port() -> int:
    with socket.socket() as client:
        client.bind((_HOST, 0))
        return client.getsockname()[1]


def wake(home: str, db: Path | None, url: str) -> None:
    """Start a previously deployed managed service after reboot as a background child."""
    if db is None or not fresh_install_supported() or (port := _port(url)) is None:
        return
    home_path = Path(home).resolve()
    root = _root(home_path)
    receipt = _receipt(root)
    if receipt.get("url") != url or receipt.get("store_id") != _store_id(db) or _occupied(port):
        return
    runtime = receipt.get("runtime")
    model_kind = receipt.get("model")
    model = deployed(home, url)  # None once an update pinned another version: deploy again
    if (not isinstance(runtime, str) or not runtime.startswith("runtime-")
            or len(runtime) != len("runtime-") + 12 or not all(c in "0123456789abcdef" for c in runtime[8:])
            or model_kind not in ("legacy", "managed") or model is None):
        return
    python = root / runtime / "Scripts" / "python.exe"
    weights = legacy_dir(home_path, model) if model_kind == "legacy" else managed_dir(root, model)
    if weights is None or not python.is_file() or not (weights / "config.json").is_file():
        return
    try:
        with setup_lock(home):
            if _occupied(port):
                return
            # Serialize the brief interval between spawn and bind across session initializers.
            record = _receipt(root)
            if record.get("url") != url or 0 <= time.monotonic() - float(record.get("spawned", -60)) < 3:
                return
            _launch(root, python, weights, db, port, model)
            _write_receipt(root, {**receipt, "spawned": time.monotonic()})
    except (OSError, ValueError, TypeError):
        return  # the next turn can still use lexical recall


def _size(count: int) -> str:
    return f"{count / _GIB:.2f} GiB" if count >= _GIB else f"{-(-count // (1 << 20))} MiB"


def _option(model: LocalModel, home: Path, root: Path, runtime: int) -> dict:
    """One model as a choice: what its weights download, what is cached and where, and the disk space still needed."""
    path, held = cache(home, root, model)
    needed = model.size - held + runtime
    extra = f" (includes {_size(runtime)} for the runtime)" if runtime else ""
    extra_zh = f"（含运行环境 {_size(runtime)}）" if runtime else ""
    return {
        "id": model.id, "label": model.label,
        "description": "\n".join((f"{model.note} {model.dim}-dimensional vectors.",
                                  f"Weights download: {_size(model.size)}. Cached: {_size(held)}.",
                                  f"Cache path: {path}",
                                  f"Estimated disk space needed: {_size(needed)}{extra}.")),
        "translations": {"zh": {"description": "\n".join((
            f"{model.note_zh}向量 {model.dim} 维。",
            f"权重下载大小 {_size(model.size)}，已缓存 {_size(held)}。",
            f"缓存路径 {path}",
            f"预计所需磁盘空间 {_size(needed)}{extra_zh}。"))}},
    }


def action(home: str, db: Path | None, url: str) -> dict:
    ready = db is not None and (fresh_install_supported() or _port(url) is not None)
    profile = Path(home).resolve()
    root = _root(profile)
    current = deployed(home, url)
    status = "" if ready else "Local setup needs a profile-wide fact store and a supported local runtime."
    zh_status = "" if ready else "本地部署需要配置级事实库和受支持的本地运行环境。"
    if ready and current is not None:
        status, zh_status = f"Deployed: {current.label}.", f"当前部署：{current.label}。"
    runtime = runtime_space(root)
    return {
        "id": JOB_ID, "label": "Local model", "ready": ready, "status": status,
        "description": "Pick a model, then deploy it. A running BGE-M3 sidecar (CUDA included) is reused; otherwise "
                       "the weights are downloaded, verified and served on this machine.",
        "options": [_option(model, profile, root, runtime) for model in MODELS],
        "selected": current.id if current is not None else DEFAULT,
        "translations": {"zh": {"label": "本地模型", "status": zh_status,
            "description": "选择模型后一键部署。已运行的 BGE-M3 侧车（含 CUDA）会直接复用，否则下载并校验所选模型的权重，再启动本机服务。"}},
    }


def _device(health: dict) -> str:
    return "CUDA" if health.get("device") == "cuda" else "CPU"


def deploy(home: str, db: Path, address: str, model: LocalModel, *, save) -> Generator[dict, None, None]:
    profile = Path(home).resolve()
    root = _root(profile)
    with setup_lock(home):
        yield progress(f"Checking the local {model.label} service…", f"正在检查本地 {model.label} 服务…")
        previous = _receipt(root)
        previous_id = (previous.get("model_id") or DEFAULT) if previous else None
        same_model = previous_id == model.id
        values: dict[str, bool | float] = {"semantic_enabled": True, "embeddings": False}
        if not same_model:
            values["semantic_tau"] = model.recommended_tau

        def connect(receipt: dict) -> None:
            _write_receipt(root, {**receipt, "model_id": model.id, "rev": model.rev, "dim": model.dim})
            try:
                save({**values, "semantic_url": receipt["url"]}, home)
            except Exception:
                _write_receipt(root, previous)
                raise

        # the configured address first, then the manual sidecar's own: switching back to BGE-M3 finds it again
        for candidate in dict.fromkeys((address, _LEGACY_URL)):
            if health := _ready(candidate, db, profile, model):
                _check_embedding(candidate, model)
                owner = health.get("store_id")
                same_service = same_model and previous.get("url") == candidate and previous.get("store_id") == owner
                receipt = previous if same_service else {}
                connect({**receipt, "url": candidate, "store_id": owner})
                _stop_replaced(previous, candidate)
                device = _device(health)
                yield result(f"Connected to the existing {model.label} service ({device}). New sessions can use it.",
                             f"已连接现有 {model.label} 侧车（{device}）。新会话将使用此模型。")
                return
        yield progress("Preparing the local runtime…", "正在准备本地运行环境…")
        python = prepare_runtime(root)
        weights = yield from prepare_model(profile, root, model)
        port = _free_port()
        address = f"http://{_HOST}:{port}"
        yield progress(f"Starting and testing {model.label}…", f"正在启动并试连 {model.label}…")
        proc = _launch(root, python, weights, db, port, model)
        try:
            health = _wait_ready(proc, address, db, profile, model)
            _check_embedding(address, model)
            receipt = {"url": address, "store_id": _store_id(db), "runtime": python.parents[1].name,
                       "model": "managed" if weights.parent == root else "legacy"}
            connect(receipt)
        except Exception:
            _stop_started(proc)
            raise
        _stop_replaced(previous, address)
        device = _device(health)
        yield result(f"{model.label} is ready on {device}. New sessions can use it.",
                     f"{model.label} 已就绪（{device}）。新会话将使用此模型。")
