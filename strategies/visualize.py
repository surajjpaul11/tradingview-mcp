"""
Backtest Chart Generator — Self-contained HTML with TradingView Lightweight Charts
===================================================================================

Generates interactive candlestick charts from backtest results with:
  - OHLCV candlestick data
  - Buy/sell trade markers at entry/exit points
  - Optional overlays: channel curves, trendlines, touch points

Usage:
    from strategies.visualize import generate_chart_html

    html_path = generate_chart_html(
        result=backtest_result_dict,
        candles=ohlcv_candle_list,
        output_path=Path("my_chart.html"),
    )

The output is a single self-contained HTML file (no server needed).
Lightweight Charts loaded via CDN.

Requires: no external dependencies (pure stdlib)
"""
from __future__ import annotations

import json
from pathlib import Path

# Abbreviation maps for chart marker text
ENTRY_ABBREV = {
    "channel_long": "CH-LONG", "channel_short": "CH-SHORT",
    "breakout_long": "BRK-UP", "breakout_short": "BRK-DN",
    "fallback_sma": "SMA", "breakout_reentry": "RE-BRK",
    "break_short": "BRK-SH", "sma_to_channel": "SMA\u2192CH",
    "early_momentum": "EARLY", "sharp_reversal_long": "REV-UP",
    "sharp_reversal_short": "REV-DN", "momentum_to_channel": "EARLY\u2192CH",
    "reversal_to_channel": "REV\u2192CH",
    "vol_divergence_long": "DIV-UP", "vol_divergence_short": "DIV-DN",
    "divergence_to_channel": "DIV\u2192CH",
    "waterfall_long": "WF-UP", "waterfall_short": "WF-DN",
    "waterfall_to_channel": "WF\u2192CH",
    # Smart Hold entries
    "initial_entry": "INIT", "vix_extreme_fear": "VIX-FEAR",
    "vix_fear_declining": "VIX-DEC", "ma_reclaim": "MA-RCL",
    "rsi_oversold_bounce": "RSI-BNC", "ema_momentum": "EMA-MOM",
    "quick_reentry": "QUICK",
    "volume_capitulation": "VOL-CAP",
}
EXIT_ABBREV = {
    "atr_trailing_stop": "ATR-TS", "channel_trail_stop": "CH-TS",
    "breakout_up": "BRK-UP", "breakout_down": "BRK-DN",
    "channel_break": "CH-BRK", "channel_flip": "CH-FLIP",
    "channel_expired": "CH-EXP", "time_exit": "TIME",
    "fallback_sma_exit": "SMA-X", "end_of_data": "EOD",
    # Smart Hold exits
    "ma_breakdown": "MA-BRK", "vix_accelerated_exit": "VIX-X",
    "trailing_stop": "TRAIL",
}


