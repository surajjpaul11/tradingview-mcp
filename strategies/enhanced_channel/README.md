# Enhanced Channel Strategy

A multi-timeframe linear regression channel strategy engineered to capture tactical swing bounces at channel boundaries while filtering for macro regime alignment and enforcing disciplined stopgap risk management.

---

## Strategy Thesis & Concepts

Many channel trading strategies fail because they treat channels as static horizontal lines or fail to account for higher-timeframe trend context. The **Enhanced Channel Strategy** solves this via three coordinated time horizons:

1. **Tactical Channel (3-Month / ~63 trading days)**:
   - Dynamic rolling Linear Regression Channel with Standard Error envelopes (default $2.0\times$ multiplier).
   - Generates tactical buy entries at support and take-profit exits at resistance.
2. **Intermediate Channel (1-Year / ~252 trading days)**:
   - Tracks intermediate trend direction, channel slope, and relative range percentile ($0\% - 100\%$).
   - Guards against taking tactical bounce buys during severe intermediate cyclical downtrends.
3. **Macro Channel (5-Year / ~1260 trading days)**:
   - Establishes secular accumulation vs. euphoria/distribution regimes.

---

## Core Trading Rules

```
Upper Channel Line ─────────────▲ Top Boundary (Take Profit Target)
  ▲ 5% Top Leeway Zone          │ Rejection candle (close < open, close < prev_close) exits trade
──┴─────────────────────────────▼

         Midline ─────────────── Linear Regression Trend Center

──┬─────────────────────────────▲
  ▼ 5% Bottom Leeway Zone       │ Bounce candle (close > open, close > prev_close) enters trade
Lower Channel Line ─────────────▼
  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ Stopgap Level (Lower Channel - 5% Margin) -> Immediate Stop Loss Exit
```

### 1. Tactical Buy Entry
- **Zone Touch**: Price low penetrates into the **5% Bottom Leeway Zone** (between Lower Channel Line and Lower Channel $+ 5\%$ of Channel Height).
- **Bounce Confirmation**: The bar closes green (`close > open`) and reverses upward (`close > prev_close` and `close > Lower Channel`).
- **Higher Timeframe Filter**: Bounces are permitted only if the 1-Year intermediate slope is non-negative or price is in the lower half of its 1-Year channel.
- **Confluence Grade A**: When a 3-Month bottom bounce occurs while price is also in the lower $30\%$ of its 1-Year channel, the setup is classified as **High Confluence**.

### 2. Tactical Take Profit Exit (Channel Top Bounce)
- **Target Reach**: Price high or close enters the **5% Top Leeway Zone** (within $5\%$ of the Upper Channel Line).
- **Downward Rejection**: A reversal bar prints (`close < open` and `close < prev_close`), confirming rejection off upper resistance.

### 3. Stopgap Risk Protection (Ratcheting Stop Loss)
- **Initial Stop**: Established at `Lower Channel - 5% Stopgap Margin` upon entry.
- **Ratchet Mechanism**: As the regression channel rises in an uptrend, the stop loss ratchets upward, never lowering. If price closes or drops below the ratcheted stop level, the position is immediately closed.

---

## File Deliverables

| File | Type | Description |
|------|------|-------------|
| `enhanced_channel_strategy.py` | Standalone Python | Full backtester with Yahoo Finance fetching, CLI parameters, JSON export, and TradingView Lightweight Chart HTML generator. |
| `enhanced_channel_strategy.pine` | Pine Script v6 | Native TradingView strategy with visual channel fills, leeway zones, ratchet stop plotting, and alerts. |
| `README.md` | Documentation | Complete strategy guide and mathematical formulation. |

---

## Python CLI Usage

```bash
# Run 5-year backtest on SPY with interactive HTML chart export
python strategies/enhanced_channel/enhanced_channel_strategy.py --symbol SPY --period 5y --chart

# Run 2-year backtest on NVDA
python strategies/enhanced_channel/enhanced_channel_strategy.py --symbol NVDA --period 2y --chart

# Customize channel multiplier and leeway tolerance
python strategies/enhanced_channel/enhanced_channel_strategy.py --symbol QQQ --period 5y --channel-mult 2.2 --leeway 0.06 --stopgap 0.04

# Run on Crypto (BTC-USD)
python strategies/enhanced_channel/enhanced_channel_strategy.py --symbol BTC-USD --period 2y --chart
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--symbol` | `SPY` | Ticker symbol from Yahoo Finance |
| `--period` | `5y` | Lookback period: `1y`, `2y`, `5y`, `max` |
| `--interval` | `1d` | Bar interval (`1d` recommended) |
| `--tactical-lb` | `63` | Lookback bars for 3-Month Tactical channel |
| `--intermediate-lb` | `252` | Lookback bars for 1-Year Intermediate channel |
| `--macro-lb` | `1260` | Lookback bars for 5-Year Macro channel |
| `--channel-mult` | `2.0` | Standard Error multiplier for channel envelope |
| `--leeway` | `0.05` | 5% boundary leeway buffer fraction |
| `--stopgap` | `0.05` | 5% buffer below lower line for emergency stop |
| `--no-htf-filter` | `False` | Disable 1-Year trend/regime filtering |
| `--chart` | `False` | Generate self-contained HTML chart with Lightweight Charts |

---

## Pine Script v6 Integration

To use in TradingView:
1. Open TradingView Pine Editor.
2. Paste the contents of `strategies/enhanced_channel/enhanced_channel_strategy.pine`.
3. Click **Add to Chart**.
4. Adjust parameters (leeway %, stopgap %, channel lookback) directly in the indicator settings menu.
