---
name: akshare
category: data-source
description: AKShare financial data aggregator (18k+ stars). Free, no API key. Covers A-shares, futures, macro, forex. Primary fallback for tushare.
---

## Overview

AKShare is a completely free, open-source Python financial data library. No registration or API key required. It aggregates data from public sources (Sina, East Money, etc.) covering Chinese markets.

- GitHub: https://github.com/akfamily/akshare (18k+ stars)
- Install: `pip install akshare`

## Quick Start

```python
import akshare as ak

# A-share daily OHLCV (前复权)
df = ak.stock_zh_a_hist(symbol="000001", period="daily",
                         start_date="20240101", end_date="20260101", adjust="qfq")
```

## Top 10 High-Frequency Interfaces

### A-shares

| Function | Description | Key Params |
|----------|-------------|------------|
| `stock_zh_a_hist()` | A-share OHLCV | symbol, period, start_date, end_date, adjust |
| `stock_zh_a_spot_em()` | Real-time A-share quotes | (none) |
| `stock_individual_info_em()` | Stock basic info | symbol |
| `stock_zh_a_hist_min_em()` | Intraday bars | symbol, period(1/5/15/30/60) |

### Macro / Forex / Futures

| Function | Description |
|----------|-------------|
| `macro_china_gdp()` | China GDP data |
| `macro_china_cpi()` | China CPI data |
| `futures_main_sina()` | Futures main contract quotes |
| `currency_boc_sina()` | BOC forex rates |

## Column Names

AKShare returns Chinese column names by default:

| Chinese | English | Description |
|---------|---------|-------------|
| 日期 | date | Trade date |
| 开盘 | open | Open price |
| 最高 | high | High price |
| 最低 | low | Low price |
| 收盘 | close | Close price |
| 成交量 | volume | Volume |
| 成交额 | amount | Turnover |
| 涨跌幅 | pct_change | % change |
| 换手率 | turnover_rate | Turnover rate |

## Date Format

- Input: `YYYYMMDD` string (e.g. `"20240101"`)
- Output: `日期` column as string, convert with `pd.to_datetime()`

## Symbol Format

- A-shares: pure digits `"000001"` (no .SZ suffix)

## Built-in Loader

The project has a built-in AKShare DataLoader at `backtest/loaders/akshare_loader.py`. When backtesting, the runner automatically falls back to AKShare when tushare is unavailable.

## Reference Docs

For less common interfaces, see the `references/` subdirectory or the official docs at https://akshare.akfamily.xyz/