def generate_chart_html(
    result: dict,
    candles: list[dict],
    output_path: Path,
    strategy_versions: dict | None = None,
    vix_candles: list[dict] | None = None,
) -> Path:
    """
    Generate a self-contained HTML chart file.

    Args:
        result: backtest result dict (from run_backtest()), must include trade_log.
                Optionally includes "overlays" list.
        candles: raw OHLCV candle list (from fetch_ohlcv())
        output_path: where to write the HTML file
        strategy_versions: optional dict of version tags to (label, description, type) tuples
        vix_candles: optional VIX OHLCV candle list for VIX overlay

    Returns:
        Path to the written HTML file.
    """
    # Convert candles to Lightweight Charts format + volume data
    candles_lw = []
    volume_data = []
    for c in candles:
        entry = {
            "open": c["open"], "high": c["high"],
            "low": c["low"], "close": c["close"],
        }
        # Daily format "YYYY-MM-DD" works directly; intraday needs Unix timestamp
        date_str = c["date"]
        if " " in date_str:
            entry["time"] = date_str
        else:
            entry["time"] = date_str
        candles_lw.append(entry)
        is_up = c["close"] >= c["open"]
        volume_data.append({
            "time": date_str,
            "value": c.get("volume", 0),
            "color": "rgba(38,166,154,0.5)" if is_up else "rgba(239,83,80,0.5)",
        })

    # Build trade markers — distinct colors per entry/exit type
    # Buy/cover colours: shades of green and blue
    BUY_COLORS = {
        "channel_long": "#26a69a",       # teal (channel)
        "sma_to_channel": "#26a69a",     # teal (channel upgrade)
        "fallback_sma": "#4CAF50",       # green (SMA)
        "breakout_long": "#00E676",      # bright green (breakout)
        "breakout_reentry": "#00E676",   # bright green (breakout re-entry)
        "early_momentum": "#2196F3",     # blue (poly-low)
        "momentum_to_channel": "#2196F3",# blue (poly-low upgrade)
        "sharp_reversal_long": "#00BCD4",# cyan (reversal)
        "reversal_to_channel": "#00BCD4",# cyan (reversal upgrade)
        "vol_divergence_long": "#7C4DFF", # purple (divergence)
        "divergence_to_channel": "#7C4DFF",# purple (divergence upgrade)
        "waterfall_long": "#FF6D00",     # deep orange (waterfall recovery)
        "waterfall_to_channel": "#FF6D00",# deep orange (waterfall upgrade)
        # Smart Hold entries
        "initial_entry": "#26a69a",      # teal
        "vix_extreme_fear": "#7C4DFF",   # purple (fear buy)
        "vix_fear_declining": "#B388FF", # violet (fear declining buy)
        "ma_reclaim": "#4CAF50",         # green (trend resume)
        "rsi_oversold_bounce": "#2196F3",# blue (oversold bounce)
        "ema_momentum": "#00BCD4",       # cyan (momentum)
        "quick_reentry": "#7C4DFF",      # purple (quick re-entry)
        "volume_capitulation": "#E040FB", # magenta-pink (capitulation buy)
    }
    # Sell/short colours: shades of red and orange
    SELL_COLORS = {
        "channel_short": "#ef5350",      # red (channel)
        "breakout_short": "#FF5722",     # deep orange (breakout)
        "break_short": "#FF9800",        # orange (break-flip)
        "sharp_reversal_short": "#E91E63",# pink (reversal)
        "vol_divergence_short": "#AB47BC",# magenta (divergence)
        "waterfall_short": "#D500F9",    # bright magenta (waterfall short)
    }
    EXIT_COLORS = {
        "atr_trailing_stop": "#ef5350",  # red
        "channel_trail_stop": "#FF7043", # deep orange
        "channel_break": "#FF9800",      # orange
        "breakout_up": "#FF5722",        # deep orange
        "breakout_down": "#FF5722",      # deep orange
        "fallback_sma_exit": "#FFAB40",  # amber
        "channel_expired": "#FFD54F",    # yellow-amber
        "time_exit": "#FFAB40",          # amber
        "channel_flip": "#FF9800",       # orange
        "end_of_data": "#BDBDBD",        # grey
        # Smart Hold exits
        "ma_breakdown": "#ef5350",       # red
        "vix_accelerated_exit": "#FF7043", # deep orange
        "trailing_stop": "#FF5722",      # deep orange
    }
    COVER_COLORS = {
        "atr_trailing_stop": "#26a69a",  # teal
        "time_exit": "#4CAF50",          # green
        "channel_flip": "#66BB6A",       # light green
    }

    trades = result.get("trade_log", [])
    markers = []
    for t in trades:
        side = t.get("side", "long")
        entry_reason = t.get("entry_reason", "")
        entry_abbrev = ENTRY_ABBREV.get(entry_reason, entry_reason.upper().replace("_", "-"))
        exit_reason = t.get("exit_reason", "")
        exit_abbrev = EXIT_ABBREV.get(exit_reason, exit_reason.upper().replace("_", "-"))
        # Entry marker
        if side == "long":
            markers.append({
                "time": t["entry_date"],
                "position": "belowBar",
                "color": BUY_COLORS.get(entry_reason, "#26a69a"),
                "shape": "arrowUp",
                "text": f"BUY {entry_abbrev}",
            })
        else:
            markers.append({
                "time": t["entry_date"],
                "position": "aboveBar",
                "color": SELL_COLORS.get(entry_reason, "#ef5350"),
                "shape": "arrowDown",
                "text": f"SHORT {entry_abbrev}",
            })
        # Exit marker
        if side == "long":
            markers.append({
                "time": t["exit_date"],
                "position": "aboveBar",
                "color": EXIT_COLORS.get(exit_reason, "#ef5350"),
                "shape": "arrowDown",
                "text": f"EXIT {exit_abbrev}",
            })
        else:
            markers.append({
                "time": t["exit_date"],
                "position": "belowBar",
                "color": COVER_COLORS.get(exit_reason, "#26a69a"),
                "shape": "arrowUp",
                "text": f"COVER {exit_abbrev}",
            })

    # Add B&H markers if present
    for bm in result.get("bnh_markers", []):
        markers.append(bm)

    # Sort markers by time (required by Lightweight Charts)
    markers.sort(key=lambda m: m["time"])

    # Build overlays
    overlays = result.get("overlays", [])

    # Meta info for stats header
    meta = {
        "symbol": result.get("symbol", ""),
        "strategy": result.get("strategy", ""),
        "strategy_label": result.get("strategy_label", ""),
        "period": result.get("period", ""),
        "interval": result.get("interval", ""),
        "total_return_pct": result.get("total_return_pct", 0),
        "buy_and_hold_return_pct": result.get("buy_and_hold_return_pct", 0),
        "vs_buy_and_hold_pct": result.get("vs_buy_and_hold_pct", 0),
        "total_trades": result.get("total_trades", 0),
        "win_rate_pct": result.get("win_rate_pct", 0),
        "profit_factor": result.get("profit_factor", 0),
        "sharpe_ratio": result.get("sharpe_ratio", 0),
        "max_drawdown_pct": result.get("max_drawdown_pct", 0),
        "final_capital": result.get("final_capital", 0),
        "initial_capital": result.get("initial_capital", 0),
    }

    # Build versions dict for legend: {tag: {label, description, type}}
    versions_for_html = {}
    if strategy_versions:
        for tag, (label, desc, mtype) in strategy_versions.items():
            versions_for_html[tag] = {"label": label, "description": desc, "type": mtype}

    # Build VIX line data for overlay
    vix_line_data = []
    if vix_candles:
        for vc in vix_candles:
            vix_line_data.append({"time": vc["date"], "value": round(vc["close"], 2)})

    html = _HTML_TEMPLATE
    html = html.replace("__CANDLES_JSON__", json.dumps(candles_lw))
    html = html.replace("__MARKERS_JSON__", json.dumps(markers))
    html = html.replace("__OVERLAYS_JSON__", json.dumps(overlays))
    html = html.replace("__VOLUME_JSON__", json.dumps(volume_data))
    html = html.replace("__META_JSON__", json.dumps(meta))
    html = html.replace("__TRADES_JSON__", json.dumps(trades))
    html = html.replace("__VERSIONS_JSON__", json.dumps(versions_for_html))
    html = html.replace("__VIX_JSON__", json.dumps(vix_line_data))

    output_path.write_text(html, encoding="utf-8")
    return output_path


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Backtest Chart</title>
<script src="https://unpkg.com/lightweight-charts@3.8.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #131722;
    color: #d1d4dc;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    overflow: hidden;
    height: 100vh;
    display: flex;
    flex-direction: column;
}
#header {
    padding: 12px 20px;
    background: #1e222d;
    border-bottom: 1px solid #2a2e39;
    flex-shrink: 0;
}
#header h1 {
    font-size: 16px;
    font-weight: 600;
    color: #e0e3eb;
    margin-bottom: 8px;
}
#stats {
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
}
.stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.stat-label {
    font-size: 10px;
    color: #787b86;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.stat-value {
    font-size: 14px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}
