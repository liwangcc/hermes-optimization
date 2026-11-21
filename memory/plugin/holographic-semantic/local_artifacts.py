"""Fetch the pinned Windows embedding runtime and a pinned model (local_models.py) into the owning profile."""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Generator
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .local_models import LocalModel, legacy_dir, managed_dir
from .setup_common import message, progress

_LOCK = Path(__file__).with_name("local-runtime.txt")
_RUNTIME_MARKER = "setup-ready"
_MIB = 1024 * 1024
_MIN_INSTALL_SPACE = 1400 * _MIB
_OS_ENV = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "USERNAME", "USERPROFILE",
           "APPDATA", "LOCALAPPDATA", "SYSTEMDRIVE"}
_DOWNLOAD_ENV = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"}


class _HttpsRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def runtime_env(root: Path, *, download: bool = False) -> dict[str, str]:
    allowed = _OS_ENV | _DOWNLOAD_ENV if download else _OS_ENV
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(HF_HOME=str(root / "hf-cache"), TORCH_HOME=str(root / "torch-cache"),
               TORCHINDUCTOR_CACHE_DIR=str(root / "torch-inductor"))
    return env


def fresh_install_supported() -> bool:
    return (sys.platform == "win32" and sys.version_info[:2] == (3, 14)
            and platform.machine().lower() in ("amd64", "x86_64"))


def _matches(path: Path, size: int, expected: str) -> bool:
    try:
        if not path.is_file() or path.stat().st_size != size:
            return False
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest() == expected
    except OSError:
        return False


def _download(path: Path, base: str, name: str, size: int, expected: str) -> Generator[dict, None, None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".partial")
    digest = hashlib.sha256()
    received = 0
    shown = 0
    deadline = time.monotonic() + 1800
    try:
        request = Request(f"{base}/{name}", headers={"User-Agent": "Hermes-Memory-Embeddings/1"})
        with build_opener(_HttpsRedirect()).open(request, timeout=40) as response, part.open("wb") as out:
            while block := response.read(_MIB):
                received += len(block)
                if received > size or time.monotonic() > deadline:
                    raise ValueError(message("The model download exceeded its limit.", "模型下载超出预期大小或时限。"))
                out.write(block)
                digest.update(block)
                if received - shown >= 32 * _MIB:
                    shown = received
                    done, total = received // _MIB, size // _MIB
                    yield progress(f"Downloading {name} ({done}/{total} MiB)…", f"正在下载 {name}（{done}/{total} MiB）…")
        if received != size or digest.hexdigest() != expected:
            raise ValueError(message(f"Model checksum did not match for {name}.", f"{name} 的模型校验值不匹配。"))
        part.replace(path)
    except (OSError, URLError) as exc:
        raise ValueError(message(f"Could not download {name}. Check the connection and available disk space.",
                                 f"无法下载 {name}，请检查网络和可用磁盘空间。")) from exc
    finally:
        part.unlink(missing_ok=True)


def prepare_model(home: Path, root: Path, model: LocalModel) -> Generator[dict, None, Path]:
    yield progress(f"Checking for saved {model.label} weights…", f"正在查找并校验已有 {model.label} 权重…")
    legacy = legacy_dir(home, model)
    if legacy is not None and all(_matches(legacy / name, *pin) for name, pin in model.files.items()):
        yield progress(f"Reusing the existing {model.label} weights.", f"复用已有 {model.label} 权重。")
        return legacy

    target = managed_dir(root, model)
    root.mkdir(parents=True, exist_ok=True)
    missing = [(name, pin) for name, pin in model.files.items() if not _matches(target / name, *pin)]
    if shutil.disk_usage(root).free < sum(pin[0] for _, pin in missing) + 64 * _MIB:
        raise ValueError(message(f"Free more disk space for {model.label} and retry.",
                                 f"请为 {model.label} 腾出磁盘空间后重试。"))
    if missing:
        yield progress(f"Downloading and verifying {model.label}…", f"正在下载并校验 {model.label} 权重…")
    for name, pin in missing:
        yield from _download(target / name, model.base, name, *pin)
    return target


def runtime_path(root: Path) -> Path:
    interpreter = f"{Path(sys.base_prefix).resolve()}\n{platform.python_version()}".encode("utf-8")
    identity = hashlib.sha256(_LOCK.read_bytes() + interpreter).hexdigest()[:12]
    return root / f"runtime-{identity}"


def runtime_python(runtime: Path) -> Path:
    return runtime / "Scripts" / "python.exe"


def runtime_ready(runtime: Path) -> bool:
    return (runtime / _RUNTIME_MARKER).is_file() and runtime_python(runtime).is_file()


def runtime_space(root: Path) -> int:
    """Bytes a deployment still needs for the runtime: none once it is installed."""
    return 0 if runtime_ready(runtime_path(root)) else _MIN_INSTALL_SPACE


def prepare_runtime(root: Path) -> Path:
    if not fresh_install_supported():
        raise ValueError(message("First-time local deployment needs Windows x64 with Hermes Python 3.14.",
                                 "首次本地部署需要 Windows x64 和 Hermes Python 3.14。"))
    runtime = runtime_path(root)
    python = runtime_python(runtime)
    if runtime_ready(runtime):
        return python
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < _MIN_INSTALL_SPACE:
        raise ValueError(message("Free more disk space for the local runtime.", "请为本地向量运行环境腾出磁盘空间。"))
    log_path = root / "runtime-install.log"
    flags = subprocess.CREATE_NO_WINDOW
    env = runtime_env(root, download=True)
    try:
        with log_path.open("ab") as log:
            if not python.is_file():
                subprocess.run([sys.executable, "-I", "-B", "-m", "venv", str(runtime)], cwd=root, env=env,
                               stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=flags, timeout=180, check=True)
            subprocess.run(
                [str(python), "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check", "--no-input",
                 "install", "--cache-dir", str(root / "pip-cache"), "--only-binary", ":all:", "--require-hashes", "--index-url",
                 "https://pypi.org/simple", "--no-warn-script-location", "-r", str(_LOCK)],
                cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                creationflags=flags, timeout=900, check=True,
            )
            subprocess.run([str(python), "-I", "-B", "-c", "import numpy, torch, sentence_transformers, sentencepiece"],
                           cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                           creationflags=flags, timeout=70, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(message(f"Local runtime setup failed. Details: {log_path}",
                                 f"本地运行环境安装失败。详见 {log_path}")) from exc
    (runtime / _RUNTIME_MARKER).write_text("verified\n", encoding="utf-8")
    return python
