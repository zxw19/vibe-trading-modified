"""Market hooks and symbol-classification helpers — A-share only build.

Hosts symbol -> market detection helpers shared by ``runner.py`` and
``composite.py``: ``_MARKET_PATTERNS``, ``_detect_market``,
``_is_china_futures``, ``_detect_submarket``.
"""

from __future__ import annotations

import re
from typing import Dict, List

import pandas as pd

from backtest.models import Position


# ── Symbol -> market classification (shared by runner.py + composite.py) ──

_MARKET_PATTERNS = [
    (re.compile(r"^\d{6}\.(SZ|SH|BJ)$", re.I), "a_share"),
    (re.compile(r"^(51|15|56)\d{4}\.(SZ|SH)$", re.I), "a_share"),
    # China futures: product+delivery.exchange (e.g. IF2406.CFFEX, rb2410.SHFE)
    (re.compile(r"^[A-Za-z]{1,2}\d{3,4}\.(ZCE|DCE|SHFE|INE|CFFEX|GFEX)$", re.I), "futures"),
]

_CHINA_EXCHANGES = {"CFFEX", "SHFE", "DCE", "ZCE", "INE", "GFEX"}

# Known Chinese-futures product codes — used as a heuristic when a symbol
# lacks an exchange suffix (e.g. bare ``RB2410``, ``IF2406``). Without this
# table composite.py was misrouting such bare codes to GlobalFutures.
# Stored lowercase; ``_is_china_futures`` lowercases the extracted product
# before lookup so callers can pass any case (``RB2410`` and ``rb2410``
# both resolve correctly).
_CN_FUTURES_PRODUCTS = {
    "if", "ic", "ih", "im", "t", "tf", "ts", "tl",
    "au", "ag", "cu", "al", "zn", "pb", "ni", "sn", "ss",
    "rb", "hc", "i", "j", "jm",
    "sc", "fu", "lu", "bu", "nr",
    "c", "cs", "m", "y", "a", "p", "jd", "lh",
    "cf", "sr", "ta", "ma", "ap", "rm", "oi",
    "pp", "l", "v", "eg", "eb", "pf", "sa", "fg", "ur",
    "si", "lc",
}


def _detect_market(code: str) -> str:
    """Infer market type from symbol format.

    Args:
        code: Ticker / symbol string.

    Returns:
        Market type (a_share/us_equity/hk_equity/crypto/futures/forex);
        unknown defaults to ``a_share``.
    """
    for pattern, market in _MARKET_PATTERNS:
        if pattern.match(code):
            return market
    return "a_share"


def _is_china_futures(code: str) -> bool:
    """Check whether a futures code belongs to a Chinese exchange.

    Recognises two forms:
      1. ``<product><delivery>.<exchange>`` where exchange is one of
         CFFEX/SHFE/DCE/ZCE/INE/GFEX (e.g. ``IF2406.CFFEX``, ``rb2410.SHFE``).
      2. Bare ``<product><delivery>`` with no exchange suffix — matched
         against ``_CN_FUTURES_PRODUCTS`` (e.g. ``RB2410`` -> True).

    Args:
        code: Symbol string.

    Returns:
        True if it looks like a Chinese futures contract.
    """
    parts = code.upper().split(".")
    if len(parts) == 2:
        # Has an exchange suffix — trust it. CN exchange = True, anything
        # else = False. Without this guard the product-code heuristic below
        # would misclassify global futures whose product letters happen to
        # collide with a CN product (e.g. ``M2412.CBOT`` — US soybean meal).
        return parts[1] in _CHINA_EXCHANGES
    # Bare code (no exchange suffix): fall back to product-code heuristic.
    m = re.match(r"([A-Za-z]+)\d+", parts[0])
    if m:
        product = m.group(1).lower()
        if product in _CN_FUTURES_PRODUCTS:
            return True
    return False


def _detect_submarket(codes: List[str]) -> str:
    """Detect US vs HK from symbol suffixes.

    Args:
        codes: Instrument codes.

    Returns:
        ``"hk"`` if any code ends with ``.HK``, else ``"us"``.
    """
    for code in codes:
        if code.upper().endswith(".HK"):
            return "hk"
    return "us"

# Crypto funding fee / liquidation / forex swap helpers removed
# — A-share research build does not cover crypto or forex.
