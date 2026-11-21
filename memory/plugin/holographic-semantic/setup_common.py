"""Profile-local serialization for the two embedding setup paths."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Iterator


def message(en: str, zh: str) -> str:
    from agent.i18n import get_language

    return zh if get_language() == "zh" else en


def progress(text: str, zh: str) -> dict:
    return {"status": text, "translations": {"zh": {"status": zh}}}


def result(text: str, zh: str) -> dict:
    return {"done": True, "result": text, "translations": {"zh": {"result": zh}}}


@contextlib.contextmanager
def setup_lock(home: str) -> Iterator[None]:
    """Cloud changes and local setup jobs can come from different processes."""
    path = Path(home) / "services" / "memory-embeddings" / "setup.lock"
    path.resolve().relative_to(Path(home).resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError(message("An embedding setup is already running.", "已有向量模型设置正在运行。")) from exc
        # Closing the descriptor releases the lock on both platforms.
        yield
