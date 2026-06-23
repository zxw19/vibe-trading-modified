---
name: adr-hshare
description: H-share/A-share cross-listing premium analysis — track pricing gaps between HK-listed H-shares and A-shares for arbitrage signals and dual-listing valuation.
category: flow
---
# H-Share / A-Share Cross-Listing Analysis

## Overview

Many Chinese companies are listed on both A-share (Shanghai/Shenzhen) and H-share (Hong Kong) markets. Pricing gaps between these listings create arbitrage opportunities and reveal market-specific sentiment differences. This skill provides frameworks for analyzing AH cross-listing premiums and identifying arbitrage signals.

## Core Concepts

### 1. Cross-Listing Structures

| Structure | Description | Examples |
|-----------|-------------|---------|
| A + H dual-listed | Same company listed on both A-share and HK exchange | PetroChina (601857.SH / 0857.HK), ICBC (601398.SH / 1398.HK) |

### 2. AH Premium Analysis

**AH Premium = (A-share price / H-share price in CNY terms - 1) × 100%**

```python
def calculate_ah_premium(a_price_cny, h_price_hkd, usdcny, usdhkd):
    """Calculate AH premium for a dual-listed stock."""
    h_price_cny = h_price_hkd * (usdcny / usdhkd)  # Convert HKD to CNY
    ah_premium = (a_price_cny / h_price_cny - 1) * 100
    return ah_premium

# Example: PetroChina
# A-share: 8.50 CNY, H-share: 6.20 HKD
# USDCNY: 7.25, USDHKD: 7.82
# H in CNY: 6.20 * (7.25/7.82) = 5.75 CNY
# AH Premium: (8.50/5.75 - 1) * 100 = 47.8%
```

**AH Premium signal interpretation:**

| Premium Level | Interpretation | Action |
|--------------|----------------|--------|
| >50% | Extreme A-share premium; A-share speculative bubble or H-share extreme undervaluation | Strong: buy H, sell/avoid A |
| 30-50% | Elevated premium; normal for high-retail-participation names | Moderate: favor H if fundamentals same |
| 10-30% | Normal range for most AH pairs | Neutral; no strong arbitrage signal |
| 0-10% | Compressed premium; A-shares relatively cheap | Unusual; investigate catalyst |
| <0% | H-share premium over A-share | Very rare; usually near-term event-driven |

**Structural drivers of AH premium:**
1. **Liquidity premium**: A-shares have much higher retail participation and turnover → liquidity premium
2. **Access premium**: A-shares were historically hard for foreigners to access → scarcity premium
3. **Currency expectations**: CNY depreciation expectations widen the premium
4. **Regulatory arbitrage**: different trading rules (T+1 in A-shares vs T+0 in HK)
5. **Investor composition**: A-share retail speculative premium vs HK institutional valuation discipline

### 3. Cross-Listing Arbitrage Strategies

**Strategy 1: AH Premium Mean-Reversion**
```python
# When AH premium for a specific stock diverges significantly from its historical average
ah_premium_current = 45  # current premium
ah_premium_mean_12m = 35  # 12-month average
ah_premium_std = 8        # standard deviation

z_score = (ah_premium_current - ah_premium_mean_12m) / ah_premium_std

if z_score > 2.0:
    signal = "fade_premium"  # A-share overvalued vs H; buy H, avoid A
elif z_score < -2.0:
    signal = "buy_premium"   # A-share undervalued vs H; buy A, avoid H
else:
    signal = "neutral"
```

**Strategy 2: Event-Driven Cross-Listing**
- MSCI / FTSE index inclusion of HK listing: triggers passive fund buying in HK
- Stock Connect inclusion (HK primary listing eligible): triggers mainland institutional buying

## Data Access

```python
import tushare as ts

pro = ts.pro_api("your_token")

# For A+H pairs: fetch A-share and H-share data
petrochina_a = pro.daily(ts_code="601857.SH", start_date="20250101", end_date="20260330")
petrochina_h = pro.hk_daily(ts_code="0857.HK", start_date="20250101", end_date="20260330")

# AH Premium Index (HSAHP) available through Tushare or Eastmoney
```

## Output Format

```
## Cross-Listing Analysis — [Company Name]

### Listing Structure
- **A-share**: [code] @ [price CNY]
- **H-share**: [code] @ [price HKD]

### Premium/Discount
- **AH Premium**: [X%] (12m avg: X%, z-score: X.X)
- **Direction**: [AH premium widening / narrowing / stable]

### Valuation Comparison
| Metric | A-share | H-share |
|--------|---------|---------|
| PE (TTM) | XX.X | XX.X |
| PB | X.X | X.X |
| Dividend yield | X.X% | X.X% |

### Arbitrage Signal
- **AH premium z-score**: [X.X] → [fade premium / neutral / buy premium]
- **Best market to buy**: [A / H] — rationale
- **Catalyst**: [index inclusion, Connect eligibility, earnings]

### Investment Implication
- **Preferred listing**: [H-share / A-share] for new position
- **Risk**: [FX, regulatory, liquidity]
```

## Notes

- AH premium arbitrage is not freely executable: A-shares and H-shares are NOT fungible (no direct conversion), so true arbitrage requires separate capital pools
- Currency risk (CNY/HKD) is a major driver of AH premiums; always hedge or account for FX when comparing
- Stock Connect eligibility requirements mean not all HK-listed Chinese companies are accessible to mainland investors
- This framework is for research purposes only and does not constitute investment advice
