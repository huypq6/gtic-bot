# Ichimoku Kinko Hyo — One-Glance Equilibrium Chart

> School: **Trend-following** (multi-indicator). Suggested timeframe: 1h–1d. Needs a lot of data (≥ 78 candles).

## Versions
- **v1** (`ichimoku.py`) — raw: enters on cross + cloud, exits when the signal reverses. NO stop-loss → holds trades for a long time.
- **v2** (`ichimoku_v2.py`) — v1 + **ATR trailing stop** (`atr_mult`) to rein in max DD while still letting profits run with the trend.

### Research (strategy-research skill)
- **v1 sweep** (`scripts/sweep_ichimoku.py`): good config `conv=9 base=52 span_b=52` → average PnL +15% (3/4 markets),
  win ~36% BUT **maxDD 33–70%** → too high for the low-DD goal.
- **v2 trailing**: clearly cuts DD but is a double-edged sword (also cuts big winners). Small `atr_mult` = low DD
  but cuts trend PnL; needs a sweep + walk-forward to settle.
- **Timeframe (decision)**: ichimoku v2 trail×2, config conv9/base52/spanB52, exact windows:
  - **15m: HEAVILY NEGATIVE** (BTC −15.6%, ETH −23.3%; 56–66 whipsaw trades) → do NOT use 15m.
  - **1h: BTC +26.8%, win 45%, maxDD 7.1%** (hits all 3 goals in-sample); ETH −1.9%.
  - 4h: BTC +31% (DD 15.6%), ETH +9.3% (DD 35.7%) — profitable but high DD.
  - ⇒ Trend-following needs long trends: run on **1h/4h**, the complete opposite of ict_po3 (intraday 15m).
- **v2 sweep (1h/4h)**: most robust config `conv=9 base=26 span_b=104 trail×2` → average PnL **+28.7%**, 4/4 markets
  positive, win 38% BUT **maxDD 28.2%** → fails the low-DD goal. SHELVED FOR NOW (no walk-forward yet) — ict_po3 v4
  prioritized as requested; if revisiting: first needs a further DD-reduction mechanism (e.g. ATR-based position sizing).

## Idea

Ichimoku (Goichi Hosoda) combines several components into a "see it at a glance" system for trend, support/resistance and momentum. Signals are strong when **multiple components agree**.

## Components

| Line | Formula |
|---|---|
| **Tenkan-sen** (conversion) | (HH + LL) / 2 over `conv` candles (9) |
| **Kijun-sen** (base) | (HH + LL) / 2 over `base` candles (26) |
| **Senkou Span A** | (Tenkan + Kijun) / 2, plotted `base` candles ahead |
| **Senkou Span B** | (HH + LL) / 2 over `span_b` candles (52), plotted `base` candles ahead |
| **Cloud (Kumo)** | the area between Span A and Span B |

## Entry/exit rules (the version used here)

| Condition | Action |
|---|---|
| Tenkan crosses **ABOVE** Kijun **AND** price is **above** the cloud | **BUY** (LONG) |
| Tenkan crosses **BELOW** Kijun **AND** price is **below** the cloud | **SELL** (SHORT) |

The cloud filter ensures entries only follow the main trend → fewer false signals.

## Parameters

| Param | Default | Meaning |
|---|---|---|
| `conv` | 9 | Tenkan period. |
| `base` | 26 | Kijun period + cloud displacement. |
| `span_b` | 52 | Senkou Span B period. |
| `size` | 0.001 | Position size. |

## Pros / Cons

- ✅ Multi-layer filter (cross + cloud) → quality signals, little noise.
- ✅ Support/resistance zones (the cloud) are visible at a glance.
- ❌ Lagging; needs a lot of data; parameters are sensitive to the timeframe.

## When to use

- Trending markets, medium–long timeframes. A good trend filter to combine with other strategies.

## Backtest notes

- Needs enough history (≥ span_b + base candles) for each decision.
- A Chikou Span (lagging price) condition can be added for stricter entries.
