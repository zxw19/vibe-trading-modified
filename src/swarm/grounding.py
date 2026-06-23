"""Pre-fetch market data AND realtime quotes for symbols in a swarm's user_vars.

Swarm workers are LLMs. Without explicit grounding they cheerfully quote
prices from their training data — which is wrong by definition. The fix is
structural: feed the worker real prices AND realtime quotes before it starts
reasoning, and tell it those are the ONLY prices it may cite.

This module now fetches TWO kinds of data per detected symbol:
1. **OHLCV bars** (30-day window) — for trend context
2. **Realtime quotes** from Tencent qt.gtimg.cn — for current price,
   today's high/low, PE TTM, market cap. This is the AUTHORITATIVE source
   for any statement about "当前价格/市值/PE/涨跌幅".

Bare US tickers
---------------
... (same promotion logic as before) ...
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, timedelta
from typing import Iterable

logger = logging.getLogger(__name__)


# Window of OHLCV bars to fetch per symbol. 30 calendar days yields
# roughly 21 US trading days — enough for a "recent" view without
# bloating the worker prompt.
DEFAULT_WINDOW_DAYS = 30
DEFAULT_MAX_SYMBOLS = 8
MAX_SYMBOLS_ENV = "SWARM_GROUNDING_MAX_SYMBOLS"

# How many of the most-recent rows to render in the worker prompt.
# The full window is still used to compute the min/max line; the table
# is truncated for readability.
PROMPT_TABLE_TAIL = 5

# Symbol patterns understood by the bundled loaders. Anchored on word
# boundaries so substrings of longer text don't trigger.
_SYMBOL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b[A-Z]{1,5}\.US\b"),
    re.compile(r"\b\d{3,5}\.HK\b"),
    re.compile(r"\b\d{6}\.(?:SZ|SH|BJ)\b"),
    re.compile(r"\b[A-Z]{2,6}-USDT\b"),
)

# Bare-ticker promotion: 2–5 uppercase letters. Single letters (A, F, T …)
# collide with ordinary prose far too often to be worth grounding. The
# lookarounds reject dotted compounds on either side (FOO.USDA promotes
# neither FOO nor USDA) while still matching a sentence-ending "NVDA.".
_BARE_US_TICKER_PATTERN = re.compile(r"(?<![\w.])[A-Z]{2,5}(?!\w)(?!\.\w)")

# All-caps tokens that show up in finance prompts but must never be promoted
# to a .US symbol — either not tickers at all, or colliding with unrelated
# listed products (CEO and MSCI are both real Yahoo symbols).
_BARE_TICKER_STOPWORDS = frozenset({
    # geography / venues / index & data providers
    "US", "USA", "UK", "EU", "HK", "CN", "JP", "NYSE", "AMEX", "SSE", "SZSE",
    "HKEX", "SPX", "NDX", "DJI", "DJIA", "HSI", "CSI", "FTSE", "MSCI", "VIX",
    # instruments / structures
    "ETF", "ETN", "ADR", "IPO", "REIT", "BOND", "SWAP", "PERP",
    # macro / institutions
    "FED", "FOMC", "SEC", "IMF", "GDP", "CPI", "PPI", "PMI", "PCE", "OPEC",
    "YOY", "QOQ", "MOM", "YTD", "EOD",
    # metrics / indicators
    "PE", "PB", "PS", "EPS", "ROE", "ROA", "ROI", "EBIT", "EV", "DCF",
    "CAGR", "IRR", "NAV", "AUM", "ATH", "ATL", "RSI", "MACD", "EMA", "SMA",
    "KDJ", "BOLL", "OHLC", "ADV", "PNL",
    # currencies / crypto traded under other loaders
    "USD", "EUR", "JPY", "GBP", "CNY", "CNH", "RMB", "KRW", "INR", "AUD",
    "CAD", "CHF", "FX", "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE",
    "USDT", "USDC", "DEFI", "NFT", "DAO",
    # trading verbs / order words
    "BUY", "SELL", "HOLD", "LONG", "SHORT", "CALL", "PUT", "STOP", "LIMIT",
    "TP", "SL", "DCA",
    # tech / prose acronyms
    "AI", "ML", "LLM", "API", "JSON", "CSV", "PDF", "URL", "HTML", "CEO",
    "CFO", "CTO", "COO", "CIO", "VP", "OK", "FAQ", "ASAP", "AM", "PM",
    "EST", "PST", "UTC", "GMT",
})


def extract_symbols_from_user_vars(user_vars: dict[str, str]) -> list[str]:
    """Return the deduplicated list of symbols mentioned anywhere in *user_vars*.

    Explicit suffixed symbols come first (in first-occurrence order),
    followed by guarded bare-ticker promotions (``NVDA`` → ``NVDA.US``),
    so explicit symbols always win the grounding cap. See the module
    docstring for the promotion guards.
    """
    explicit: dict[str, None] = {}  # ordered set
    promoted: dict[str, None] = {}
    for value in user_vars.values():
        if not isinstance(value, str):
            continue
        remainder = value
        for pattern in _SYMBOL_PATTERNS:
            for match in pattern.findall(remainder):
                explicit.setdefault(match, None)
            # Blank matched spans so the bare scan can't split a suffixed
            # symbol into bogus fragments (BTC-USDT -> BTC.US).
            remainder = pattern.sub(" ", remainder)
        for token in _BARE_US_TICKER_PATTERN.findall(remainder):
            if token not in _BARE_TICKER_STOPWORDS:
                promoted.setdefault(f"{token}.US", None)
    return list(explicit) + [s for s in promoted if s not in explicit]


def max_grounding_symbols() -> int:
    """Return the configured cap for symbols fetched into worker prompts."""
    raw = os.getenv(MAX_SYMBOLS_ENV, "").strip()
    if not raw:
        return DEFAULT_MAX_SYMBOLS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "grounding: invalid %s=%r, using default %d",
            MAX_SYMBOLS_ENV, raw, DEFAULT_MAX_SYMBOLS,
        )
        return DEFAULT_MAX_SYMBOLS
    return max(1, value)


def fetch_grounding_data(
    symbols: Iterable[str],
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    today: date | None = None,
) -> dict[str, list[dict]]:
    """Fetch OHLCV for *symbols* and return a code -> list-of-bars mapping.

    Each bar is a plain dict with ``trade_date`` (ISO string), ``open``,
    ``high``, ``low``, ``close``, ``volume``. Symbols that fail to
    resolve are simply omitted from the result with a logged warning.

    Args:
        symbols: Iterable of suffixed symbols (``NVDA.US`` etc.).
        window_days: Calendar-day lookback. Defaults to
            :data:`DEFAULT_WINDOW_DAYS`.
        today: Override the upper bound (mainly for tests). Defaults to
            ``date.today()``.

    Returns:
        Dict keyed by the *original* symbol string with the bars list as
        value. Empty if no symbols resolve.
    """
    symbols_list = list(symbols)
    if not symbols_list:
        return {}

    end = today or date.today()
    start = end - timedelta(days=window_days)
    start_str = start.isoformat()
    end_str = end.isoformat()

    # Imported lazily so unit tests of the extraction / formatting layer
    # don't have to drag in pandas + the loader graph just to import.
    # ``resolve_loader`` expects a *market* key (``"us_equity"`` etc.), not a
    # raw code; ``_detect_market`` is the function ``runner.py`` already uses
    # to dispatch the same shapes we extract here, so reusing it keeps the
    # routing identical to the rest of the codebase.
    from backtest.loaders.registry import resolve_loader
    from backtest.runner import _detect_market

    out: dict[str, list[dict]] = {}
    for code in symbols_list:
        try:
            market = _detect_market(code)
            loader = resolve_loader(market)  # already a ready-to-use instance
            df_map = loader.fetch([code], start_str, end_str, interval="1D")
        except Exception as exc:  # pragma: no cover — depends on network
            logger.warning(
                "grounding: failed to fetch %s — %s", code, exc, exc_info=False
            )
            continue
        df = df_map.get(code)
        if df is None or df.empty:
            logger.info("grounding: no data returned for %s", code)
            continue
        rows: list[dict] = []
        for ts, row in df.iterrows():
            rows.append({
                "trade_date": getattr(ts, "isoformat", lambda: str(ts))(),
                "open": float(row.get("open", 0.0)),
                "high": float(row.get("high", 0.0)),
                "low": float(row.get("low", 0.0)),
                "close": float(row.get("close", 0.0)),
                "volume": float(row.get("volume", 0.0)),
            })
        if rows:
            out[code] = rows
    return out


# ---------------------------------------------------------------------------
# Realtime quote injection — fetches current prices from Tencent
# ---------------------------------------------------------------------------

_TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="

# Mapping from A-share code suffix to Tencent prefix
_SUFFIX_TO_PREFIX = {"SH": "sh", "SZ": "sz", "BJ": "sz"}


def _tencent_query_symbol(code: str) -> str | None:
    """Convert 600519.SH → sh600519, 000001.SZ → sz000001."""
    parts = code.strip().upper().rpartition(".")
    symbol, suffix = parts[0], parts[2]
    if not symbol.isdigit() or len(symbol) != 6:
        return None
    prefix = _SUFFIX_TO_PREFIX.get(suffix)
    return f"{prefix}{symbol}" if prefix else None


def _parse_tencent_quote_line(line: str, code: str) -> dict | None:
    """Parse one line of Tencent's ~-delimited realtime response."""
    if "=\"" not in line:
        return None
    raw = line.split("=\"", 1)[1].rstrip('";\r\n')
    fields = raw.split("~")
    if len(fields) < 50:
        return None

    def f(idx: int) -> float | None:
        try:
            v = fields[idx].strip()
            return float(v) if v else None
        except (IndexError, ValueError):
            return None

    dt_raw = fields[30].strip()
    dt = ""
    if len(dt_raw) >= 14 and dt_raw.isdigit():
        dt = f"{dt_raw[0:4]}-{dt_raw[4:6]}-{dt_raw[6:8]} {dt_raw[8:10]}:{dt_raw[10:12]}:{dt_raw[12:14]}"

    return {
        "code": code,
        "name": fields[1].strip(),
        "latest_price": f(3),
        "previous_close": f(4),
        "open": f(5),
        "high": f(33),
        "low": f(34),
        "change_pct": f(32),
        "pe_ttm": f(39),
        "total_market_cap_yi": f(45),
        "turnover_rate_pct": f(38),
        "quote_time": dt,
    }


