# TradingView MCP — Project Memory

## Overview
TradingView MCP server with multiple trading strategies, backtesting engine, and live trade execution (Bitget + Alpaca).

## Strategies (newest first)
1. **Smart Hold** — VIX-based smart buy & hold; exits on confirmed downturns, re-enters at peak fear. Adaptive volatility exit sensitivity (ATR-classified).
2. **Curved Channels** — Polynomial regression channel strategy with interactive visualizer.
3. **EMA 21** — EMA 21 crossover strategy with interactive UI dashboard.
4. **Enhanced Straight Lines** — Channel bounce strategy with volume-weighted sizing, trend hysteresis, and dynamic capital sizing.
5. **Straight Line** — Trendline break strategy.
6. **VWMA 17** — VWMA 17 strategy with ATR-based SL/TP and adaptive ER trend filter.
7. **Higher Highs MTF** — Multi-timeframe higher highs structure strategy with adaptive ER trend filter.
8. **Buy and Protect** — Protective strategy implementation.
9. **Volatility Harvester** — Multi-symbol volatility strategy with indicators, engine, metrics, and backtest pipeline.

## Infrastructure
- **Backtesting engine** with per-strategy JSON result output and interactive HTML chart generation
- **Live trade execution** via Bitget (crypto) and Alpaca (equities)
- **Signal detection** with SQLite trade journal for tracking
- **Shared visualizer** (`strategies/visualize.py`) using TradingView Lightweight Charts CDN

## Development
- Work happens on feature branches off main
- User is actively iterating on and fine-tuning trading logic across strategies
