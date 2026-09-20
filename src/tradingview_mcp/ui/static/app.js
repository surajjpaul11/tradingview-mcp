// ============================================================
// Trade Visualizer — app.js
// ============================================================

// ----- Core DOM References -----
const tickerSelect = document.getElementById('ticker-select');
const strategySelect = document.getElementById('strategy-select');
const channelMultGroup = document.getElementById('channel-mult-group');
const channelMultSelect = document.getElementById('channel-mult-select');
const channelLookbackGroup = document.getElementById('channel-lookback-group');
const channelLookbackSelect = document.getElementById('channel-lookback-select');
const channelStoplossGroup = document.getElementById('channel-stoploss-group');
const channelStoplossCheckbox = document.getElementById('channel-stoploss-checkbox');
const loadingOverlay = document.getElementById('loading');
const pnlVal = document.getElementById('pnl-val');
const pnlPctVal = document.getElementById('pnl-pct-val');
const bnhVal = document.getElementById('bnh-val');
const winrateVal = document.getElementById('winrate-val');
const totalTradesVal = document.getElementById('total-trades-val');

function getSelectedChannelMult() {
    if (!channelMultSelect) return 1.7;
    return parseFloat(channelMultSelect.value) || 1.7;
}

function getSelectedChannelLookback() {
    if (!channelLookbackSelect) return 50;
    return parseInt(channelLookbackSelect.value, 10) || 50;
}

function getChannelStoplossEnabled() {
    if (!channelStoplossCheckbox) return true;
    return channelStoplossCheckbox.checked;
}

function syncChannelMultVisibility(strategy) {
    const currentStrat = strategy || (strategySelect ? strategySelect.value : '');
    const isChannel = (currentStrat === 'enhanced_channel');
    if (channelMultGroup) channelMultGroup.style.display = isChannel ? 'flex' : 'none';
    if (channelLookbackGroup) channelLookbackGroup.style.display = isChannel ? 'flex' : 'none';
    if (channelStoplossGroup) channelStoplossGroup.style.display = isChannel ? 'flex' : 'none';
}

// ----- Chart Globals (Regular Tab) -----
let chart = null;
let candlestickSeries = null;
let currentCandles = [];
let activeRange = '5y'; // Default: 5-Year view
let trendlineSeries = []; // LineSeries for trendline overlays

// ----- Chart Globals (Advanced Tab) -----
let advChart = null;
let advCandlestickSeries = null;
let advCurrentCandles = [];
let advActiveRange = '1y'; // Default: 1-Year daily
let advTrendlineSeries = [];

// ----- Tab State -----
let activeTab = 'regular';

// ============================================================
// TAB SWITCHING
// ============================================================
function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            if (tab === activeTab) return;
            switchTab(tab);
        });
    });
}

function switchTab(tab) {
    activeTab = tab;

    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    // Update tab panels
    document.querySelectorAll('.tab-panel').forEach(panel => {
        const isActive = panel.id === `panel-${tab}`;
        panel.classList.toggle('active', isActive);
    });

    // Initialize advanced chart if first switch
    if (tab === 'advanced' && !advChart) {
        initAdvChart();
        updateAdvDashboard();
    } else if (tab === 'advanced' && advChart) {
        // Resize to fit container
        const container = document.getElementById('adv-chart');
        if (container && advChart) {
            advChart.applyOptions({
                width: container.clientWidth || 800,
                height: container.clientHeight || 500,
            });
        }
    }
}

// ============================================================
// STEP 1: Initialize Regular TradingView chart
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

    new ResizeObserver(entries => {
        if (chart && container) {
            const width = container.clientWidth || (entries[0] && entries[0].contentRect.width) || 800;
            const height = container.clientHeight || (entries[0] && entries[0].contentRect.height) || 500;
            if (width > 50 && height > 50) {
                chart.applyOptions({ width, height });
            }
        }
    }).observe(container);
}

