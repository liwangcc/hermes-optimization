"""Probe an OpenAI-compatible embedding endpoint and commit the profile connection."""
from __future__ import annotations

import ipaddress
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .setup_common import message, setup_lock

API_KEY_FIELD = "embedding_api_key"
API_KEY_VAR = "MEMORY_EMBEDDING_API_KEY"
NO_KEY = "MEMORY_LOCAL_EMBEDDING_NO_KEY"
DEFAULT_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "text-embedding-3-small"
TEST_TEXT = "Hermes embedding connection test."
_RESPONSE_LIMIT = 1 << 20


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _base_url(address: str) -> tuple[str, bool]:
    try:
        url = urlsplit(address.strip().rstrip("/"))
        port = url.port
    except ValueError:
        url, port = urlsplit(""), None
    loopback = _loopback(url.hostname or "")
    if (not url.hostname or url.username is not None or url.password is not None or url.query or url.fragment
            or url.scheme != "https" and not (url.scheme == "http" and loopback)
            or port == 0 or any(ord(char) <= 32 or char.isspace() or char == "\\" for char in address.strip())):
        raise ValueError(message(
            "Enter an HTTPS API base URL (HTTP is allowed on loopback).",
            "请输入 HTTPS 向量 API 地址。本机回环地址可以使用 HTTP。",
        ))
    path = url.path.removesuffix("/embeddings")
    return url._replace(path=path).geturl(), loopback


def _probe(url: str, model: str, key: str, *, loopback: bool) -> None:
    # A test sends a single fixed sentence. A redirect cannot move the credential.
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    handlers = [_NoRedirect()]
    if loopback:
        handlers.append(ProxyHandler({}))
    request = Request(f"{url}/embeddings", json.dumps({"model": model, "input": [TEST_TEXT]}).encode(), headers)
    try:
        with build_opener(*handlers).open(request, timeout=12) as response:
            raw = response.read(_RESPONSE_LIMIT + 1)
        data = json.loads(raw) if len(raw) <= _RESPONSE_LIMIT else {}
        vector = data["data"][0]["embedding"]
        if (not isinstance(vector, list) or not vector
                or not all(type(value) in (int, float) and math.isfinite(value) for value in vector)
                or not any(vector)):
            raise ValueError("invalid vector")
    except HTTPError as exc:
        code = exc.code
        exc.close()
        hint = message(" Check the key and model ID.", " 请核对密钥和模型 ID。")
        raise ValueError(message(f"Embedding API returned HTTP {code}.", f"向量接口返回 HTTP {code}。") + hint) from None
    except (URLError, OSError):
        raise ValueError(message("Could not reach the embedding API.", "无法连接向量接口，请检查地址和网络。")) from None
    except (ValueError, TypeError, KeyError, IndexError, OverflowError):
        raise ValueError(message("The API did not return an embedding vector.", "接口未返回有效向量，请核对模型和地址。")) from None


def saved_key(previous: dict, env: dict, address: str) -> tuple[str, str]:
    """(variable, key) already saved for *address*, or ("", ""): the connection's own key only at the address it was
    saved for, the profile's OPENAI_API_KEY only at the official endpoint."""
    if str(previous.get("embedding_url") or DEFAULT_URL).rstrip("/") == address:
        name = str(previous.get("embedding_key_env") or "")
        if name and name != NO_KEY and (name != "OPENAI_API_KEY" or address == DEFAULT_URL) and env.get(name):
            return name, env[name]
    if address == DEFAULT_URL and env.get("OPENAI_API_KEY"):
        return "OPENAI_API_KEY", env["OPENAI_API_KEY"]
    return "", ""


def connect(values: dict[str, str], home: str, *, read, save) -> None:
    """Probe before any write: a failed probe leaves the saved connection and the mode in effect as they were."""
    from hermes_cli.config import load_env, remove_env_value, save_env_value

    address, loopback = _base_url(values.get("embedding_url", ""))
    model = values.get("embedding_model", "").strip()
    submitted = values.get(API_KEY_FIELD, "").strip()
    if not model or len(model) > 256 or any(ord(char) < 32 for char in model):
        raise ValueError(message("Enter the embedding model ID.", "请输入向量模型 ID。"))
    with setup_lock(home):
        env = load_env()
        selected_key, key = (API_KEY_VAR, submitted) if submitted else saved_key(read(), env, address)
        if not key and not loopback:
            raise ValueError(message("Enter the API key for this address.", "请输入此地址对应的 API 密钥。"))
        if key and not all(32 < ord(char) < 127 for char in key):
            raise ValueError(message("The API key contains an invalid character.", "API 密钥含有无效字符。"))
        _probe(address, model, key, loopback=loopback)
        # An unauthenticated loopback service must never inherit a chat credential.
        if not key:
            selected_key = NO_KEY

        old_key = env.get(API_KEY_VAR)
        wrote_key = bool(submitted and submitted != old_key)
        if wrote_key:
            try:
                save_env_value(API_KEY_VAR, submitted)
                if load_env().get(API_KEY_VAR) != submitted:
                    raise ValueError("credential write was not accepted")
            except (ValueError, OSError):
                raise ValueError(message("Could not save the embedding key.", "无法保存向量服务密钥。")) from None
        try:
            save({
                "embeddings": True, "embedding_url": address, "embedding_model": model,
                "embedding_key_env": selected_key, "semantic_enabled": False,
            }, home)
        except Exception:
            if wrote_key and load_env().get(API_KEY_VAR) == submitted:
                if old_key is None:
                    remove_env_value(API_KEY_VAR)
                else:
                    save_env_value(API_KEY_VAR, old_key)
            raise
