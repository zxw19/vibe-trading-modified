---
name: minute-analysis
description: Minute-level data analysis and backtesting. Retrieves minute candlesticks through Tushare and can be used both for analysis and as input to the backtest engine (A-share only).
category: strategy
---
# Minute-Level Data Analysis and Backtesting

## Purpose

Retrieve minute-level candlestick data through data-source APIs and calculate intraday indicators (VWAP, TWAP, volume distribution, and more).
Supports minute-level backtesting: set `"interval": "5m"` in `config.json` and use the `backtest` tool to run intraday strategies.

## Backtest Configuration

For minute-level backtests, simply add the `interval` field in `config.json`:

```json
{
  "source": "tushare",
  "codes": ["000001.SZ"],
  "start_date": "2026-03-01",
  "end_date": "2026-03-15",
  "interval": "5m",
  "initial_cash": 1000000,
  "commission": 0.001
}
```

- The annualization factor for A-shares is 252 trading days
- Minute-level datasets are large. Recommended time limits: no more than 7 days for `1m`, no more than 30 days for `5m`, and no more than 1 year for `1H`

## Supported Data Sources and Intervals

| Data Source | Supported Intervals | Notes |
|--------|---------|------|
| Tushare | 1m/5m/15m/30m/1H | China A-shares, requires score >= 2000 |
| Tencent | 1m/5m/15m/30m/1H | China A-shares, never-banned |
| Mootdx | 1m/5m/15m/30m/1H | China A-shares, TDX servers |

## Tushare Minute Candlestick API

```python
import tushare as ts
import pandas as pd

pro = ts.pro_api("your_token")
df = pro.stk_mins(ts_code="000001.SZ", freq="5min",
                   start_date="2026-03-01", end_date="2026-03-15")
```

## Indicator Calculation Templates

### VWAP (Volume-Weighted Average Price)

```python
typical_price = (df["high"] + df["low"] + df["close"]) / 3
df["vwap"] = (typical_price * df["vol"]).cumsum() / df["vol"].cumsum()
```

### TWAP (Time-Weighted Average Price)

```python
df["twap"] = df["close"].expanding().mean()
```

### Volume Distribution

```python
df["vol_pct"] = df["vol"] / df["vol"].sum() * 100
hourly_vol = df.set_index("ts").resample("1h")["vol"].sum()
```

## Parameters

| Parameter | Description |
|------|------|
| ts_code | A-share code, such as `"000001.SZ"` |
| freq / interval | Candlestick interval: `1m/5m/15m/30m/1H` |
| start_date / end_date | Date range for data retrieval |

## Common Pitfalls

- The time range for minute-level backtests should not be too long, otherwise both data retrieval and backtesting will become slow or time out
- Tushare minute endpoints require a score >= 2000. If the score is insufficient, the API returns empty data
- Transaction costs for minute strategies should be set lower (for example 0.05% instead of 0.1%) because intraday trading is frequent

## Dependencies

```bash
pip install pandas numpy tushare
```
