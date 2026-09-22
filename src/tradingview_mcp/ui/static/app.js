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
const channelMidlineGroup = document.getElementById('channel-midline-group');
const channelMidlineCheckbox = document.getElementById('channel-midline-checkbox');
const channelLowerReclaimGroup = document.getElementById('channel-lower-reclaim-group');
const channelLowerReclaimCheckbox = document.getElementById('channel-lower-reclaim-checkbox');
const channelCurlGroup = document.getElementById('channel-curl-group');
const channelCurlSelect = document.getElementById('channel-curl-select');
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
    if (!channelStoplossCheckbox) return false;
    return channelStoplossCheckbox.checked;
}

function getChannelMidlineEnabled() {
    if (!channelMidlineCheckbox) return false;
    return channelMidlineCheckbox.checked;
}

function getChannelLowerReclaimEnabled() {
    if (!channelLowerReclaimCheckbox) return false;
    return channelLowerReclaimCheckbox.checked;
}

function getChannelCurlMode() {
    if (!channelCurlSelect) return 'both';
    return channelCurlSelect.value || 'both';
}

function getChannelCurlEnabled() {
    const mode = getChannelCurlMode();
    return mode !== 'none';
}

const slopedFullCandleGroup = document.getElementById('sloped-full-candle-group');
const slopedFullCandleCheckbox = document.getElementById('sloped-full-candle-checkbox');
const slopedWickGroup = document.getElementById('sloped-wick-group');
const slopedWickCheckbox = document.getElementById('sloped-wick-checkbox');
const slopedConfirmCandlesGroup = document.getElementById('sloped-confirm-candles-group');
const slopedConfirmCandlesSelect = document.getElementById('sloped-confirm-candles-select');
const slopedInverseColorGroup = document.getElementById('sloped-inverse-color-group');
const slopedInverseColorCheckbox = document.getElementById('sloped-inverse-color-checkbox');
const slopedLineAngleGroup = document.getElementById('sloped-line-angle-group');
const slopedLineAngleSelect = document.getElementById('sloped-line-angle-select');
const slopedStopLossGroup = document.getElementById('sloped-stop-loss-group');
const slopedStopLossSelect = document.getElementById('sloped-stop-loss-select');

function getFullCandleEnabled() {
    if (!slopedFullCandleCheckbox) return true;
    return slopedFullCandleCheckbox.checked;
}

function getWickEnabled() {
    if (!slopedWickCheckbox) return false;
    return slopedWickCheckbox.checked;
}

function getConfirmCandles() {
    if (!slopedConfirmCandlesSelect) return 0;
    return parseInt(slopedConfirmCandlesSelect.value, 10) || 0;
}

function getInverseColorTriggerEnabled() {
    if (!slopedInverseColorCheckbox) return false;
    return slopedInverseColorCheckbox.checked;
}

function getLineAngle() {
    if (!slopedLineAngleSelect) return 3.0;
    const val = parseFloat(slopedLineAngleSelect.value);
    return isNaN(val) ? 3.0 : val;
}

function getStopLossMode() {
    if (!slopedStopLossSelect) return 'exit_peak_reclaim';
    return slopedStopLossSelect.value || 'exit_peak_reclaim';
}

function syncChannelMultVisibility(strategy) {
    const currentStrat = strategy || (strategySelect ? strategySelect.value : '');
    const isChannel = (currentStrat === 'enhanced_channel');
    const isSloped = (currentStrat === 'sloped_lines' || currentStrat === 'slope_lines');
    if (channelMultGroup) channelMultGroup.style.display = isChannel ? 'flex' : 'none';
    if (channelLookbackGroup) channelLookbackGroup.style.display = isChannel ? 'flex' : 'none';
    if (channelStoplossGroup) channelStoplossGroup.style.display = isChannel ? 'flex' : 'none';
    if (channelMidlineGroup) channelMidlineGroup.style.display = isChannel ? 'flex' : 'none';
    if (channelLowerReclaimGroup) channelLowerReclaimGroup.style.display = isChannel ? 'flex' : 'none';
    if (channelCurlGroup) channelCurlGroup.style.display = isChannel ? 'flex' : 'none';
    if (slopedFullCandleGroup) slopedFullCandleGroup.style.display = isSloped ? 'flex' : 'none';
    if (slopedWickGroup) slopedWickGroup.style.display = isSloped ? 'flex' : 'none';
    if (slopedConfirmCandlesGroup) slopedConfirmCandlesGroup.style.display = isSloped ? 'flex' : 'none';
    if (slopedInverseColorGroup) slopedInverseColorGroup.style.display = isSloped ? 'flex' : 'none';
    if (slopedLineAngleGroup) slopedLineAngleGroup.style.display = isSloped ? 'flex' : 'none';
    if (slopedStopLossGroup) slopedStopLossGroup.style.display = isSloped ? 'flex' : 'none';
}

