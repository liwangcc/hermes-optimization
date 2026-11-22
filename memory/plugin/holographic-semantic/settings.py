"""The wrapper's own settings as the Desktop panel (config_schema.py) edits them: read from and written to
config.yaml plugins.hermes-memory-store of the profile being configured, the section the base provider reads too."""

from __future__ import annotations

from math import isfinite
from typing import Any, Callable

from utils import is_truthy_value

from . import cloud_setup

# The keys config_schema.py declares, with the default each takes when it is not stored.
DEFAULTS: dict[str, Any] = {
    "semantic_enabled": False,
    "semantic_url": "http://127.0.0.1:8791",
    "semantic_tau": 0.55,
    "embedding_min_score": None,  # the base's own key: unset is no floor
    "catalog_enabled": False,
    "catalog_max_tokens": 3000,
}


def stored(hermes_home: str, load: Callable[[], dict]) -> dict[str, Any]:
    """The section as stored for *hermes_home*, not for whichever profile this process runs."""
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    token = set_hermes_home_override(hermes_home)
    try:
        section = load()
    finally:
        reset_hermes_home_override(token)
    return section if isinstance(section, dict) else {}


def mode(section: dict[str, Any]) -> str:
    """The embedding mode in effect: "cloud" (the base's own embeddings), "local" (the sidecar) or ""."""
    if is_truthy_value(section.get("embeddings")):
        return "cloud"
    return "local" if is_truthy_value(section.get("semantic_enabled")) else ""


def read(hermes_home: str, load: Callable[[], dict]) -> dict[str, Any]:
    """``read_config_fields``: the stored values of our keys (absent = unset, the panel shows the default)."""
    from hermes_cli.config import load_env

    env: dict[str, str] = {}

    def both() -> dict:
        env.update(load_env())  # this profile's, under the same override
        return load()

    section = stored(hermes_home, both)
    fields = (*DEFAULTS, "embedding_url", "embedding_model")
    values = {k: section[k] for k in fields if k in section}
    # The key field reads as set only when a saved key belongs to the endpoint shown: never the key itself.
    address = str(section.get("embedding_url") or cloud_setup.DEFAULT_URL).rstrip("/")
    if cloud_setup.saved_key(section, env, address)[1]:
        values[cloud_setup.API_KEY_FIELD] = True
    return {"values": values, "placeholders": {}, "connection_state": mode(section)}


def current(hermes_home: str, load: Callable[[], dict]) -> dict[str, Any]:
    """Every key as it applies now: stored, else its default."""
    return {**DEFAULTS, **{k: v for k, v in stored(hermes_home, load).items() if k in DEFAULTS}}


def to_store(values: dict[str, Any]) -> dict[str, Any]:
    """``write_config_fields`` input as stored values: only our keys; a cleared one (None) goes back to its default,
    since the base's writer merges and cannot delete a key. The panel edits numbers as text."""
    stored = {key: DEFAULTS[key] if value is None else value for key, value in values.items() if key in DEFAULTS}
    numbers = {"semantic_tau": float, "catalog_max_tokens": int, "embedding_min_score": float}
    for key, parse in numbers.items():
        value = stored.get(key)
        if value is None:
            continue
        try:
            number = parse(str(value))
            if parse is float and not isfinite(number):
                raise ValueError
        except ValueError:
            kind = "a whole number" if parse is int else "a finite number"
            raise ValueError(f"{key} must be {kind}") from None
        stored[key] = number
    return stored