// ============================================================
// STEP 1b: Initialize Advanced TradingView chart
// ============================================================
function initAdvChart() {
    const container = document.getElementById('adv-chart');
    if (!container) return;

    container.innerHTML = '';

    advChart = LightweightCharts.createChart(container, {
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

    if (typeof advChart.addCandlestickSeries === 'function') {
        advCandlestickSeries = advChart.addCandlestickSeries({
            upColor: '#10B981',
            downColor: '#EF4444',
            borderVisible: false,
            wickUpColor: '#10B981',
            wickDownColor: '#EF4444'
        });
    } else if (typeof advChart.addSeries === 'function' && typeof LightweightCharts.CandlestickSeries !== 'undefined') {
        advCandlestickSeries = advChart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: '#10B981',
            downColor: '#EF4444',
            borderVisible: false,
            wickUpColor: '#10B981',
            wickDownColor: '#EF4444'
        });
    }

    new ResizeObserver(entries => {
        if (advChart && container) {
            const width = container.clientWidth || (entries[0] && entries[0].contentRect.width) || 800;
            const height = container.clientHeight || (entries[0] && entries[0].contentRect.height) || 500;
            if (width > 50 && height > 50) {
                advChart.applyOptions({ width, height });
            }
        }
    }).observe(container);
}

// ============================================================
// STEP 2: Timeframe / Range Selector Handling (Regular Tab)
// ============================================================
function applyTimeframeRange(range) {
    activeRange = range;

    // Update active button state
    document.querySelectorAll('#timeframe-btn-group .tf-btn').forEach(btn => {
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
    document.querySelectorAll('#timeframe-btn-group .tf-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const range = e.currentTarget.dataset.range;
            if (range) {
                applyTimeframeRange(range);
            }
        });
    });
}

// ============================================================
// STEP 2b: Advanced Timeframe Handler (fetches new data)
// ============================================================
const ADV_RANGE_CONFIG = {
    '1d':  { interval: '5m',  period: '1d',  label: '1 Day · 5-Min Candles' },
    '5d':  { interval: '15m', period: '5d',  label: '5 Days · 15-Min Candles' },
    '1mo': { interval: '1h',  period: '1mo', label: '1 Month · Hourly Candles' },
    'ytd': { interval: '1d',  period: 'ytd', label: 'Year-to-Date · Daily Candles' },
    '1y':  { interval: '1d',  period: '1y',  label: '1 Year · Daily Candles' },
    '5y':  { interval: '1wk', period: '5y',  label: '5 Years · Weekly Candles' },
};

