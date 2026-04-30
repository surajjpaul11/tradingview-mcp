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

// ============================================================
// STEP 1: Initialize TradingView chart
// ============================================================
function initChart() {
    const container = document.getElementById('tv-chart');
    if (!container) { console.error('[TV] No chart container found'); return; }

    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: container.clientHeight,
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

    candlestickSeries = chart.addCandlestickSeries({
        upColor: '#10B981',
        downColor: '#EF4444',
        borderVisible: false,
        wickUpColor: '#10B981',
        wickDownColor: '#EF4444'
    });

    new ResizeObserver(() => {
        chart.applyOptions({
            width: container.clientWidth,
            height: container.clientHeight
        });
    }).observe(container);
}

// ============================================================
// STEP 2: Load filter dropdowns from /api/filters
// ============================================================
async function loadFilters() {
    try {
        const res = await fetch('/api/filters');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // Populate ticker dropdown
        tickerSelect.innerHTML = '';
        if (data.symbols.length === 0) {
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
        data.strategies.forEach(strat => {
            const opt = document.createElement('option');
            opt.value = strat;
            opt.textContent = strat;
            strategySelect.appendChild(opt);
        });

        // Wire up change listeners
        tickerSelect.addEventListener('change', updateDashboard);
        strategySelect.addEventListener('change', updateDashboard);

        // Trigger initial data load
        if (data.symbols.length > 0) {
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
    if (active) loadingOverlay.classList.add('active');
    else loadingOverlay.classList.remove('active');
}

function toChartTime(isoString) {
    return Math.floor(new Date(isoString).getTime() / 1000);
}

// ============================================================
// STEP 3: Update chart + stats based on current filter state
// ============================================================
async function updateDashboard() {
    const symbol = tickerSelect.value;
    const strategy = strategySelect.value;
    if (!symbol) return;

    setLoading(true);

    try {
        const [candlesRes, tradesRes, statsRes] = await Promise.all([
            fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}`),
            fetch(`/api/trades?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}`),
            fetch(`/api/stats?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}`)
        ]);

        const candlesData = await candlesRes.json();
        const tradesData = await tradesRes.json();
        const statsData = await statsRes.json();

        // -- Candles --
        const sorted = candlesData.candles
            .sort((a, b) => a.time - b.time)
            .filter((c, i, arr) => i === 0 || c.time !== arr[i - 1].time); // deduplicate

        if (candlestickSeries) candlestickSeries.setData(sorted);

        // -- Trade Markers --
        const markers = tradesData.trades.map(trade => ({
            time: toChartTime(trade.created_at),
            position: trade.side.toLowerCase() === 'buy' ? 'belowBar' : 'aboveBar',
            color: trade.side.toLowerCase() === 'buy' ? '#10B981' : '#EF4444',
            shape: trade.side.toLowerCase() === 'buy' ? 'arrowUp' : 'arrowDown',
            text: `${trade.strategy} ${trade.side} @ ${trade.entry_price}`
        })).sort((a, b) => a.time - b.time);

        if (candlestickSeries) candlestickSeries.setMarkers(markers);
        if (chart) chart.timeScale().fitContent();

        // -- Stats --
        const pnl = statsData.total_pnl_usd || 0;
        pnlVal.textContent = `$${pnl.toFixed(2)}`;
        pnlVal.className = 'stat-value' + (pnl > 0 ? ' profit' : pnl < 0 ? ' loss' : '');
        winrateVal.textContent = `${statsData.win_rate_pct || 0}%`;
        totalTradesVal.textContent = statsData.total_trades || 0;

    } catch (err) {
        console.error('[TV] updateDashboard failed:', err);
    } finally {
        setLoading(false);
    }
}

// ============================================================
// Bootstrap — scripts are at bottom of body so DOM is ready
// ============================================================
(function bootstrap() {
    if (typeof LightweightCharts === 'undefined') {
        console.error('[TV] LightweightCharts not loaded');
        document.getElementById('tv-chart').innerHTML =
            '<p style="color:#EF4444;padding:2rem;text-align:center;">Chart library failed to load from CDN.<br>Check your internet connection and reload the page.</p>';
        loadFilters(); // still load the dropdowns
        return;
    }
    initChart();
    loadFilters();
})();