.stat-value.positive { color: #26a69a; }
.stat-value.negative { color: #ef5350; }
.stat-value.neutral  { color: #d1d4dc; }
#toolbar-buttons {
    position: absolute;
    top: 12px;
    right: 20px;
    display: flex;
    gap: 8px;
    z-index: 10;
}
.toolbar-btn {
    background: #2a2e39;
    color: #d1d4dc;
    border: 1px solid #363a45;
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
}
.toolbar-btn:hover { background: #363a45; }
.toolbar-btn.active { background: #363a45; border-color: #d1d4dc; }
#legend-panel {
    display: none;
    position: absolute;
    top: 0;
    right: 0;
    width: 560px;
    height: 100%;
    background: #1e222d;
    border-right: 1px solid #2a2e39;
    z-index: 5;
    overflow-y: auto;
    padding: 16px;
    font-size: 12px;
}
#legend-panel.visible { display: block; }
#legend-panel h3 {
    color: #e0e3eb;
    margin-bottom: 12px;
    font-size: 14px;
}
#legend-panel h4 {
    color: #e0e3eb;
    margin: 16px 0 8px;
    font-size: 12px;
    padding-bottom: 4px;
    border-bottom: 1px solid #2a2e39;
}
#legend-panel table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 8px;
    font-size: 11px;
}
#legend-panel th {
    text-align: left;
    padding: 5px 8px;
    background: #131722;
    color: #787b86;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    font-size: 10px;
    border-bottom: 1px solid #2a2e39;
}
#legend-panel td {
    padding: 5px 8px;
    border-bottom: 1px solid #1e222d;
    vertical-align: top;
    color: #9598a1;
}
#legend-panel tr:hover { background: rgba(42,46,57,0.4); }
.lp-marker {
    font-family: 'SF Mono', Menlo, Consolas, monospace;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 3px;
    white-space: nowrap;
    display: inline-block;
}
.lp-marker.buy { background: rgba(38,166,154,0.15); color: #26a69a; }
.lp-marker.sell { background: rgba(239,83,80,0.15); color: #ef5350; }
.lp-abbrev {
    font-family: 'SF Mono', Menlo, Consolas, monospace;
    font-weight: 700;
    font-size: 11px;
    white-space: nowrap;
}
.lp-abbrev.entry { color: #26a69a; }
.lp-abbrev.exit { color: #ef5350; }
.lp-name { color: #d1d4dc; white-space: nowrap; }
.lp-desc { color: #9598a1; }
.lp-vtag-pill {
    display: inline-block;
    font-family: 'SF Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 3px;
    margin: 1px 2px;
}
.lp-vtag-pill.entry { background: rgba(77,208,225,0.15); color: #4dd0e1; }
.lp-vtag-pill.exit { background: rgba(255,183,77,0.15); color: #ffb74d; }
.lp-vtag-plain { color: #787b86; font-size: 10px; }
.lp-vtype { color: #787b86; font-size: 10px; }
#chart-container {
    flex: 1;
    position: relative;
}
#trade-log-panel {
    display: none;
    position: absolute;
    top: 0;
    right: 0;
    width: 560px;
    height: 100%;
    background: #1e222d;
    border-left: 1px solid #2a2e39;
    z-index: 5;
    overflow-y: auto;
    padding: 12px;
    font-size: 12px;
}
#trade-log-panel.visible { display: block; }
#trade-log-panel h3 {
    color: #e0e3eb;
    margin-bottom: 8px;
    font-size: 13px;
}
.trade-row {
    padding: 6px 0;
    border-bottom: 1px solid #2a2e39;
    font-variant-numeric: tabular-nums;
}
.trade-row-main {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.trade-row .side { width: 50px; font-weight: 600; display: inline-block; }
.trade-row .side.long { color: #26a69a; }
.trade-row .side.short { color: #ef5350; }
.trade-row .entry-type { color: #d1d4dc; margin-left: 4px; font-size: 11px; }
.trade-row .dates { color: #787b86; flex: 1; margin: 0 8px; }
.trade-row .pnl { width: 70px; text-align: right; font-weight: 600; }
.trade-row .pnl.positive { color: #26a69a; }
.trade-row .pnl.negative { color: #ef5350; }
.trade-row .reason { width: 90px; text-align: right; color: #787b86; font-size: 11px; }
.trade-row-versions {
    font-size: 10px;
    color: #787b86;
    margin-top: 2px;
    padding-left: 54px;
}
.trade-row-versions .entry-ver { color: #4dd0e1; }
.trade-row-versions .exit-ver { color: #ffb74d; }
#legend {
    position: absolute;
    top: 12px;
    left: 12px;
    display: flex;
    gap: 16px;
    z-index: 5;
    font-size: 11px;
    background: rgba(19,23,34,0.85);
    padding: 6px 12px;
    border-radius: 4px;
}
.legend-item {
    display: flex;
    align-items: center;
    gap: 4px;
}
.legend-swatch {
    width: 12px;
    height: 3px;
    border-radius: 1px;
}
#version-legend {
    position: absolute;
    bottom: 12px;
    left: 12px;
    z-index: 6;
    background: rgba(30,34,45,0.95);
    border: 1px solid #363a45;
    border-radius: 6px;
    font-size: 11px;
    max-width: 480px;
    overflow: hidden;
}
#version-legend-header {
    padding: 6px 12px;
    cursor: pointer;
    color: #e0e3eb;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 6px;
    user-select: none;
}
#version-legend-header:hover { background: rgba(54,58,69,0.5); }
#version-legend-body {
    display: none;
    padding: 4px 12px 8px;
}
#version-legend-body.open { display: block; }
.ver-row {
    display: inline-flex;
    align-items: baseline;
    gap: 4px;
    padding: 2px 8px 2px 0;
    min-width: 200px;
}
.ver-tag { color: #4dd0e1; font-weight: 600; min-width: 28px; }
.ver-label { color: #d1d4dc; }
.ver-desc { color: #787b86; font-size: 10px; }
</style>
</head>
<body>
<div id="header">
    <h1 id="title"></h1>
    <div id="stats"></div>
</div>
<div id="toolbar-buttons">
    <button id="vix-toggle" class="toolbar-btn" onclick="toggleVix()" style="display:none">VIX</button>
    <button id="legend-toggle" class="toolbar-btn" onclick="toggleLegendPanel()">Legend</button>
    <button id="trade-log-toggle" class="toolbar-btn" onclick="toggleTradeLog()">Trade Log</button>
</div>
<div id="chart-container">
    <div id="legend-panel">
        <h3>Chart Legend Reference</h3>
        <div id="legend-panel-body"></div>
    </div>
    <div id="trade-log-panel">
        <h3>Trade Log</h3>
        <div id="trade-log-body"></div>
    </div>
    <div id="legend"></div>
    <div id="version-legend">
        <div id="version-legend-header" onclick="toggleVersionLegend()">
            <span id="ver-arrow">\u25B6</span> Strategy Versions
        </div>
        <div id="version-legend-body"></div>
    </div>
</div>

<script>
const CANDLES = __CANDLES_JSON__;
const MARKERS = __MARKERS_JSON__;
const OVERLAYS = __OVERLAYS_JSON__;
const VOLUME = __VOLUME_JSON__;
const META = __META_JSON__;
const VERSIONS = __VERSIONS_JSON__;
const VIX_DATA = __VIX_JSON__;

// --- Time conversion ---
function parseTime(dateStr) {
    if (dateStr.includes(' ')) {
        // Intraday: "2024-01-15 14:00" -> Unix timestamp (UTC)
        return Math.floor(new Date(dateStr.replace(' ', 'T') + ':00Z').getTime() / 1000);
    }
    return dateStr; // Daily: "2024-01-15" works directly
}

// Convert all time fields
CANDLES.forEach(c => c.time = parseTime(c.time));
MARKERS.forEach(m => m.time = parseTime(m.time));
OVERLAYS.forEach(o => {
    if (o.points) o.points.forEach(p => p.time = parseTime(p.time));
});
VOLUME.forEach(v => v.time = parseTime(v.time));
VIX_DATA.forEach(v => v.time = parseTime(v.time));

// --- Header ---
document.getElementById('title').textContent =
    META.strategy_label + ' \u2014 ' + META.symbol + ' (' + META.period + ', ' + META.interval + ')';

function statClass(val) {
    if (val > 0) return 'positive';
    if (val < 0) return 'negative';
    return 'neutral';
}

const statsHTML = [
    { label: 'Total Return', value: META.total_return_pct.toFixed(2) + '%', cls: statClass(META.total_return_pct) },
    { label: 'Buy & Hold', value: META.buy_and_hold_return_pct.toFixed(2) + '%', cls: statClass(META.buy_and_hold_return_pct) },
    { label: 'vs B&H', value: (META.vs_buy_and_hold_pct >= 0 ? '+' : '') + META.vs_buy_and_hold_pct.toFixed(2) + '%', cls: statClass(META.vs_buy_and_hold_pct) },
    { label: 'Trades', value: META.total_trades, cls: 'neutral' },
    { label: 'Win Rate', value: META.win_rate_pct + '%', cls: META.win_rate_pct >= 50 ? 'positive' : 'negative' },
    { label: 'Profit Factor', value: META.profit_factor, cls: META.profit_factor >= 1 ? 'positive' : 'negative' },
    { label: 'Sharpe', value: META.sharpe_ratio, cls: statClass(META.sharpe_ratio) },
    { label: 'Max DD', value: META.max_drawdown_pct + '%', cls: 'negative' },
    { label: 'Final Capital', value: '$' + META.final_capital.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}), cls: statClass(META.final_capital - META.initial_capital) },
].map(s =>
    '<div class="stat"><span class="stat-label">' + s.label + '</span>' +
    '<span class="stat-value ' + s.cls + '">' + s.value + '</span></div>'
).join('');
document.getElementById('stats').innerHTML = statsHTML;

// --- Chart ---
const container = document.getElementById('chart-container');
const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    layout: {
        background: { type: 'solid', color: '#131722' },
        textColor: '#d1d4dc',
    },
    grid: {
        vertLines: { color: '#1e222d' },
        horzLines: { color: '#1e222d' },
    },
    crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
    },
    rightPriceScale: {
        borderColor: '#2a2e39',
    },
    timeScale: {
        borderColor: '#2a2e39',
        timeVisible: CANDLES.length > 0 && typeof CANDLES[0].time === 'number',
    },
});

const candleSeries = chart.addCandlestickSeries({
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderUpColor: '#26a69a',
    borderDownColor: '#ef5350',
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350',
});
candleSeries.setData(CANDLES);

// --- Volume Histogram ---
const volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'volume',
    scaleMargins: { top: 0.8, bottom: 0 },
});
chart.priceScale('volume').applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
});
volumeSeries.setData(VOLUME);

// --- VIX Overlay (separate right price scale) ---
let vixSeries = null;
let vixVisible = false;
if (VIX_DATA.length > 0) {
    document.getElementById('vix-toggle').style.display = '';
    vixSeries = chart.addLineSeries({
        color: '#FF9800',
        lineWidth: 2,
        lastValueVisible: true,
        priceLineVisible: false,
        crosshairMarkerVisible: true,
        priceScaleId: 'vix',
        title: 'VIX',
        visible: false,
    });
    chart.priceScale('vix').applyOptions({
        scaleMargins: { top: 0.05, bottom: 0.3 },
        borderVisible: true,
        borderColor: '#FF9800',
        textColor: '#FF9800',
        visible: false,
    });
    vixSeries.setData(VIX_DATA);

    // Add horizontal lines at key VIX levels
    vixSeries.createPriceLine({ price: 25, color: 'rgba(255,152,0,0.3)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'VIX Exit Boost' });
    vixSeries.createPriceLine({ price: 30, color: 'rgba(255,87,34,0.3)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'VIX Fear' });
    vixSeries.createPriceLine({ price: 35, color: 'rgba(244,67,54,0.3)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'VIX Extreme' });
}

function toggleVix() {
    if (!vixSeries) return;
    vixVisible = !vixVisible;
    document.getElementById('vix-toggle').classList.toggle('active', vixVisible);
    vixSeries.applyOptions({ visible: vixVisible });
    chart.priceScale('vix').applyOptions({ visible: vixVisible });
}

// --- Trade Markers ---
if (MARKERS.length > 0) {
    candleSeries.setMarkers(MARKERS);
}

// --- Overlays ---
const legendEl = document.getElementById('legend');
let legendHTML = '';

OVERLAYS.forEach(overlay => {
    if (overlay.type === 'line' && overlay.points && overlay.points.length > 1) {
        const lineSeries = chart.addLineSeries({
            color: overlay.color || '#787b86',
            lineWidth: overlay.lineWidth || 2,
            lineStyle: overlay.lineStyle || 0,
            lastValueVisible: false,
            priceLineVisible: false,
            crosshairMarkerVisible: false,
        });
        lineSeries.setData(overlay.points);

        if (overlay.label) {
            legendHTML += '<div class="legend-item">' +
                '<div class="legend-swatch" style="background:' + overlay.color + '"></div>' +
                '<span>' + overlay.label + '</span></div>';
        }
    } else if (overlay.type === 'marker_points' && overlay.points && overlay.points.length > 0) {
        const ptSeries = chart.addLineSeries({
            color: 'rgba(0,0,0,0)',
            lineWidth: 0,
            lastValueVisible: false,
            priceLineVisible: false,
            crosshairMarkerVisible: false,
            pointMarkersVisible: false,
        });
        ptSeries.setData(overlay.points);

        // Draw circle markers using the series markers API
        const ptMarkers = overlay.points.map(p => ({
            time: p.time,
            position: 'inBar',
            color: overlay.color || '#FFFFFF',
            shape: 'circle',
            text: '',
            size: 1,
        }));
        ptSeries.setMarkers(ptMarkers);

        if (overlay.label) {
            legendHTML += '<div class="legend-item">' +
                '<div class="legend-swatch" style="background:' + (overlay.color || '#FFFFFF') +
                '; border-radius: 50%; width: 8px; height: 8px;"></div>' +
                '<span>' + overlay.label + '</span></div>';
        }
    }
});

legendEl.innerHTML = legendHTML;

// --- Side Panel Helpers (mutually exclusive — only one open at a time) ---
function getOpenPanelWidth() {
    const lp = document.getElementById('legend-panel');
    const tp = document.getElementById('trade-log-panel');
    if (lp.classList.contains('visible') || tp.classList.contains('visible')) return 560;
    return 0;
}
function resizeChart() {
    chart.applyOptions({ width: container.clientWidth - getOpenPanelWidth(), height: container.clientHeight });
}

// --- Legend Panel ---
function toggleLegendPanel() {
    const legend = document.getElementById('legend-panel');
    const tradeLog = document.getElementById('trade-log-panel');
    if (legend.classList.contains('visible')) {
        legend.classList.remove('visible');
    } else {
        tradeLog.classList.remove('visible');
        legend.classList.add('visible');
    }
    resizeChart();
}

// --- Trade Log Panel ---
function toggleTradeLog() {
    const legend = document.getElementById('legend-panel');
    const tradeLog = document.getElementById('trade-log-panel');
    if (tradeLog.classList.contains('visible')) {
        tradeLog.classList.remove('visible');
    } else {
        legend.classList.remove('visible');
        tradeLog.classList.add('visible');
    }
    resizeChart();
}

// Entry/exit reason display names
const ENTRY_NAMES = {
    'channel_long': 'Channel Long', 'channel_short': 'Channel Short',
    'breakout_long': 'Breakout Up', 'breakout_short': 'Breakout Down',
    'fallback_sma': 'SMA Fallback', 'breakout_reentry': 'Breakout Re-entry',
    'break_short': 'Break Short', 'sma_to_channel': 'SMA \u2192 Channel',
    'early_momentum': 'Poly-Low Entry', 'sharp_reversal_long': 'Sharp Reversal Long',
    'sharp_reversal_short': 'Sharp Reversal Short', 'momentum_to_channel': 'Poly-Low \u2192 Channel',
    'reversal_to_channel': 'Reversal \u2192 Channel',
    'vol_divergence_long': 'Vol Divergence Long', 'vol_divergence_short': 'Vol Divergence Short',
    'divergence_to_channel': 'Divergence \u2192 Channel',
    'waterfall_long': 'Waterfall Recovery Long', 'waterfall_short': 'Waterfall Short',
    'waterfall_to_channel': 'Waterfall \u2192 Channel',
    // Smart Hold
    'initial_entry': 'Initial Entry', 'vix_extreme_fear': 'VIX Extreme Fear',
    'vix_fear_declining': 'VIX Fear Declining', 'ma_reclaim': 'MA Reclaim',
    'rsi_oversold_bounce': 'RSI Oversold Bounce', 'ema_momentum': 'EMA Momentum',
    'quick_reentry': 'Quick Re-entry',
    'volume_capitulation': 'Volume Capitulation',
};

const tradeLogBody = document.getElementById('trade-log-body');
const TRADE_LOG = __TRADES_JSON__;
let tlHTML = '';
TRADE_LOG.forEach(t => {
    const pnlCls = (t.return_pct || 0) > 0 ? 'positive' : 'negative';
    const sideCls = t.side === 'long' ? 'long' : 'short';
    const entryName = ENTRY_NAMES[t.entry_reason] || (t.entry_reason||'unknown').replace(/_/g, ' ');
    const entryVers = (t.entry_versions || []).join(' ');
    const exitVers = (t.exit_versions || []).join(' ');
    tlHTML += '<div class="trade-row">' +
        '<div class="trade-row-main">' +
        '<span class="side ' + sideCls + '">' + t.side.toUpperCase() + '</span>' +
        '<span class="entry-type">' + entryName + '</span>' +
        '<span class="dates">' + (t.entry_date||'').substring(0,10) + ' \u2192 ' + (t.exit_date||'').substring(0,10) + '</span>' +
        '<span class="pnl ' + pnlCls + '">' + ((t.return_pct||0) >= 0 ? '+' : '') + (t.return_pct||0).toFixed(2) + '%</span>' +
        '<span class="reason">' + (t.exit_reason||'').replace(/_/g, ' ') + '</span>' +
        '</div>' +
        '<div class="trade-row-versions">' +
        '\u25B6 Entry: <span class="entry-ver">' + (entryVers || 'n/a') + '</span>' +
        ' &nbsp; Exit: <span class="exit-ver">' + (exitVers || 'n/a') + '</span>' +
        '</div>' +
        '</div>';
});
tradeLogBody.innerHTML = tlHTML || '<div style="color:#787b86">No trades</div>';

// --- Version Legend ---
function toggleVersionLegend() {
    const body = document.getElementById('version-legend-body');
    const arrow = document.getElementById('ver-arrow');
    body.classList.toggle('open');
    arrow.textContent = body.classList.contains('open') ? '\u25BC' : '\u25B6';
}

(function buildVersionLegend() {
    const body = document.getElementById('version-legend-body');
    const tags = Object.keys(VERSIONS).sort((a, b) => {
        const na = parseInt(a.replace('v',''), 10);
        const nb = parseInt(b.replace('v',''), 10);
        return na - nb;
    });
    if (tags.length === 0) {
        document.getElementById('version-legend').style.display = 'none';
        return;
    }
    document.getElementById('version-legend-header').innerHTML =
        '<span id="ver-arrow">\u25B6</span> Strategy Versions (v' +
        tags[tags.length - 1].replace('v','') + ')';
    let html = '';
    tags.forEach(tag => {
        const v = VERSIONS[tag];
        html += '<div class="ver-row">' +
            '<span class="ver-tag">' + tag + '</span>' +
            '<span class="ver-label">' + v.label + '</span>' +
            '<span class="ver-desc"> \u2014 ' + v.description + '</span>' +
            '</div>';
    });
    body.innerHTML = html;
})();

// --- Legend Panel Content (dynamic — built from all known marker types) ---
(function buildLegendPanel() {
    const body = document.getElementById('legend-panel-body');

    // Complete registry of all entry/exit types across all strategies
    // Colors match the chart marker colors exactly (BUY_COLORS / SELL_COLORS / EXIT_COLORS in Python)
    const ENTRY_REGISTRY = {
        // Curved Channels — buy entries (green-blue shades)
        'channel_long':          { abbrev: 'CH-LONG',    name: 'Channel Long',             desc: 'Price bouncing off ascending channel support with bullish close.', side: 'long', color: '#26a69a' },
        'sma_to_channel':        { abbrev: 'SMA\u2192CH',name: 'SMA to Channel',           desc: 'SMA fallback entry upgraded to channel-based exit management.', side: 'long', color: '#26a69a' },
        'fallback_sma':          { abbrev: 'SMA',        name: 'Fallback SMA',             desc: 'No channel active \u2014 price crossed above SMA(50) after cooldown.', side: 'long', color: '#4CAF50' },
        'breakout_long':         { abbrev: 'BRK-UP',     name: 'Breakout Long',            desc: 'Price broke above upper channel boundary. Captures explosive upside moves.', side: 'long', color: '#00E676' },
        'breakout_reentry':      { abbrev: 'RE-BRK',     name: 'Breakout Re-entry',        desc: 'Existing long broke above channel resistance. Re-opened at 200%.', side: 'long', color: '#00E676' },
        'early_momentum':        { abbrev: 'EARLY',      name: 'Poly-Low Entry',           desc: 'Polynomial through recent lows has positive slope + volume. 25% exploratory long.', side: 'long', color: '#2196F3' },
        'momentum_to_channel':   { abbrev: 'EARLY\u2192CH', name: 'Poly-Low \u2192 Channel', desc: 'Poly-low entry upgraded to channel management.', side: 'long', color: '#2196F3' },
        'sharp_reversal_long':   { abbrev: 'REV-UP',     name: 'Sharp Reversal Long',      desc: 'Large bullish bar (\u22652x ATR) with high volume after bearish bars.', side: 'long', color: '#00BCD4' },
        'reversal_to_channel':   { abbrev: 'REV\u2192CH',   name: 'Reversal \u2192 Channel', desc: 'Sharp reversal entry upgraded to channel management.', side: 'long', color: '#00BCD4' },
        'vol_divergence_long':   { abbrev: 'DIV-UP',     name: 'Vol Divergence Long',      desc: 'Price dropping with declining volume \u2014 bullish divergence.', side: 'long', color: '#7C4DFF' },
        'divergence_to_channel': { abbrev: 'DIV\u2192CH',   name: 'Divergence \u2192 Channel', desc: 'Volume divergence entry upgraded to channel management.', side: 'long', color: '#7C4DFF' },
        'waterfall_long':        { abbrev: 'WF-UP',      name: 'Waterfall Recovery Long',  desc: 'Waterfall recovery entry on long side.', side: 'long', color: '#FF6D00' },
        'waterfall_to_channel':  { abbrev: 'WF\u2192CH', name: 'Waterfall \u2192 Channel', desc: 'Waterfall entry upgraded to channel management.', side: 'long', color: '#FF6D00' },
        // Curved Channels — short entries (red-orange shades)
        'channel_short':         { abbrev: 'CH-SHORT',   name: 'Channel Short',            desc: 'Price rejecting off descending channel resistance with bearish close.', side: 'short', color: '#ef5350' },
        'breakout_short':        { abbrev: 'BRK-DN',     name: 'Breakout Short',           desc: 'Price broke below lower channel boundary.', side: 'short', color: '#FF5722' },
        'break_short':           { abbrev: 'BRK-SH',     name: 'Break Short',              desc: 'Long position flipped to short after channel breakdown.', side: 'short', color: '#FF9800' },
        'sharp_reversal_short':  { abbrev: 'REV-DN',     name: 'Sharp Reversal Short',     desc: 'Large bearish bar (\u22652x ATR) with high volume after bullish bars.', side: 'short', color: '#E91E63' },
        'vol_divergence_short':  { abbrev: 'DIV-DN',     name: 'Vol Divergence Short',     desc: 'Price rising with declining volume \u2014 bearish divergence.', side: 'short', color: '#AB47BC' },
        'waterfall_short':       { abbrev: 'WF-DN',      name: 'Waterfall Short',          desc: 'Waterfall short entry.', side: 'short', color: '#D500F9' },
        // Smart Hold entries (green-blue shades for buys)
        'initial_entry':         { abbrev: 'INIT',       name: 'Initial Entry',            desc: 'Buy on first bar \u2014 start fully invested like buy & hold.', side: 'long', color: '#26a69a' },
        'vix_extreme_fear':      { abbrev: 'VIX-FEAR',   name: 'VIX Extreme Fear',         desc: 'VIX \u2265 35 (extreme fear) + bullish candle. Peak panic buy signal.', side: 'long', color: '#7C4DFF' },
        'vix_fear_declining':    { abbrev: 'VIX-DEC',    name: 'VIX Fear Declining',       desc: 'VIX \u2265 30 but declining from peak \u2014 fear is peaking, enter on reversal.', side: 'long', color: '#B388FF' },
        'ma_reclaim':            { abbrev: 'MA-RCL',     name: 'MA Reclaim',               desc: 'Price reclaimed SMA with consecutive closes above + rising fast EMA.', side: 'long', color: '#4CAF50' },
        'rsi_oversold_bounce':   { abbrev: 'RSI-BNC',    name: 'RSI Oversold Bounce',      desc: 'RSI crossed back above 30 (oversold) with bullish candle.', side: 'long', color: '#2196F3' },
        'ema_momentum':          { abbrev: 'EMA-MOM',    name: 'EMA Momentum',             desc: 'Price above rising fast EMA for 2+ bars \u2014 momentum re-entry.', side: 'long', color: '#00BCD4' },
        'quick_reentry':         { abbrev: 'QUICK',      name: 'Quick Re-entry',           desc: 'Fast re-entry after brief exit when trend resumes quickly.', side: 'long', color: '#7C4DFF' },
        'volume_capitulation':   { abbrev: 'VOL-CAP',    name: 'Volume Capitulation',      desc: 'Consecutive bars of declining price with increasing volume \u2014 selling climax washout.', side: 'long', color: '#E040FB' },
    };
    const EXIT_REGISTRY = {
        // Curved Channels exits (red-orange-yellow shades)
        'atr_trailing_stop':     { abbrev: 'ATR-TS',     name: 'ATR Trailing Stop',        desc: 'Price hit ATR-based trailing stop.', color: '#ef5350' },
        'channel_trail_stop':    { abbrev: 'CH-TS',      name: 'Channel Trail Stop',       desc: 'In-channel trailing stop after +2% profit.', color: '#FF7043' },
        'breakout_up':           { abbrev: 'BRK-UP',     name: 'Breakout Up',              desc: 'Price broke above upper channel \u2014 exit to re-enter at higher size.', color: '#FF5722' },
        'breakout_down':         { abbrev: 'BRK-DN',     name: 'Breakout Down',            desc: 'Price broke below lower channel.', color: '#FF5722' },
        'channel_break':         { abbrev: 'CH-BRK',     name: 'Channel Break',            desc: 'Price violated channel boundary beyond tolerance.', color: '#FF9800' },
        'channel_flip':          { abbrev: 'CH-FLIP',    name: 'Channel Flip',             desc: 'Channel direction changed while position was open.', color: '#FF9800' },
        'channel_expired':       { abbrev: 'CH-EXP',     name: 'Channel Expired',          desc: 'Channel expired and position was not profitable.', color: '#FFD54F' },
        'time_exit':             { abbrev: 'TIME',        name: 'Time Exit',                desc: 'Position held max bars without reaching profit target.', color: '#FFAB40' },
        'fallback_sma_exit':     { abbrev: 'SMA-X',      name: 'Fallback SMA Exit',        desc: 'SMA-entered position closed when price dropped below SMA.', color: '#FFAB40' },
        'end_of_data':           { abbrev: 'EOD',         name: 'End of Data',              desc: 'Backtest ended with open position. Force-closed at final price.', color: '#BDBDBD' },
        // Smart Hold exits (red-orange shades)
        'ma_breakdown':          { abbrev: 'MA-BRK',     name: 'MA Breakdown',             desc: 'Confirmed close below SMA with declining slope + EMA below SMA. Adaptive to volatility.', color: '#ef5350' },
        'vix_accelerated_exit':  { abbrev: 'VIX-X',      name: 'VIX Accelerated Exit',     desc: 'MA breakdown exit triggered 1 bar faster due to elevated VIX (\u2265 25).', color: '#FF7043' },
        'trailing_stop':         { abbrev: 'TRAIL',       name: 'Trailing Stop',            desc: 'ATR trailing stop hit \u2014 catastrophic drop protection (6x ATR from peak).', color: '#FF5722' },
    };

    // Find which entry/exit types actually appear in the trade log
    const usedEntries = new Set();
    const usedExits = new Set();
    TRADE_LOG.forEach(t => {
        if (t.entry_reason) usedEntries.add(t.entry_reason);
        if (t.exit_reason) usedExits.add(t.exit_reason);
    });

    // Helper: convert hex color to rgba for background tint
    function hexToRgba(hex, alpha) {
        const r = parseInt(hex.slice(1,3), 16);
        const g = parseInt(hex.slice(3,5), 16);
        const b = parseInt(hex.slice(5,7), 16);
        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
    }

    // Build entry table (only showing types that appear in this chart's trades)
    let html = '<h4>Entry Markers</h4>' +
        '<table><tr><th>Marker</th><th>Abbrev</th><th>Name</th><th>Description</th></tr>';
    usedEntries.forEach(key => {
        const info = ENTRY_REGISTRY[key];
        if (!info) return;
        const prefix = info.side === 'long' ? 'BUY' : 'SHORT';
        const c = info.color;
        html += '<tr>' +
            '<td><span class="lp-marker" style="background:' + hexToRgba(c, 0.15) + ';color:' + c + '">' + prefix + ' ' + info.abbrev + '</span></td>' +
            '<td><span class="lp-abbrev" style="color:' + c + '">' + info.abbrev + '</span></td>' +
            '<td class="lp-name">' + info.name + '</td>' +
            '<td class="lp-desc">' + info.desc + '</td></tr>';
    });
    html += '</table>';

    // Build exit table
    html += '<h4>Exit Markers</h4>' +
        '<table><tr><th>Marker</th><th>Abbrev</th><th>Name</th><th>Description</th></tr>';
    usedExits.forEach(key => {
        const info = EXIT_REGISTRY[key];
        if (!info) return;
        const c = info.color;
        html += '<tr>' +
            '<td><span class="lp-marker" style="background:' + hexToRgba(c, 0.15) + ';color:' + c + '">EXIT ' + info.abbrev + '</span></td>' +
            '<td><span class="lp-abbrev" style="color:' + c + '">' + info.abbrev + '</span></td>' +
            '<td class="lp-name">' + info.name + '</td>' +
            '<td class="lp-desc">' + info.desc + '</td></tr>';
    });
    html += '</table>';

    // Version tags (if any)
    const tags = Object.keys(VERSIONS).sort((a, b) => parseInt(a.replace('v',''),10) - parseInt(b.replace('v',''),10));
    if (tags.length > 0) {
        html += '<h4>Strategy Version Tags</h4>' +
            '<table><tr><th>Tag</th><th>Label</th><th>Type</th><th>Description</th></tr>';
        tags.forEach(tag => {
            const v = VERSIONS[tag];
            const typeCls = (v.type === 'exit_type') ? 'exit' : 'entry';
            html += '<tr>' +
                '<td><span class="lp-vtag-pill ' + typeCls + '">' + tag + '</span></td>' +
                '<td class="lp-name">' + v.label + '</td>' +
                '<td class="lp-vtype">' + v.type.replace(/_/g,' ') + '</td>' +
                '<td class="lp-desc">' + v.description + '</td></tr>';
        });
        html += '</table>';
    }
    body.innerHTML = html;
})();

// --- Fit content ---
chart.timeScale().fitContent();

// --- Resize ---
const ro = new ResizeObserver(() => {
    resizeChart();
});
ro.observe(container);
</script>
</body>
</html>
"""
