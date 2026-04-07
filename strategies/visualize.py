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
}
EXIT_ABBREV = {
    "atr_trailing_stop": "ATR-TS", "channel_trail_stop": "CH-TS",
    "breakout_up": "BRK-UP", "breakout_down": "BRK-DN",
    "channel_break": "CH-BRK", "channel_flip": "CH-FLIP",
    "channel_expired": "CH-EXP", "time_exit": "TIME",
    "fallback_sma_exit": "SMA-X", "end_of_data": "EOD",
}


def generate_chart_html(
    result: dict,
    candles: list[dict],
    output_path: Path,
) -> Path:
    """
    Generate a self-contained HTML chart file.

    Args:
        result: backtest result dict (from run_backtest()), must include trade_log.
                Optionally includes "overlays" list.
        candles: raw OHLCV candle list (from fetch_ohlcv())
        output_path: where to write the HTML file

    Returns:
        Path to the written HTML file.
    """
    # Convert candles to Lightweight Charts format
    candles_lw = []
    for c in candles:
        entry = {
            "open": c["open"], "high": c["high"],
            "low": c["low"], "close": c["close"],
        }
        # Daily format "YYYY-MM-DD" works directly; intraday needs Unix timestamp
        date_str = c["date"]
        if " " in date_str:
            # Intraday: "2024-01-15 14:00" -> Unix timestamp
            entry["time"] = date_str
        else:
            entry["time"] = date_str
        candles_lw.append(entry)

    # Build trade markers
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
                "color": "#26a69a",
                "shape": "arrowUp",
                "text": f"BUY {entry_abbrev}",
            })
        else:
            markers.append({
                "time": t["entry_date"],
                "position": "aboveBar",
                "color": "#ef5350",
                "shape": "arrowDown",
                "text": f"SHORT {entry_abbrev}",
            })
        # Exit marker
        if side == "long":
            markers.append({
                "time": t["exit_date"],
                "position": "aboveBar",
                "color": "#ef5350",
                "shape": "arrowDown",
                "text": f"EXIT {exit_abbrev}",
            })
        else:
            markers.append({
                "time": t["exit_date"],
                "position": "belowBar",
                "color": "#26a69a",
                "shape": "arrowUp",
                "text": f"COVER {exit_abbrev}",
            })

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

    html = _HTML_TEMPLATE
    html = html.replace("__CANDLES_JSON__", json.dumps(candles_lw))
    html = html.replace("__MARKERS_JSON__", json.dumps(markers))
    html = html.replace("__OVERLAYS_JSON__", json.dumps(overlays))
    html = html.replace("__META_JSON__", json.dumps(meta))
    html = html.replace("__TRADES_JSON__", json.dumps(trades))

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
#trade-log-toggle {
    position: absolute;
    top: 12px;
    right: 20px;
    background: #2a2e39;
    color: #d1d4dc;
    border: 1px solid #363a45;
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    z-index: 10;
}
#trade-log-toggle:hover { background: #363a45; }
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
</style>
</head>
<body>
<div id="header">
    <h1 id="title"></h1>
    <div id="stats"></div>
</div>
<button id="trade-log-toggle" onclick="toggleTradeLog()">Trade Log</button>
<div id="chart-container">
    <div id="trade-log-panel">
        <h3>Trade Log</h3>
        <div id="trade-log-body"></div>
    </div>
    <div id="legend"></div>
</div>

<script>
const CANDLES = __CANDLES_JSON__;
const MARKERS = __MARKERS_JSON__;
const OVERLAYS = __OVERLAYS_JSON__;
const META = __META_JSON__;

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

// --- Trade Log Panel ---
function toggleTradeLog() {
    const panel = document.getElementById('trade-log-panel');
    panel.classList.toggle('visible');
    const panelW = panel.classList.contains('visible') ? 420 : 0;
    chart.applyOptions({ width: container.clientWidth - panelW, height: container.clientHeight });
}

const tradeLogBody = document.getElementById('trade-log-body');
const TRADE_LOG = __TRADES_JSON__;
let tlHTML = '';
TRADE_LOG.forEach(t => {
    const pnlCls = (t.return_pct || 0) > 0 ? 'positive' : 'negative';
    const sideCls = t.side === 'long' ? 'long' : 'short';
    tlHTML += '<div class="trade-row">' +
        '<span class="side ' + sideCls + '">' + t.side.toUpperCase() + '</span>' +
        '<span class="dates">' + (t.entry_date||'').substring(0,10) + ' \u2192 ' + (t.exit_date||'').substring(0,10) + '</span>' +
        '<span class="pnl ' + pnlCls + '">' + ((t.return_pct||0) >= 0 ? '+' : '') + (t.return_pct||0).toFixed(2) + '%</span>' +
        '<span class="reason">' + (t.exit_reason||'').replace(/_/g, ' ') + '</span>' +
        '</div>';
});
tradeLogBody.innerHTML = tlHTML || '<div style="color:#787b86">No trades</div>';

// --- Fit content ---
chart.timeScale().fitContent();

// --- Resize ---
const ro = new ResizeObserver(() => {
    const panel = document.getElementById('trade-log-panel');
    const panelW = panel.classList.contains('visible') ? 420 : 0;
    chart.applyOptions({
        width: container.clientWidth - panelW,
        height: container.clientHeight,
    });
});
ro.observe(container);
</script>
</body>
</html>
"""
