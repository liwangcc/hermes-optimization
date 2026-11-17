"""What a calibration will cost, said before anything is sent: estimated tokens and their price."""
from __future__ import annotations

import math
import re

# Chinese, Japanese and Korean characters (CJK ideographs, kana, hangul): about one token each.
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")

# USD per million input tokens, list prices checked 2026-11. Any other remote model needs --price-per-mtok.
PRICES = {"text-embedding-3-small": 0.02, "text-embedding-3-large": 0.13}


def tokens(text: str) -> int:
    """Estimated tokens of one text: a CJK character ~ 1 token, any other four characters ~ 1 token.
    shortcut: no tokenizer is bundled (numpy + stdlib only); the estimate decides whether to run, it is not the bill."""
    cjk = len(CJK.findall(text))
    return max(1, cjk + math.ceil((len(text) - cjk) / 4))


def estimate(texts: list[str], model: str, local: bool, price: float | None = None) -> dict:
    """{"tokens", "usd" (None: price unknown), "price" (where the price came from)} for sending *texts* once."""
    n = sum(tokens(t) for t in texts)
    if local:
        return {"tokens": n, "usd": 0.0, "price": "local endpoint, free"}
    per = price if price is not None else PRICES.get(model)
    if per is None:
        return {"tokens": n, "usd": None, "price": "unknown for this model: pass --price-per-mtok"}
    source = "--price-per-mtok" if price is not None else "list price checked 2026-11"
    return {"tokens": n, "usd": n * per / 1e6, "price": f"{per} USD per 1M tokens ({source})"}


def line(texts_n: int, est: dict) -> str:
    """The sentence printed before a run."""
    usd = "price unknown" if est["usd"] is None else f"~ ${est['usd']:.4f}"
    return f"estimate: {texts_n} texts, ~{est['tokens']:,} tokens, {usd} ({est['price']})"