// ----- Chart Globals (Regular Tab) -----
let chart = null;
let candlestickSeries = null;
let activeResolution = '1d'; // Default: 1D candles
let activeTimeframe = '1y';  // Default: 1-Year range
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

    if (tab === 'advanced') {
        if (!advChart) {
            initAdvChart();
        } else {
            const container = document.getElementById('adv-chart');
            if (container && advChart) {
                advChart.applyOptions({
                    width: container.clientWidth || 800,
                    height: container.clientHeight || 500,
                });
            }
        }
        updateAdvDashboard();
    } else if (tab === 'regular') {
        const container = document.getElementById('tv-chart');
        if (container && chart) {
            chart.applyOptions({
                width: container.clientWidth || 800,
                height: container.clientHeight || 500,
            });
        }
        updateDashboard();
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
// STEP 2: Candle Resolution & Timeframe / Range Handling (Regular Tab)
// ============================================================
function setResolution(res) {
    activeResolution = res;
    document.querySelectorAll('#resolution-btn-group .res-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.res === res);
    });
    const resLabels = {
        '30m': '30 Minutes (30m)',
        '1h': '1 Hour (1H)',
        '4h': '4 Hours (4H)',
        '12h': '12 Hours (12H)',
        '1d': 'Daily (1D)',
        '5d': '5 Days (5D)'
    };
    const hintEl = document.getElementById('active-res-hint');
    if (hintEl) hintEl.textContent = resLabels[res] || res;
    updateDashboard();
}

function setTimeframe(range) {
    activeTimeframe = range;
    document.querySelectorAll('#timeframe-btn-group .range-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.range === range);
    });
    const rangeLabels = {
        '3mo': '3 Months (3M)',
        '1y': '1-Year (1Y)',
        '5y': '5-Year (5Y)',
        'max': 'Max History (MAX)'
    };
    const hintEl = document.getElementById('active-range-hint');
    if (hintEl) hintEl.textContent = rangeLabels[range] || range;
    updateDashboard();
}

