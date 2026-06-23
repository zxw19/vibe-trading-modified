"""Latest A-share quote tool using Tencent realtime quote endpoint."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from backtest.loaders._http import throttled_get
from src.agent.tools import BaseTool

logger = logging.getLogger(__name__)

_TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
_HOST_KEY = "tencent_quote"
_MIN_INTERVAL = 0.2


def _tencent_symbol(code: str) -> str | None:
    symbol, dot, suffix = code.strip().upper().partition(".")
    if not dot or not symbol.isdigit() or len(symbol) != 6:
        return None
    if suffix == "SH":
        return f"sh{symbol}"
    if suffix in {"SZ", "BJ"}:
        return f"sz{symbol}"
    return None


def _decode_tencent_content(content: bytes) -> str:
    return content.decode("gbk", errors="replace")


def _parse_quote_line(line: str, requested_code: str) -> dict[str, Any] | None:
    if "=\"" not in line:
        return None
    raw = line.split("=\"", 1)[1].rstrip('";\r\n')
    fields = raw.split("~")
    if len(fields) < 50:
        return None

    def as_float(index: int) -> float | None:
        try:
            value = fields[index].strip()
            return float(value) if value else None
        except (IndexError, ValueError):
            return None

    def as_int(index: int) -> int | None:
        try:
            value = fields[index].strip()
            return int(float(value)) if value else None
        except (IndexError, ValueError):
            return None

    quote_time = fields[30].strip() if len(fields) > 30 else ""
    quote_date = ""
    quote_datetime = ""
    if len(quote_time) >= 14 and quote_time.isdigit():
        quote_date = f"{quote_time[0:4]}-{quote_time[4:6]}-{quote_time[6:8]}"
        quote_datetime = (
            f"{quote_date} {quote_time[8:10]}:{quote_time[10:12]}:{quote_time[12:14]}"
        )

    return {
        "code": requested_code,
        "name": fields[1].strip(),
        "latest_price": as_float(3),
        "previous_close": as_float(4),
        "open": as_float(5),
        "volume_lot": as_int(6),
        "bid_volume_lot": as_int(7),
        "ask_volume_lot": as_int(8),
        "change": as_float(31),
        "change_pct": as_float(32),
        "high": as_float(33),
        "low": as_float(34),
        "turnover_amount_yuan": as_float(37),
        "turnover_rate_pct": as_float(38),
        "pe_ttm": as_float(39),
        "market_cap_100m": as_float(45),
        "float_market_cap_100m": as_float(44),
        "quote_date": quote_date,
        "quote_datetime": quote_datetime,
        "source": "tencent_realtime",
        "freshness": "realtime_or_latest_trading_snapshot",
    }


class LatestQuoteTool(BaseTool):
    """Fetch latest A-share quote snapshots from Tencent realtime endpoint."""

    name = "get_latest_quote"
    description = (
        "Fetch LATEST/REALTIME A-share quote snapshots — THE ONLY TOOL for "
        "current stock price, today's high/low/open, PE TTM, market cap, "
        "turnover. Returns realtime data from Tencent qt.gtimg.cn. "
        "MANDATORY: call this BEFORE making ANY statement about current price, "
        "market cap, PE, high, low, or change%. "
        "NEVER use get_market_data for current prices — get_market_data returns "
        "HISTORICAL OHLCV bars whose last row is the most recent COMPLETED "
        "trading day, NOT current session data. "
        "Use this for: valuation tables, peer price comparison, industry "
        "analysis stock prices, any table showing 当前价格/最新价/市值/PE/涨跌幅."
    )
    parameters = {
        "type": "object",
        "properties": {
            "codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": 'A-share symbols, e.g. ["600519.SH", "000001.SZ"].',
            }
        },
        "required": ["codes"],
    }

    def execute(self, **kwargs: Any) -> str:
        codes = [str(code).strip().upper() for code in kwargs["codes"]]
        symbol_map = {code: _tencent_symbol(code) for code in codes}
        valid_pairs = [(code, symbol) for code, symbol in symbol_map.items() if symbol]
        unresolved = [code for code, symbol in symbol_map.items() if not symbol]

        quotes: list[dict[str, Any]] = []
        if valid_pairs:
            query = ",".join(symbol for _, symbol in valid_pairs)
            try:
                response = throttled_get(
                    f"{_TENCENT_QUOTE_URL}{query}",
                    host_key=_HOST_KEY,
                    min_interval=_MIN_INTERVAL,
                    timeout=10.0,
                )
                response.raise_for_status()
                text = _decode_tencent_content(response.content)
                requested_by_symbol = {symbol: code for code, symbol in valid_pairs}
                for line in text.splitlines():
                    left = line.split("=", 1)[0]
                    symbol = left.removeprefix("v_")
                    code = requested_by_symbol.get(symbol)
                    if not code:
                        continue
                    parsed = _parse_quote_line(line, code)
                    if parsed is None:
                        unresolved.append(code)
                    else:
                        quotes.append(parsed)
            except Exception as exc:
                logger.warning("latest quote fetch failed: %s", exc)
                unresolved.extend(code for code, _ in valid_pairs)

        # Direct table copy section — agent can use immediately in markdown tables.
        table_columns = ["code", "name", "latest_price", "open", "high", "low",
                         "previous_close", "change_pct", "pe_ttm",
                         "market_cap_100m", "turnover_rate_pct", "quote_datetime"]
        table_rows = []
        for q in quotes:
            row = {}
            for col in table_columns:
                val = q.get(col)
                if isinstance(val, float):
                    row[col] = round(val, 2)
                else:
                    row[col] = val
            table_rows.append(row)

        payload = {
            "as_of": datetime.now().isoformat(timespec="seconds"),
            "source": "tencent_realtime",
            "quote_count": len(quotes),
            "table_summary": {
                "columns": table_columns,
                "rows": table_rows,
            },
            "quotes": quotes,
            "unresolved": sorted(set(unresolved)),
            "note": "latest_price = realtime bid/ask mid during trading hours, otherwise latest close. 当前价格可以直接填入估值表，来源为腾讯实时行情。",
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
