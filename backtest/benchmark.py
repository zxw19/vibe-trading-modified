"""Benchmark ticker resolution and fetch for A-share backtest comparison.

Uses the same A-share fallback chain as the rest of the project
(registry.get_loader_cls_with_fallback) so benchmarks always match
the strategy data source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


# A-share-only benchmark map.
MARKET_BENCHMARKS: dict[str, Optional[str]] = {
    "a_share":  "000300.SH",  # CSI 300
    "futures":  None,         # no universal benchmark for China futures
}


@dataclass
class BenchmarkResult:
    ticker:     str
    ret_series: pd.Series       # per-bar returns, index = timestamps
    total_ret: float          # total return over the period


def resolve_benchmark(
    strategy_codes: list[str],
    source:       str,
    start_date:   str,
    end_date:     str,
    interval:     str = "1D",
    explicit:     Optional[str] = None,
) -> Optional[BenchmarkResult]:
    """Resolve the appropriate A-share benchmark ticker and fetch its return series.

    Args:
        strategy_codes: Instruments being backtested (used for market inference).
        source:         Data source name (tencent / mootdx / eastmoney / baostock / akshare / auto).
        start_date:     Backtest start date.
        end_date:       Backtest end date.
        interval:       Bar interval (1m / 5m / 15m / 30m / 1H / 4H / 1D).
        explicit:       Override ticker (e.g. "000300.SH" passed via config).

    Returns:
        BenchmarkResult with return series and total return, or None if no
        benchmark applies or fetch fails.
    """
    ticker = _resolve_ticker(strategy_codes, explicit)
    if ticker is None:
        return None

    try:
        bench_df = _fetch_benchmark(ticker, source, start_date, end_date, interval)
    except Exception:
        return None

    if bench_df.empty or "close" not in bench_df.columns:
        return None

    close = bench_df["close"].dropna()
    if len(close) < 2:
        return None

    ret_series = close.pct_change().fillna(0.0)
    total_ret   = float((1 + ret_series).prod() - 1)

    return BenchmarkResult(ticker=ticker, ret_series=ret_series, total_ret=total_ret)


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------

def _resolve_ticker(
    codes:     list[str],
    explicit:  Optional[str],
) -> Optional[str]:
    """Pick the A-share benchmark ticker to use."""
    if explicit:
        return explicit

    # Default: CSI 300 for A-share strategies.
    if not codes:
        return "000300.SH"

    first = codes[0].upper()
    if first.endswith((".SH", ".SZ", ".BJ")):
        return "000300.SH"

    return None


def _fetch_benchmark(
    ticker:     str,
    source:     str,
    start_date: str,
    end_date:   str,
    interval:   str,
) -> pd.DataFrame:
    """Fetch benchmark OHLCV data via the A-share loader chain."""
    from backtest.loaders.registry import get_loader_cls_with_fallback

    loader_cls = get_loader_cls_with_fallback(source)
    loader = loader_cls()
    result = loader.fetch([ticker], start_date, end_date, interval=interval)

    if isinstance(result, dict):
        df = result.get(ticker)
    elif isinstance(result, pd.DataFrame):
        df = result
    else:
        return pd.DataFrame()

    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return pd.DataFrame()

    return df
