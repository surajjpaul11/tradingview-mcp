// ============================================================
// Trade Visualizer — app.js
// ============================================================

// ----- Core DOM References -----
const tickerSelect = document.getElementById('ticker-select');
const strategySelect = document.getElementById('strategy-select');
const loadingOverlay = document.getElementById('loading');
const pnlVal = document.getElementById('pnl-val');
const winrateVal = document.getElementById('winrate-val');
const totalTradesVal = document.getElementById('total-trades-val');

// ----- Chart Globals -----
let chart = null;
let candlestickSeries = null;
let currentCandles = [];
let activeRange = '5y'; // Default: 5-Year view

// ============================================================
// STEP 1: Initialize TradingView chart
// ============================================================
function initChart() {
    const container = document.getElementById('tv-chart');
    if (!container) {
        console.error('[TV] No chart container found');
        return;
    }

    // Clear any previous child nodes
    container.innerHTML = '';

    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth || 800,
        height: container.clientHeight || 500,
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#94A3B8',
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
        },
        timeScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
            timeVisible: true,
            secondsVisible: false,
        },
        crosshair: {
            mode: 1,
            vertLine: { color: '#3B82F6', labelBackgroundColor: '#3B82F6' },
            horzLine: { color: '#3B82F6', labelBackgroundColor: '#3B82F6' }
        }
    });

    // Support both LightweightCharts v4 and v5 APIs
    if (typeof chart.addCandlestickSeries === 'function') {
        candlestickSeries = chart.addCandlestickSeries({
            upColor: '#10B981',
            downColor: '#EF4444',
            borderVisible: false,
            wickUpColor: '#10B981',
            wickDownColor: '#EF4444'
        });
    } else if (typeof chart.addSeries === 'function' && typeof LightweightCharts.CandlestickSeries !== 'undefined') {
        candlestickSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: '#10B981',
            downColor: '#EF4444',
            borderVisible: false,
            wickUpColor: '#10B981',
            wickDownColor: '#EF4444'
        });
    } else {
        console.error('[TV] Could not create candlestick series with loaded chart library.');
    }

    new ResizeObserver(() => {
        if (chart && container) {
            chart.applyOptions({
                width: container.clientWidth,
                height: container.clientHeight
            });
        }
    }).observe(container);
}

// ============================================================
// STEP 2: Timeframe / Range Selector Handling
// ============================================================
function applyTimeframeRange(range) {
    activeRange = range;

    // Update active button state
    document.querySelectorAll('.tf-btn').forEach(btn => {
        if (btn.dataset.range === range) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Update hint label
    const hintEl = document.getElementById('active-range-hint');
    const labels = {
        '1d': 'Daily (1D) View',
        '1m': 'Monthly (1M) View',
        'ytd': 'Year-to-Date (YTD) View',
        '1y': '1-Year (1Y) View',
        '5y': '5-Year (5Y) View'
    };
    if (hintEl) hintEl.textContent = labels[range] || `${range.toUpperCase()} View`;

    if (!chart || !currentCandles || currentCandles.length === 0) return;

    if (range === '5y') {
        chart.timeScale().fitContent();
        return;
    }

    const lastBar = currentCandles[currentCandles.length - 1];
    const lastTime = lastBar.time;
    const nowObj = new Date(lastTime * 1000);

    let fromTime;
    if (range === '1d') {
        // High-zoom view on the latest 2-3 trading sessions
        fromTime = lastTime - (2 * 86400);
    } else if (range === '1m') {
        // Last 30 calendar days
        fromTime = lastTime - (30 * 86400);
    } else if (range === 'ytd') {
        // Jan 1 of the last bar's current year
        fromTime = Math.floor(new Date(nowObj.getFullYear(), 0, 1).getTime() / 1000);
    } else if (range === '1y') {
        // Last 365 calendar days
        fromTime = lastTime - (365 * 86400);
    }

    try {
        chart.timeScale().setVisibleRange({
            from: fromTime,
            to: lastTime + 86400
        });
    } catch (e) {
        console.warn('[TV] setVisibleRange fallback:', e);
        chart.timeScale().fitContent();
    }
}

function initTimeframeButtons() {
    document.querySelectorAll('.tf-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const range = e.currentTarget.dataset.range;
            if (range) {
                applyTimeframeRange(range);
            }
        });
    });
}