function initAdvTimeframeButtons() {
    document.querySelectorAll('.adv-tf-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const range = e.currentTarget.dataset.advRange;
            if (range) {
                advActiveRange = range;
                // Update active state
                document.querySelectorAll('.adv-tf-btn').forEach(b => {
                    b.classList.toggle('active', b.dataset.advRange === range);
                });
                // Update hint
                const hint = document.getElementById('adv-range-hint');
                if (hint) hint.textContent = ADV_RANGE_CONFIG[range]?.label || range;
                // Fetch new data
                updateAdvDashboard();
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

        // Default to enhanced_channel strategy if available
        const defaultStrategy = 'enhanced_channel';
        const hasDefault = data.strategies && data.strategies.includes(defaultStrategy);
        if (hasDefault) {
            strategySelect.value = defaultStrategy;
        }

        // Wire up change listeners — update both tabs
        tickerSelect.onchange = () => {
            updateDashboard();
            if (activeTab === 'advanced' && advChart) updateAdvDashboard();
        };
        strategySelect.onchange = () => {
            syncChannelMultVisibility(strategySelect.value);
            updateDashboard();
            if (activeTab === 'advanced' && advChart) updateAdvDashboard();
        };
        if (channelMultSelect) {
            channelMultSelect.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        if (channelLookbackSelect) {
            channelLookbackSelect.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        if (channelStoplossCheckbox) {
            channelStoplossCheckbox.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        syncChannelMultVisibility(strategySelect.value);

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
function setLoading(active, overlayId = 'loading') {
    const overlay = document.getElementById(overlayId);
    if (!overlay) return;
    if (active) overlay.classList.add('active');
    else overlay.classList.remove('active');
}

function toChartTime(isoString) {
    if (!isoString) return Math.floor(Date.now() / 1000);
    let str = String(isoString).trim();
    // Handle double-timestamp corrupted strings like "2024-05-01 14:30T09:30:00+00:00"
    if (str.includes(' ') && str.includes('T')) {
        str = str.split('T')[0].replace(' ', 'T');
        if (str.split(':').length === 2) str += ':00';
    } else {
        str = str.replace(' ', 'T');
    }
    let ts = new Date(str).getTime();
    if (isNaN(ts)) {
        const match = str.match(/\d{4}-\d{2}-\d{2}/);
        if (match) {
            ts = new Date(match[0] + 'T12:00:00Z').getTime();
        }
    }
    if (isNaN(ts)) return Math.floor(Date.now() / 1000);
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

function isTimeInCandleRange(tradeTime, candles) {
    if (!candles || candles.length === 0) return false;
    const minTime = candles[0].time;
    const maxTime = candles[candles.length - 1].time;
    const step = candles.length > 1 ? (candles[1].time - candles[0].time) : 86400;
    const margin = step >= 86400 ? Math.max(step, 86400 * 4) : Math.max(step * 2, 3600);
    return tradeTime >= (minTime - margin) && tradeTime <= (maxTime + margin);
}

function isStopLossReason(reason) {
    if (!reason || typeof reason !== 'string') return false;
    const r = reason.toLowerCase();
    return r.includes('stop') || r.includes('stopgap') || r.includes('trailing');
}

function buildMarkers(tradesData, sorted, strategy) {
    if (!sorted || sorted.length === 0 || !tradesData || !Array.isArray(tradesData.trades)) {
        return [];
    }

    const markers = [];
    const showStrategy = strategy === 'all';

    tradesData.trades.forEach(trade => {
        const entryTime = toChartTime(trade.created_at);
        if (isTimeInCandleRange(entryTime, sorted)) {
            const snappedEntry = findNearestCandleTime(entryTime, sorted);
            const sideStr = (trade.side || '').toLowerCase();
            const isLong = sideStr === 'buy' || sideStr === 'long';
            const stratPrefix = showStrategy ? `${trade.strategy} ` : '';
            const isStopEntry = isStopLossReason(trade.entry_reason) || isStopLossReason(trade.notes);
            const entryPrefix = isStopEntry ? 'STOP LOSS ' : '';

            // 1. Entry Marker
            markers.push({
                time: snappedEntry,
                position: isLong ? 'belowBar' : 'aboveBar',
                color: isLong ? '#10B981' : '#F59E0B',
                shape: isLong ? 'arrowUp' : 'arrowDown',
                text: `${stratPrefix}${entryPrefix}${isLong ? 'BUY' : 'SHORT'} $${Number(trade.entry_price || 0).toFixed(2)}`
            });
        }

        // 2. Exit Marker (if trade has an exit recorded)
        if (trade.status === 'closed' && trade.exit_price != null && trade.closed_at) {
            const exitTime = toChartTime(trade.closed_at);
            if (isTimeInCandleRange(exitTime, sorted)) {
                const snappedExit = findNearestCandleTime(exitTime, sorted);
                const sideStr = (trade.side || '').toLowerCase();
                const isLong = sideStr === 'buy' || sideStr === 'long';
                const isWin = (trade.pnl_usd || 0) >= 0;
                const pnlPct = Number(trade.pnl_pct || 0);
                const pnlSign = pnlPct >= 0 ? '+' : '';
                const stratPrefix = showStrategy ? `${trade.strategy} ` : '';
                const isStopExit = isStopLossReason(trade.exit_reason) || isStopLossReason(trade.notes);
                const exitPrefix = isStopExit ? 'STOP LOSS ' : '';
                const action = isLong ? 'SELL' : 'COVER';

                markers.push({
                    time: snappedExit,
                    position: isLong ? 'aboveBar' : 'belowBar',
                    color: isStopExit ? '#F43F5E' : (isWin ? '#10B981' : '#EF4444'),
                    shape: isLong ? 'arrowDown' : 'arrowUp',
                    text: `${stratPrefix}${exitPrefix}${action} $${Number(trade.exit_price).toFixed(2)} (${pnlSign}${pnlPct.toFixed(1)}%)`
                });
            }
        }
    });

    // Consolidate markers sharing exact same candle time & position
    const consolidatedMap = new Map();
    markers.forEach(m => {
        const key = `${m.time}_${m.position}`;
        if (!consolidatedMap.has(key)) {
            consolidatedMap.set(key, { ...m, count: 1 });
        } else {
            const existing = consolidatedMap.get(key);
            existing.count += 1;
            const isSL = (existing.text && existing.text.includes('STOP LOSS')) || (m.text && m.text.includes('STOP LOSS'));
            const action = m.position === 'belowBar' ? 'BUY' : 'SELL';
            existing.text = isSL ? `${existing.count}x STOP LOSS ${action}` : `${existing.count}x ${action}`;
        }
    });

    const finalMarkers = Array.from(consolidatedMap.values());

    // Buy & Hold Entry and Exit Markers (Silver color: #C0C0C0)
    const sortedTrades = [...tradesData.trades]
        .filter(t => t.created_at && t.entry_price != null)
        .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

    if (sortedTrades.length > 0) {
        const firstTrade = sortedTrades[0];
        const closedTrades = sortedTrades.filter(t => t.status === 'closed' && t.exit_price != null && t.closed_at);
        const lastTrade = closedTrades.length > 0 ? closedTrades[closedTrades.length - 1] : sortedTrades[sortedTrades.length - 1];

        const entryPrice = Number(firstTrade.entry_price);
        const exitPrice = lastTrade.exit_price != null ? Number(lastTrade.exit_price) : Number(lastTrade.entry_price);

        if (entryPrice > 0) {
            const bnhPct = ((exitPrice - entryPrice) / entryPrice) * 100;
            const bnhSign = bnhPct >= 0 ? '+' : '';

            // B&H Entry
            const entryTime = toChartTime(firstTrade.created_at);
            if (isTimeInCandleRange(entryTime, sorted)) {
                const snappedEntry = findNearestCandleTime(entryTime, sorted);
                finalMarkers.push({
                    time: snappedEntry,
                    position: 'belowBar',
                    color: '#C0C0C0',
                    shape: 'circle',
                    size: 2,
                    text: `B&H BUY $${entryPrice.toFixed(2)}`
                });
            }

            // B&H Exit
            const exitTime = toChartTime(lastTrade.closed_at || lastTrade.created_at);
            if (isTimeInCandleRange(exitTime, sorted)) {
                const snappedExit = findNearestCandleTime(exitTime, sorted);
                finalMarkers.push({
                    time: snappedExit,
                    position: 'aboveBar',
                    color: '#C0C0C0',
                    shape: 'circle',
                    size: 2,
                    text: `B&H EXIT $${exitPrice.toFixed(2)} (${bnhSign}${bnhPct.toFixed(1)}%)`
                });
            }
        }
    }

    return finalMarkers.sort((a, b) => a.time - b.time);
}

// ============================================================
// TRENDLINE OVERLAY
// ============================================================
async function fetchAndRenderTrendlines(symbol, chartInstance, candleData, existingSeriesList) {
    // Remove previous trendline series
    existingSeriesList.forEach(s => {
        try { chartInstance.removeSeries(s); } catch (_) {}
    });
    existingSeriesList.length = 0;

    try {
        const res = await fetch(`/api/trendlines?symbol=${encodeURIComponent(symbol)}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.trendlines || data.trendlines.length === 0) return;

        data.trendlines.forEach(tl => {
            const startTime = toChartTime(tl.start_date);
            const endTime = toChartTime(tl.end_date);

            // Only render lines that overlap with visible candle data
            if (candleData.length === 0) return;
            const firstCandle = candleData[0].time;
            const lastCandle = candleData[candleData.length - 1].time;
            if (endTime < firstCandle || startTime > lastCandle) return;

            const color = tl.type === 'support' ? 'rgba(16, 185, 129, 0.6)' : 'rgba(245, 158, 11, 0.6)';

            let lineSeries;
            if (typeof chartInstance.addLineSeries === 'function') {
                lineSeries = chartInstance.addLineSeries({
                    color: color,
                    lineWidth: 2,
                    lineStyle: 2, // Dashed
                    crosshairMarkerVisible: false,
                    lastValueVisible: false,
                    priceLineVisible: false,
                });
            } else if (typeof chartInstance.addSeries === 'function' && typeof LightweightCharts.LineSeries !== 'undefined') {
                lineSeries = chartInstance.addSeries(LightweightCharts.LineSeries, {
                    color: color,
                    lineWidth: 2,
                    lineStyle: 2,
                    crosshairMarkerVisible: false,
                    lastValueVisible: false,
                    priceLineVisible: false,
                });
            }

            if (lineSeries) {
                const snappedStart = findNearestCandleTime(startTime, candleData);
                const snappedEnd = findNearestCandleTime(endTime, candleData);
                lineSeries.setData([
                    { time: snappedStart, value: tl.start_price },
                    { time: snappedEnd, value: tl.end_price },
                ]);
                existingSeriesList.push(lineSeries);
            }
        });
    } catch (err) {
        console.warn('[TV] Trendline fetch error:', err);
    }
}

// ============================================================
// ENHANCED CHANNEL OVERLAYS & LEGEND
// ============================================================
const channelSeries = [];
const advChannelSeries = [];

function updateChannelLegend(containerId, isVisible) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!isVisible) {
        el.style.display = 'none';
        el.innerHTML = '';
        return;
    }
    el.style.display = 'flex';
    el.innerHTML = `
        <div class="channel-pill"><span class="channel-dot" style="background: #10B981;"></span>Tactical Lower (Buy Zone)</div>
        <div class="channel-pill"><span class="channel-dot" style="background: #EF4444;"></span>Tactical Upper (Take Profit)</div>
        <div class="channel-pill"><span class="channel-dot" style="background: #3B82F6;"></span>Tactical Mid (3M)</div>
        <div class="channel-pill"><span class="channel-dot" style="background: #F59E0B;"></span>Intermediate (1Y)</div>
        <div class="channel-pill"><span class="channel-dot" style="background: #A855F7;"></span>Macro (5Y)</div>
    `;
}

async function fetchAndRenderChannels(symbol, chartInstance, candleData, existingSeriesList, timeframe = '1d', period = '5y') {
    // Remove previous channel series
    existingSeriesList.forEach(s => {
        try { chartInstance.removeSeries(s); } catch (_) {}
    });
    existingSeriesList.length = 0;

    try {
        const mult = getSelectedChannelMult();
        const lb = getSelectedChannelLookback();
        const res = await fetch(`/api/channels?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&period=${encodeURIComponent(period)}&channel_mult=${mult}&lookback=${lb}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.overlays || data.overlays.length === 0) return;

        if (candleData.length === 0) return;
        const firstCandle = candleData[0].time;
        const lastCandle = candleData[candleData.length - 1].time;

        data.overlays.forEach(ov => {
            if (!ov.points || ov.points.length === 0) return;

            // Map each point to nearest candle and ensure strictly ascending timestamps
            const mappedPoints = [];
            const seenTimes = new Set();

            ov.points.forEach(pt => {
                if (pt.time >= firstCandle && pt.time <= lastCandle) {
                    const snapped = findNearestCandleTime(pt.time, candleData);
                    if (!seenTimes.has(snapped)) {
                        seenTimes.add(snapped);
                        mappedPoints.push({ time: snapped, value: pt.value });
                    }
                }
            });

            if (mappedPoints.length < 2) return;
            mappedPoints.sort((a, b) => a.time - b.time);

            let lineSeries;
            const seriesOptions = {
                color: ov.color,
                lineWidth: ov.lineWidth || 2,
                lineStyle: ov.lineStyle || 0,
                crosshairMarkerVisible: false,
                lastValueVisible: true,
                priceLineVisible: false,
                title: ov.label,
            };

            if (typeof chartInstance.addLineSeries === 'function') {
                lineSeries = chartInstance.addLineSeries(seriesOptions);
            } else if (typeof chartInstance.addSeries === 'function' && typeof LightweightCharts.LineSeries !== 'undefined') {
                lineSeries = chartInstance.addSeries(LightweightCharts.LineSeries, seriesOptions);
            }

            if (lineSeries) {
                lineSeries.setData(mappedPoints);
                existingSeriesList.push(lineSeries);
            }
        });
    } catch (err) {
        console.warn('[TV] Channel overlay error:', err);
    }
}

// ============================================================
// STEP 4: Update Regular chart + stats
// ============================================================
async function updateDashboard() {
    const symbol = tickerSelect.value;
    const strategy = strategySelect.value || 'all';
    if (!symbol) return;

    setLoading(true, 'loading');

    try {
        const multParam = (strategy === 'enhanced_channel') 
            ? `&channel_mult=${getSelectedChannelMult()}&lookback=${getSelectedChannelLookback()}&use_stop_loss=${getChannelStoplossEnabled()}` 
            : '';
        const [candlesRes, tradesRes, statsRes] = await Promise.all([
            fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}&period=5y`),
            fetch(`/api/trades?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}${multParam}`),
            fetch(`/api/stats?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}${multParam}`)
        ]);

        const candlesData = candlesRes.ok ? await candlesRes.json() : { candles: [] };
        const tradesData = tradesRes.ok ? await tradesRes.json() : { trades: [] };
        const statsData = statsRes.ok ? await statsRes.json() : {};

        // -- Candles --
        const rawCandles = candlesData.candles || [];
        const sorted = rawCandles
            .filter(c => c && typeof c.time === 'number' && !isNaN(c.open) && !isNaN(c.high) && !isNaN(c.low) && !isNaN(c.close))
            .sort((a, b) => a.time - b.time)
            .filter((c, i, arr) => i === 0 || c.time !== arr[i - 1].time); // deduplicate

        currentCandles = sorted;

        if (candlestickSeries) {
            candlestickSeries.setData(sorted);
        }

        // -- Trade Markers --
        if (candlestickSeries && tradesData.trades && sorted.length > 0) {
            try {
                const finalMarkers = buildMarkers(tradesData, sorted, strategy);
                if (typeof candlestickSeries.setMarkers === 'function') {
                    candlestickSeries.setMarkers(finalMarkers);
                }
            } catch (markerErr) {
                console.warn('[TV] Marker setting warning:', markerErr);
            }
        } else if (candlestickSeries) {
            candlestickSeries.setMarkers([]);
        }

        // -- Overlays (enhanced_lines trendlines or enhanced_channel regression channels) --
        if (chart && strategy === 'enhanced_lines' && sorted.length > 0) {
            updateChannelLegend('channel-legend', false);
            channelSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            channelSeries.length = 0;
            await fetchAndRenderTrendlines(symbol, chart, sorted, trendlineSeries);
        } else if (chart && strategy === 'enhanced_channel' && sorted.length > 0) {
            trendlineSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            trendlineSeries.length = 0;
            updateChannelLegend('channel-legend', true);
            await fetchAndRenderChannels(symbol, chart, sorted, channelSeries);
        } else {
            updateChannelLegend('channel-legend', false);
            trendlineSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            trendlineSeries.length = 0;
            channelSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            channelSeries.length = 0;
        }

        // Apply active timeframe zoom (preserves user selection across dropdown changes)
        applyTimeframeRange(activeRange);

        // -- Stats --
        const pnl = statsData.total_pnl_usd || 0;
        const pnlSign = pnl >= 0 ? '+' : '-';
        pnlVal.textContent = `${pnlSign}$${Math.abs(pnl).toFixed(2)}`;
        pnlVal.className = 'stat-value' + (pnl > 0 ? ' profit' : pnl < 0 ? ' loss' : '');

        const pnlPct = statsData.total_pnl_pct != null
            ? statsData.total_pnl_pct
            : (statsData.total_pnl_usd ? (statsData.total_pnl_usd / 100) : 0);
        const pnlPctSign = pnlPct >= 0 ? '+' : '';
        if (pnlPctVal) {
            pnlPctVal.textContent = `${pnlPctSign}${Number(pnlPct).toFixed(2)}%`;
            pnlPctVal.className = 'stat-value' + (pnlPct > 0 ? ' profit' : pnlPct < 0 ? ' loss' : '');
        }

        // -- Buy & Hold Return --
        let bnh = statsData.buy_and_hold_pct;
        if ((bnh == null || bnh === 0) && sorted.length >= 2) {
            bnh = ((sorted[sorted.length - 1].close - sorted[0].close) / sorted[0].close) * 100;
        }
        if (bnhVal) {
            if (bnh != null) {
                const bnhSign = bnh >= 0 ? '+' : '';
                bnhVal.textContent = `${bnhSign}${Number(bnh).toFixed(2)}%`;
                bnhVal.className = 'stat-value' + (bnh > 0 ? ' profit' : bnh < 0 ? ' loss' : '');
            } else {
                bnhVal.textContent = '--';
                bnhVal.className = 'stat-value';
            }
        }

        winrateVal.textContent = `${statsData.win_rate_pct || 0}%`;
        totalTradesVal.textContent = (tradesData.trades ? tradesData.trades.length : statsData.total_trades) || 0;

    } catch (err) {
        console.error('[TV] updateDashboard failed:', err);
    } finally {
        setLoading(false, 'loading');
    }
}

// ============================================================
// STEP 5: Update Advanced chart (multi-resolution)
// ============================================================
async function updateAdvDashboard() {
    const symbol = tickerSelect.value;
    const strategy = strategySelect.value || 'all';
    if (!symbol || !advChart || !advCandlestickSeries) return;

    const config = ADV_RANGE_CONFIG[advActiveRange];
    if (!config) return;

    setLoading(true, 'adv-loading');

    try {
        const multParam = (strategy === 'enhanced_channel') 
            ? `&channel_mult=${getSelectedChannelMult()}&lookback=${getSelectedChannelLookback()}&use_stop_loss=${getChannelStoplossEnabled()}` 
            : '';
        const [candlesRes, tradesRes] = await Promise.all([
            fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(config.interval)}&period=${encodeURIComponent(config.period)}`),
            fetch(`/api/trades?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}${multParam}`)
        ]);

        const candlesData = candlesRes.ok ? await candlesRes.json() : { candles: [] };
        const tradesData = tradesRes.ok ? await tradesRes.json() : { trades: [] };

        const rawCandles = candlesData.candles || [];
        const sorted = rawCandles
            .filter(c => c && typeof c.time === 'number' && !isNaN(c.open) && !isNaN(c.high) && !isNaN(c.low) && !isNaN(c.close))
            .sort((a, b) => a.time - b.time)
            .filter((c, i, arr) => i === 0 || c.time !== arr[i - 1].time);

        advCurrentCandles = sorted;

        advCandlestickSeries.setData(sorted);

        // -- Trade Markers on Advanced Chart --
        if (tradesData.trades && sorted.length > 0) {
            try {
                const finalMarkers = buildMarkers(tradesData, sorted, strategy);
                if (typeof advCandlestickSeries.setMarkers === 'function') {
                    advCandlestickSeries.setMarkers(finalMarkers);
                }
            } catch (markerErr) {
                console.warn('[TV] Marker setting warning (adv):', markerErr);
            }
        } else {
            advCandlestickSeries.setMarkers([]);
        }

        // -- Overlays on Advanced (enhanced_lines or enhanced_channel) --
        if (strategy === 'enhanced_lines' && sorted.length > 0) {
            updateChannelLegend('adv-channel-legend', false);
            advChannelSeries.forEach(s => { try { advChart.removeSeries(s); } catch (_) {} });
            advChannelSeries.length = 0;
            await fetchAndRenderTrendlines(symbol, advChart, sorted, advTrendlineSeries);
        } else if (strategy === 'enhanced_channel' && sorted.length > 0) {
            advTrendlineSeries.forEach(s => { try { advChart.removeSeries(s); } catch (_) {} });
            advTrendlineSeries.length = 0;
            updateChannelLegend('adv-channel-legend', true);
            await fetchAndRenderChannels(symbol, advChart, sorted, advChannelSeries, config.interval, config.period);
        } else {
            updateChannelLegend('adv-channel-legend', false);
            advTrendlineSeries.forEach(s => { try { advChart.removeSeries(s); } catch (_) {} });
            advTrendlineSeries.length = 0;
            advChannelSeries.forEach(s => { try { advChart.removeSeries(s); } catch (_) {} });
            advChannelSeries.length = 0;
        }

        // Fit content
        advChart.timeScale().fitContent();

    } catch (err) {
        console.error('[TV-ADV] updateAdvDashboard failed:', err);
    } finally {
        setLoading(false, 'adv-loading');
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
    initTabs();
    initTimeframeButtons();
    initAdvTimeframeButtons();
    loadFilters();
})();
