"""The wrapper's own settings as the Desktop panel (config_schema.py) edits them: read from and written to
config.yaml plugins.hermes-memory-store of the profile being configured, the section the base provider reads too."""

from __future__ import annotations

from typing import Any, Callable

# The keys config_schema.py declares, with the default each takes when it is not stored.
DEFAULTS: dict[str, Any] = {
    "semantic_enabled": False,
    "semantic_url": "http://127.0.0.1:8791",
    "semantic_tau": 0.55,
    "semantic_max_extra": 3,
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


def read(hermes_home: str, load: Callable[[], dict]) -> dict[str, Any]:
    """``read_config_fields``: the stored values of our keys (absent = unset, the panel shows the default)."""
    section = stored(hermes_home, load)
    return {"values": {k: section[k] for k in DEFAULTS if k in section}, "placeholders": {}}


def current(hermes_home: str, load: Callable[[], dict]) -> dict[str, Any]:
    """Every key as it applies now: stored, else its default."""
    return {**DEFAULTS, **{k: v for k, v in stored(hermes_home, load).items() if k in DEFAULTS}}


def to_store(values: dict[str, Any]) -> dict[str, Any]:
    """``write_config_fields`` input as stored values: only our keys; a cleared one (None) goes back to its default,
    since the base's writer merges and cannot delete a key."""
    return {k: DEFAULTS[k] if v is None else v for k, v in values.items() if k in DEFAULTS}