// ============================================================
// STEP 3: Load filter dropdowns from /api/filters
// ============================================================
async function loadFilters() {
    try {
        const res = await fetch('/api/filters');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // Populate ticker dropdown
        tickerSelect.innerHTML = '';
        if (!data.symbols || data.symbols.length === 0) {
            tickerSelect.innerHTML = '<option value="">No trades in DB yet</option>';
        } else {
            data.symbols.forEach(sym => {
                const opt = document.createElement('option');
                opt.value = sym;
                opt.textContent = sym;
                tickerSelect.appendChild(opt);
            });
        }

        // Populate strategy dropdown
        strategySelect.innerHTML = '<option value="all">All Strategies</option>';
        if (data.strategies && data.strategies.length > 0) {
            data.strategies.forEach(strat => {
                const opt = document.createElement('option');
                opt.value = strat;
                opt.textContent = strat;
                strategySelect.appendChild(opt);
            });
        }

        // Default to enhanced_lines strategy if available
        const defaultStrategy = 'enhanced_lines';
        const hasDefault = data.strategies && data.strategies.includes(defaultStrategy);
        if (hasDefault) {
            strategySelect.value = defaultStrategy;
        }

        // Wire up change listeners
        tickerSelect.onchange = updateDashboard;
        strategySelect.onchange = updateDashboard;

        // Trigger initial data load
        if (data.symbols && data.symbols.length > 0) {
            await updateDashboard();
        }

    } catch (err) {
        console.error('[TV] loadFilters failed:', err);
        tickerSelect.innerHTML = '<option value="">Error loading data</option>';
    }
}

// ============================================================
// Helpers
// ============================================================
function setLoading(active) {
    if (!loadingOverlay) return;
    if (active) loadingOverlay.classList.add('active');
    else loadingOverlay.classList.remove('active');
}

function toChartTime(isoString) {
    if (!isoString) return Math.floor(Date.now() / 1000);
    const ts = new Date(isoString).getTime();
    return Math.floor(ts / 1000);
}

function findNearestCandleTime(tradeTime, candles) {
    if (!candles || candles.length === 0) return tradeTime;
    let closest = candles[0].time;
    let minDiff = Math.abs(tradeTime - closest);
    for (let i = 1; i < candles.length; i++) {
        const diff = Math.abs(tradeTime - candles[i].time);
        if (diff < minDiff) {
            minDiff = diff;
            closest = candles[i].time;
        }
    }
    return closest;
}