def fetch_realtime_quotes(symbols: Iterable[str]) -> dict[str, dict]:
    """Fetch realtime quotes from Tencent for A-share codes.

    Args:
        symbols: Iterable of suffixed symbols (e.g. ``["600519.SH", "000001.SZ"]``).

    Returns:
        Dict keyed by original symbol with quote data as value. Non-A-share
        codes are silently skipped.
    """
    import requests

    code_list = [c for c in symbols if c.upper().endswith((".SH", ".SZ", ".BJ"))]
    if not code_list:
        return {}

    symbol_map = {}
    for code in code_list:
        ts = _tencent_query_symbol(code)
        if ts:
            symbol_map[code] = ts

    if not symbol_map:
        return {}

    rev = {ts: code for code, ts in symbol_map.items()}
    query = ",".join(symbol_map.values())
    try:
        resp = requests.get(
            f"{_TENCENT_QUOTE_URL}{query}",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        text = resp.content.decode("gbk", errors="replace")
    except Exception as exc:
        logger.warning("grounding: realtime quote fetch failed: %s", exc)
        return {}

    out: dict[str, dict] = {}
    for line in text.splitlines():
        sym = line.split("=", 1)[0].removeprefix("v_")
        code = rev.get(sym)
        if not code:
            continue
        parsed = _parse_tencent_quote_line(line, code)
        if parsed:
            out[code] = parsed
    return out


def format_grounding_block(
    grounding: dict[str, list[dict]],
    quotes: dict[str, dict] | None = None,
) -> str:
    """Render *grounding* and *quotes* as a mandatory markdown block.

    Combines recent OHLCV bars (for trend context) with realtime quotes
    (for current prices). Returns empty string if neither has any data.
    """
    if not grounding and not quotes:
        return ""

    sections: list[str] = []

    # -- Realtime quotes section (MOST IMPORTANT) --
    if quotes:
        quote_lines = [
            "## Current Prices — MANDATORY AUTHORITATIVE DATA",
            "",
            "**These are the ONLY current prices, PE ratios, and market caps you may cite.**",
            "They come from Tencent realtime qt.gtimg.cn as of this run's start time.",
            "If a code is not in this table, you MUST call `get_latest_quote` to get its data.",
            "",
            "| Code | Name | Latest Price | Chg% | High | Low | PE(TTM) | Mkt Cap(亿) | Time |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for code, q in quotes.items():
            name = q.get("name", code)
            lp = q.get("latest_price")
            chg = q.get("change_pct")
            high = q.get("high")
            low = q.get("low")
            pe = q.get("pe_ttm")
            mcap = q.get("total_market_cap_yi")
            qt = q.get("quote_time", "")
            lp_s = f"{lp:.2f}" if isinstance(lp, (int, float)) else "N/A"
            chg_s = f"{chg:.2f}%" if isinstance(chg, (int, float)) else "N/A"
            high_s = f"{high:.2f}" if isinstance(high, (int, float)) else "N/A"
            low_s = f"{low:.2f}" if isinstance(low, (int, float)) else "N/A"
            pe_s = f"{pe:.2f}" if isinstance(pe, (int, float)) else "N/A"
            mcap_s = f"{mcap:.2f}" if isinstance(mcap, (int, float)) else "N/A"
            quote_lines.append(
                f"| {code} | {name} | {lp_s} | {chg_s} | {high_s} | "
                f"{low_s} | {pe_s} | {mcap_s} | {qt} |"
            )
        quote_lines.append("")
        quote_lines.append(
            "**HARD RULE: Every price/PE/market-cap cell in your report tables "
            "MUST come from the table above, or from a `get_latest_quote` call "
            "you made in THIS run. Training-data prices are WRONG.**"
        )
        sections.append("\n".join(quote_lines))

    # -- Historical OHLCV section --
    if grounding:
        ohlc_sections = []
        for code, rows in grounding.items():
            if not rows:
                continue
            first_date = rows[0]["trade_date"][:10]
            last_date = rows[-1]["trade_date"][:10]
            closes = [row["close"] for row in rows]
            window_low = min(closes)
            window_high = max(closes)
            last_close = closes[-1]

            lines = [
                f"### {code} — Recent OHLCV (for trend context only, NOT current price)",
                f"Window: {first_date} → {last_date}",
                "",
                "| Date | Close | Volume |",
                "| --- | ---: | ---: |",
            ]
            for row in rows[-PROMPT_TABLE_TAIL:]:
                lines.append(
                    f"| {row['trade_date'][:10]} | {row['close']:.2f} "
                    f"| {int(row['volume']):,} |"
                )
            lines.append("")
            lines.append(
                f"**Last completed close:** {last_close:.2f} ({last_date})  "
                f"**Window range:** {window_low:.2f} – {window_high:.2f}"
            )
            ohlc_sections.append("\n".join(lines))

        if ohlc_sections:
            ohlc_header = (
                "## Historical OHLCV (for trend context)\n\n"
                "The LAST ROW of each table is the most recent COMPLETED "
                "trading day. It is NOT the current price — use the Current "
                "Prices section above for current data."
            )
            sections.append(ohlc_header + "\n\n" + "\n\n".join(ohlc_sections))

    if not sections:
        return ""

    header = (
        "## Ground Truth — MANDATORY Authoritative Market Data\n\n"
        "**ALL prices, valuations, and market data below are the ONLY data "
        "you may cite in your report.** Do NOT use numbers from your training "
        "data — they are from before your knowledge cutoff and are WRONG. "
        "If you need data for a symbol not listed here, call `get_latest_quote` "
        "or `get_financial_statements` to fetch it. Any number not traceable "
        "to this block or a tool call you made MUST be omitted or labeled "
        "\"资料缺口\".\n"
    )
    return header + "\n\n" + "\n\n".join(sections)
