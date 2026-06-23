"""Local market data tool backed by the shared loader layer."""

from __future__ import annotations

from typing import Any

from src.agent.tools import BaseTool
from src.market_data import DEFAULT_MAX_ROWS, fetch_market_data_json


class MarketDataTool(BaseTool):
    """Fetch normalized OHLCV data through China A-share loaders."""

    name = "get_market_data"
    description = (
        "Fetch HISTORICAL OHLCV bars for A-share stocks (daily bars only). "
        "FOR CHARTS AND TREND ANALYSIS ONLY. "
        "The last OHLCV row is the most recent COMPLETED trading day — it does "
        "NOT represent the current trading session. "
        "For current prices, today's high/low, PE TTM, market cap: use "
        "get_latest_quote instead. "
        "Uses free domestic chain: tencent > mootdx > eastmoney > baostock > akshare."
    )
    parameters = {
        "type": "object",
        "properties": {
            "codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": 'A-share symbols, e.g. ["000001.SZ"], ["600519.SH"], ["000300.SH"].',
            },
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format.",
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format.",
            },
            "source": {
                "type": "string",
                "enum": [
                    "auto",
                    "tencent",
                    "mootdx",
                    "eastmoney",
                    "baostock",
                    "akshare",
                    "local",
                ],
                "description": (
                    "Data source. 'auto' detects from symbol with fallback through "
                    "free domestic sources. All sources are free and work in China."
                ),
                "default": "auto",
            },
            "interval": {
                "type": "string",
                "description": "Bar size, e.g. 1D, 1H, 4H, 30m.",
                "default": "1D",
            },
            "max_rows": {
                "type": "integer",
                "description": "Per-symbol row cap. Use 0 only when the full series is required.",
                "default": DEFAULT_MAX_ROWS,
            },
        },
        "required": ["codes", "start_date", "end_date"],
    }

    def execute(self, **kwargs: Any) -> str:
        return fetch_market_data_json(
            codes=kwargs["codes"],
            start_date=kwargs["start_date"],
            end_date=kwargs["end_date"],
            source=kwargs.get("source", "auto"),
            interval=kwargs.get("interval", "1D"),
            max_rows=kwargs.get("max_rows", DEFAULT_MAX_ROWS),
        )