// ============================================================
// STEP 4: Update chart + stats based on current filter state
// ============================================================
async function updateDashboard() {
    const symbol = tickerSelect.value;
    const strategy = strategySelect.value || 'all';
    if (!symbol) return;

    setLoading(true);

    try {
        const [candlesRes, tradesRes, statsRes] = await Promise.all([
            fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}&period=5y`),
            fetch(`/api/trades?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}`),
            fetch(`/api/stats?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}`)
        ]);

        const candlesData = await candlesRes.json();
        const tradesData = await tradesRes.json();
        const statsData = await statsRes.json();

        // -- Candles --
        const rawCandles = candlesData.candles || [];
        const sorted = rawCandles
            .sort((a, b) => a.time - b.time)
            .filter((c, i, arr) => i === 0 || c.time !== arr[i - 1].time); // deduplicate

        currentCandles = sorted;

        if (candlestickSeries && sorted.length > 0) {
            candlestickSeries.setData(sorted);
        }

        // -- Trade Markers (Both Buy/Entry and Sell/Exit) --
        if (candlestickSeries && tradesData.trades && sorted.length > 0) {
            try {
                const markers = [];
                tradesData.trades.forEach(trade => {
                    const entryTime = toChartTime(trade.created_at);
                    const snappedEntry = findNearestCandleTime(entryTime, sorted);
                    const isLong = (trade.side || '').toLowerCase() === 'buy';

                    // 1. Entry Marker
                    markers.push({
                        time: snappedEntry,
                        position: isLong ? 'belowBar' : 'aboveBar',
                        color: isLong ? '#10B981' : '#F59E0B',
                        shape: isLong ? 'arrowUp' : 'arrowDown',
                        text: `${trade.strategy} ${isLong ? 'BUY' : 'SHORT'} @ $${Number(trade.entry_price || 0).toFixed(2)}`
                    });

                    // 2. Exit Marker (if trade has an exit recorded)
                    if (trade.status === 'closed' && trade.exit_price != null && trade.closed_at) {
                        const exitTime = toChartTime(trade.closed_at);
                        const snappedExit = findNearestCandleTime(exitTime, sorted);
                        const isWin = (trade.pnl_usd || 0) >= 0;
                        const pnlPct = Number(trade.pnl_pct || 0);
                        const pnlSign = pnlPct >= 0 ? '+' : '';
                        const reason = trade.exit_reason ? ` [${trade.exit_reason}]` : '';

                        markers.push({
                            time: snappedExit,
                            position: isLong ? 'aboveBar' : 'belowBar',
                            color: isWin ? '#10B981' : '#EF4444',
                            shape: isLong ? 'arrowDown' : 'arrowUp',
                            text: `${trade.strategy} ${isLong ? 'SELL' : 'COVER'} @ $${Number(trade.exit_price).toFixed(2)} (${pnlSign}${pnlPct.toFixed(1)}%)${reason}`
                        });
                    }
                });

                markers.sort((a, b) => a.time - b.time);

                if (typeof candlestickSeries.setMarkers === 'function') {
                    candlestickSeries.setMarkers(markers);
                }
            } catch (markerErr) {
                console.warn('[TV] Marker setting warning:', markerErr);
            }
        } else if (candlestickSeries) {
            candlestickSeries.setMarkers([]);
        }

        // Apply active timeframe zoom (preserves user selection across dropdown changes)
        applyTimeframeRange(activeRange);

        // -- Stats --
        const pnl = statsData.total_pnl_usd || 0;
        const pnlSign = pnl >= 0 ? '+' : '-';
        pnlVal.textContent = `${pnlSign}$${Math.abs(pnl).toFixed(2)}`;
        pnlVal.className = 'stat-value' + (pnl > 0 ? ' profit' : pnl < 0 ? ' loss' : '');
        winrateVal.textContent = `${statsData.win_rate_pct || 0}%`;
        totalTradesVal.textContent = (tradesData.trades ? tradesData.trades.length : statsData.total_trades) || 0;

    } catch (err) {
        console.error('[TV] updateDashboard failed:', err);
    } finally {
        setLoading(false);
    }
}

// ============================================================
// Bootstrap — runs once DOM scripts have executed
// ============================================================
(function bootstrap() {
    try {
        if (typeof LightweightCharts === 'undefined') {
            console.error('[TV] LightweightCharts not loaded');
            const tvContainer = document.getElementById('tv-chart');
            if (tvContainer) {
                tvContainer.innerHTML =
                    '<p style="color:#EF4444;padding:2rem;text-align:center;">Chart library failed to load from CDN.<br>Check your internet connection and reload the page.</p>';
            }
            loadFilters();
            return;
        }
        initChart();
    } catch (err) {
        console.error('[TV] Chart initialization failed:', err);
    }
    initTimeframeButtons();
    loadFilters();
})();