function initTimeframeButtons() {
    document.querySelectorAll('#resolution-btn-group .res-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const res = e.currentTarget.dataset.res;
            if (res && res !== activeResolution) {
                setResolution(res);
            }
        });
    });

    document.querySelectorAll('#timeframe-btn-group .range-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const range = e.currentTarget.dataset.range;
            if (range && range !== activeTimeframe) {
                setTimeframe(range);
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

        // Default to sloped_lines strategy if available
        const defaultStrategy = 'sloped_lines';
        const hasDefault = data.strategies && data.strategies.includes(defaultStrategy);
        if (hasDefault) {
            strategySelect.value = defaultStrategy;
        }
        syncChannelMultVisibility(strategySelect.value);

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
        if (channelMidlineCheckbox) {
            channelMidlineCheckbox.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        if (channelLowerReclaimCheckbox) {
            channelLowerReclaimCheckbox.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        if (channelCurlSelect) {
            channelCurlSelect.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        if (slopedFullCandleCheckbox) {
            slopedFullCandleCheckbox.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        if (slopedWickCheckbox) {
            slopedWickCheckbox.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        if (slopedConfirmCandlesSelect) {
            slopedConfirmCandlesSelect.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        if (slopedInverseColorCheckbox) {
            slopedInverseColorCheckbox.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        if (slopedLineAngleSelect) {
            slopedLineAngleSelect.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        if (slopedStopLossSelect) {
            slopedStopLossSelect.onchange = () => {
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
            const isSlopedBreakout = (trade.strategy === 'sloped_lines') || (strategy === 'sloped_lines');
            const isMidlineCross = (trade.entry_reason === 'midline_cross') || (trade.notes && trade.notes.includes('midline_cross'));
            const isMidlineReclaim = (trade.entry_reason === 'midline_reclaim') || (trade.notes && trade.notes.includes('midline_reclaim'));
            const isChannelReclaim = (trade.entry_reason === 'channel_reclaim') || (trade.notes && trade.notes.includes('channel_reclaim'));
            const isChannelInflection = (trade.entry_reason === 'channel_inflection') || (trade.notes && trade.notes.includes('channel_inflection'));
            const isStopEntry = isStopLossReason(trade.entry_reason) || isStopLossReason(trade.notes);
            const entryPrefix = isStopEntry ? 'STOP LOSS ' : (isMidlineCross ? 'MID CROSS ' : (isMidlineReclaim ? 'MID RECLAIM ' : (isChannelReclaim ? 'LOWER RECLAIM ' : (isChannelInflection ? 'CHANNEL CURL ' : (isSlopedBreakout ? 'BREAKOUT ' : '')))));
            const entryColor = isMidlineCross ? '#0EA5E9' : (isMidlineReclaim ? '#3B82F6' : (isChannelReclaim ? '#06B6D4' : (isChannelInflection ? '#FACC15' : (isLong ? '#10B981' : '#F59E0B'))));

            // 1. Entry Marker
            markers.push({
                time: snappedEntry,
                position: isLong ? 'belowBar' : 'aboveBar',
                color: entryColor,
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
                const isSupportBreak = (trade.exit_reason === 'support_break');
                const isResistanceBreak = (trade.exit_reason === 'resistance_break');
                const isStopExit = isStopLossReason(trade.exit_reason) || isStopLossReason(trade.notes);
                const isMidlineCrossExit = (trade.exit_reason === 'midline_cross_exit') || (trade.notes && trade.notes.includes('midline_cross_exit'));
                const isMidStop = (trade.exit_reason === 'midline_stop_exit') || (trade.notes && trade.notes.includes('midline_stop'));
                const isChannelCurlExit = (trade.exit_reason === 'channel_curl_exit') || (trade.notes && trade.notes.includes('channel_curl_exit')) || (trade.exit_reason === 'channel_curl_sell');
                const exitPrefix = isSupportBreak ? 'SUPPORT BREAK ' : (isResistanceBreak ? 'RESISTANCE BREAK ' : (isChannelCurlExit ? 'CHANNEL CURL ' : (isMidlineCrossExit ? 'MID CROSS ' : (isMidStop ? 'MID STOP ' : (isStopExit ? 'STOP LOSS ' : '')))));
                const action = isLong ? 'SELL' : 'COVER';
                const exitColor = isSupportBreak ? '#3B82F6' : (isChannelCurlExit ? '#EC4899' : ((isMidStop || isStopExit) ? '#F43F5E' : (isWin ? '#10B981' : '#EF4444')));

                markers.push({
                    time: snappedExit,
                    position: isLong ? 'aboveBar' : 'belowBar',
                    color: exitColor,
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
            const isMidStop = (existing.text && existing.text.includes('MID STOP')) || (m.text && m.text.includes('MID STOP'));
            const isSL = (existing.text && existing.text.includes('STOP LOSS')) || (m.text && m.text.includes('STOP LOSS'));
            const isMid = (existing.text && existing.text.includes('MID RECLAIM')) || (m.text && m.text.includes('MID RECLAIM'));
            const isLowerReclaim = (existing.text && existing.text.includes('LOWER RECLAIM')) || (m.text && m.text.includes('LOWER RECLAIM'));
            const isCurlBuy = (existing.text && existing.text.includes('CHANNEL CURL BUY')) || (m.text && m.text.includes('CHANNEL CURL BUY'));
            const isCurlSell = (existing.text && existing.text.includes('CHANNEL CURL SELL')) || (m.text && m.text.includes('CHANNEL CURL SELL'));
            const action = m.position === 'belowBar' ? 'BUY' : 'SELL';
            let prefix = '';
            if (isCurlSell) prefix = 'CHANNEL CURL ';
            else if (isMidStop) prefix = 'MID STOP ';
            else if (isSL) prefix = 'STOP LOSS ';
            else if (isMid) prefix = 'MID RECLAIM ';
            else if (isLowerReclaim) prefix = 'LOWER RECLAIM ';
            else if (isCurlBuy) prefix = 'CHANNEL CURL ';
            existing.text = `${existing.count}x ${prefix}${action}`;
            if (isCurlSell && m.position === 'aboveBar') existing.color = '#EC4899';
            else if ((isMidStop || isSL) && m.position === 'aboveBar') existing.color = '#F43F5E';
            if (isMid && m.position === 'belowBar') existing.color = '#3B82F6';
            if (isLowerReclaim && m.position === 'belowBar') existing.color = '#06B6D4';
            if (isCurlBuy && m.position === 'belowBar') existing.color = '#FACC15';
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
async function fetchAndRenderTrendlines(symbol, chartInstance, candleData, existingSeriesList, strategy = 'enhanced_lines', fullCandle = true, timeframe = '1d', period = '1y', useWick = false, confirmCandles = 0, inverseColorTrigger = false, lineAngle = 0, stopLossMode = 'none') {
    // Remove previous trendline series
    existingSeriesList.forEach(s => {
        try { chartInstance.removeSeries(s); } catch (_) {}
    });
    existingSeriesList.length = 0;

    try {
        const fullCandleParam = (strategy === 'sloped_lines' || strategy === 'slope_lines') ? `&full_candle=${fullCandle}&use_wick=${useWick}&confirm_candles=${confirmCandles}&inverse_color_trigger=${inverseColorTrigger}&line_angle=${lineAngle}&stop_loss_mode=${encodeURIComponent(stopLossMode)}` : '';
        const res = await fetch(`/api/trendlines?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&timeframe=${encodeURIComponent(timeframe)}&period=${encodeURIComponent(period)}${fullCandleParam}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.trendlines || data.trendlines.length === 0) return;

        if (candleData.length === 0) return;
        const firstCandle = candleData[0].time;
        const lastCandle = candleData[candleData.length - 1].time;

        data.trendlines.forEach(tl => {
            const startTime = tl.start_time || toChartTime(tl.start_date);
            const endTime = tl.end_time || toChartTime(tl.end_date);

            // Only render lines that overlap with visible candle data
            if (endTime < firstCandle || startTime > lastCandle) return;

            let color;
            let lineStyle = 2; // default dashed
            if (strategy === 'sloped_lines') {
                // Descending resistance = green (breakout = buy)
                // Ascending support = blue (breakdown = sell)
                color = tl.color || (tl.type === 'resistance' ? '#10B981' : '#3B82F6');
                lineStyle = 0; // Solid line for sloped lines
            } else {
                color = tl.color || (tl.type === 'support' ? 'rgba(16, 185, 129, 0.6)' : 'rgba(245, 158, 11, 0.6)');
                lineStyle = 2; // Dashed for enhanced_lines
            }

            const snappedStart = findNearestCandleTime(startTime, candleData);
            let snappedEnd = findNearestCandleTime(endTime, candleData);

            if (snappedEnd <= snappedStart) {
                // Ensure strictly ascending time for Lightweight Charts
                const startIdx = candleData.findIndex(c => c.time === snappedStart);
                if (startIdx !== -1 && startIdx + 1 < candleData.length) {
                    snappedEnd = candleData[startIdx + 1].time;
                } else {
                    return;
                }
            }

            const seriesOptions = {
                color: color,
                lineWidth: 2,
                lineStyle: lineStyle,
                crosshairMarkerVisible: false,
                lastValueVisible: false,
                priceLineVisible: false,
                title: tl.label || '',
            };

            let lineSeries;
            if (typeof chartInstance.addLineSeries === 'function') {
                lineSeries = chartInstance.addLineSeries(seriesOptions);
            } else if (typeof chartInstance.addSeries === 'function' && typeof LightweightCharts.LineSeries !== 'undefined') {
                lineSeries = chartInstance.addSeries(LightweightCharts.LineSeries, seriesOptions);
            }

            if (lineSeries) {
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

function updateChannelLegend(containerId, isVisible, strategy = 'enhanced_channel') {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!isVisible) {
        el.style.display = 'none';
        el.innerHTML = '';
        return;
    }
    el.style.display = 'flex';
    if (strategy === 'sloped_lines') {
        el.innerHTML = `
            <div class="channel-pill"><span class="channel-dot" style="background: #10B981;"></span>Descending Resistance (Break = Buy)</div>
            <div class="channel-pill"><span class="channel-dot" style="background: #3B82F6;"></span>Ascending Support (Break = Sell)</div>
        `;
    } else if (strategy === 'enhanced_lines') {
        el.innerHTML = `
            <div class="channel-pill"><span class="channel-dot" style="background: #10B981;"></span>Support Trendline</div>
            <div class="channel-pill"><span class="channel-dot" style="background: #F59E0B;"></span>Resistance Trendline</div>
        `;
    } else {
        el.innerHTML = `
            <div class="channel-pill"><span class="channel-dot" style="background: #10B981;"></span>Tactical Lower (Buy Zone)</div>
            <div class="channel-pill"><span class="channel-dot" style="background: #EF4444;"></span>Tactical Upper (Take Profit)</div>
            <div class="channel-pill"><span class="channel-dot" style="background: #3B82F6;"></span>Tactical Mid (50b)</div>
            <div class="channel-pill"><span class="channel-dot" style="background: #F59E0B;"></span>Intermediate Mid (200b)</div>
            <div class="channel-pill"><span class="channel-dot" style="background: #A855F7;"></span>Macro Mid (1000b)</div>
        `;
    }
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
        const reqResolution = activeResolution || '1d';
        const reqPeriod = activeTimeframe || '1y';

        const slopedParam = (strategy === 'sloped_lines' || strategy === 'slope_lines')
            ? `&full_candle=${getFullCandleEnabled()}&use_wick=${getWickEnabled()}&confirm_candles=${getConfirmCandles()}&inverse_color_trigger=${getInverseColorTriggerEnabled()}&line_angle=${getLineAngle()}&stop_loss_mode=${encodeURIComponent(getStopLossMode())}`
            : '';
        const multParam = (strategy === 'enhanced_channel') 
            ? `&channel_mult=${getSelectedChannelMult()}&lookback=${getSelectedChannelLookback()}&use_stop_loss=${getChannelStoplossEnabled()}&midline_reentry=${getChannelMidlineEnabled()}&midline_cross=${getChannelMidlineEnabled()}&lower_reclaim=${getChannelLowerReclaimEnabled()}&channel_curl_mode=${encodeURIComponent(getChannelCurlMode())}&channel_inflection=${getChannelCurlEnabled()}&timeframe=${encodeURIComponent(reqResolution)}&period=${encodeURIComponent(reqPeriod)}` 
            : slopedParam;

        const [candlesRes, tradesRes, statsRes] = await Promise.all([
            fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(reqResolution)}&period=${encodeURIComponent(reqPeriod)}`),
            fetch(`/api/trades?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&timeframe=${encodeURIComponent(reqResolution)}&period=${encodeURIComponent(reqPeriod)}${multParam}`),
            fetch(`/api/stats?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&timeframe=${encodeURIComponent(reqResolution)}&period=${encodeURIComponent(reqPeriod)}${multParam}`)
        ]);

        const candlesData = candlesRes.ok ? await candlesRes.json() : { candles: [] };
        const tradesData = tradesRes.ok ? await tradesRes.json() : { trades: [] };
        const statsData = statsRes.ok ? await statsRes.json() : {};

        // Update range hint if actual period was clamped by Yahoo Finance (e.g. 30m max 60d)
        if (candlesData.period && candlesData.period !== reqPeriod) {
            const hintEl = document.getElementById('active-range-hint');
            if (hintEl) hintEl.textContent = `${reqPeriod.toUpperCase()} (${candlesData.period} Max Intraday)`;
        }

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

        // -- Overlays (enhanced_lines, sloped_lines, or enhanced_channel regression channels) --
        if (chart && (strategy === 'enhanced_lines' || strategy === 'sloped_lines') && sorted.length > 0) {
            channelSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            channelSeries.length = 0;
            updateChannelLegend('channel-legend', true, strategy);
            await fetchAndRenderTrendlines(symbol, chart, sorted, trendlineSeries, strategy, getFullCandleEnabled(), reqResolution, reqPeriod, getWickEnabled(), getConfirmCandles(), getInverseColorTriggerEnabled(), getLineAngle(), getStopLossMode());
        } else if (chart && strategy === 'enhanced_channel' && sorted.length > 0) {
            trendlineSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            trendlineSeries.length = 0;
            updateChannelLegend('channel-legend', true, strategy);
            await fetchAndRenderChannels(symbol, chart, sorted, channelSeries, reqResolution, reqPeriod);
        } else {
            updateChannelLegend('channel-legend', false);
            trendlineSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            trendlineSeries.length = 0;
            channelSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            channelSeries.length = 0;
        }

        if (chart) {
            chart.timeScale().fitContent();
        }

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
        const slopedAdvParam = (strategy === 'sloped_lines' || strategy === 'slope_lines')
            ? `&full_candle=${getFullCandleEnabled()}&use_wick=${getWickEnabled()}&confirm_candles=${getConfirmCandles()}&inverse_color_trigger=${getInverseColorTriggerEnabled()}&line_angle=${getLineAngle()}&stop_loss_mode=${encodeURIComponent(getStopLossMode())}`
            : '';
        const multParam = (strategy === 'enhanced_channel') 
            ? `&channel_mult=${getSelectedChannelMult()}&lookback=${getSelectedChannelLookback()}&use_stop_loss=${getChannelStoplossEnabled()}&midline_reentry=${getChannelMidlineEnabled()}&midline_cross=${getChannelMidlineEnabled()}&lower_reclaim=${getChannelLowerReclaimEnabled()}&channel_curl_mode=${encodeURIComponent(getChannelCurlMode())}&channel_inflection=${getChannelCurlEnabled()}&period=${encodeURIComponent(config.period)}` 
            : slopedAdvParam;
        const [candlesRes, tradesRes, statsRes] = await Promise.all([
            fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(config.interval)}&period=${encodeURIComponent(config.period)}`),
            fetch(`/api/trades?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}${multParam}`),
            fetch(`/api/stats?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}${multParam}`)
        ]);

        const candlesData = candlesRes.ok ? await candlesRes.json() : { candles: [] };
        const tradesData = tradesRes.ok ? await tradesRes.json() : { trades: [] };
        const statsData = statsRes.ok ? await statsRes.json() : {};

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

        // -- Overlays on Advanced (enhanced_lines, sloped_lines, or enhanced_channel) --
        if ((strategy === 'enhanced_lines' || strategy === 'sloped_lines') && sorted.length > 0) {
            advChannelSeries.forEach(s => { try { advChart.removeSeries(s); } catch (_) {} });
            advChannelSeries.length = 0;
            updateChannelLegend('adv-channel-legend', true, strategy);
            await fetchAndRenderTrendlines(symbol, advChart, sorted, advTrendlineSeries, strategy, getFullCandleEnabled(), config.interval, config.period, getWickEnabled(), getConfirmCandles(), getInverseColorTriggerEnabled(), getLineAngle(), getStopLossMode());
        } else if (strategy === 'enhanced_channel' && sorted.length > 0) {
            advTrendlineSeries.forEach(s => { try { advChart.removeSeries(s); } catch (_) {} });
            advTrendlineSeries.length = 0;
            updateChannelLegend('adv-channel-legend', true, strategy);
            await fetchAndRenderChannels(symbol, advChart, sorted, advChannelSeries, config.interval, config.period);
        } else {
            updateChannelLegend('adv-channel-legend', false);
            advTrendlineSeries.forEach(s => { try { advChart.removeSeries(s); } catch (_) {} });
            advTrendlineSeries.length = 0;
            advChannelSeries.forEach(s => { try { advChart.removeSeries(s); } catch (_) {} });
            advChannelSeries.length = 0;
        }

        // -- Update Top Stats Cards for Current Period --
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
