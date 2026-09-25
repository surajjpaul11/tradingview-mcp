// ============================================================
// Trade Visualizer — app.js
// ============================================================

// ----- Core DOM References -----
const tickerSelect = document.getElementById('ticker-select');
const strategySelect = document.getElementById('strategy-select');
const tradingWindowSelect = document.getElementById('trading-window-select');
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
const marketRefreshStatus = document.getElementById('market-refresh-status');
const volumeIndicatorCheckbox = document.getElementById('volume-indicator-checkbox');
const rsiIndicatorCheckbox = document.getElementById('rsi-indicator-checkbox');
const indicatorStack = document.getElementById('indicator-stack');
const volumeIndicatorPane = document.getElementById('volume-indicator-pane');
const rsiIndicatorPane = document.getElementById('rsi-indicator-pane');
let lastDataRefreshAt = 0;
let marketStatusTimer = null;
let autoRefreshInFlight = false;
let filtersLoaded = false;
const ACTIVE_TAB_STORAGE_KEY = 'trade-visualizer-active-tab';
const LEGACY_BEFORE_HOURS_STORAGE_KEY = 'trade-visualizer-before-hours';
const LEGACY_AFTER_HOURS_STORAGE_KEY = 'trade-visualizer-after-hours';
const MARKET_TIME_ZONE = 'America/New_York';

function chartTimeToDate(time) {
    if (typeof time === 'number') return new Date(time * 1000);
    if (typeof time === 'string') return new Date(`${time}T12:00:00Z`);
    if (time && typeof time === 'object') {
        return new Date(Date.UTC(time.year, time.month - 1, time.day, 12));
    }
    return null;
}

function formatMarketChartTime(time, includeDate = true, includeZone = false) {
    const date = chartTimeToDate(time);
    if (!date || Number.isNaN(date.getTime())) return '';
    return new Intl.DateTimeFormat('en-US', {
        timeZone: MARKET_TIME_ZONE,
        ...(includeDate ? { month: 'short', day: 'numeric' } : {}),
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        ...(includeZone ? { timeZoneName: 'short' } : {}),
    }).format(date);
}

function formatMarketAxisTick(time, tickMarkType) {
    const date = chartTimeToDate(time);
    if (!date || Number.isNaN(date.getTime())) return '';

    // Lightweight Charts uses 0/1/2 for year, month, and day ticks, and
    // 3/4 for intraday time ticks. Keep session-heavy intraday charts compact
    // while still marking each date boundary selected by the chart library.
    if (tickMarkType === 0) {
        return new Intl.DateTimeFormat('en-US', {
            timeZone: MARKET_TIME_ZONE,
            year: 'numeric',
        }).format(date);
    }
    if (tickMarkType === 1) {
        return new Intl.DateTimeFormat('en-US', {
            timeZone: MARKET_TIME_ZONE,
            month: 'short',
        }).format(date);
    }
    if (tickMarkType === 2) {
        return new Intl.DateTimeFormat('en-US', {
            timeZone: MARKET_TIME_ZONE,
            month: 'short',
            day: 'numeric',
        }).format(date);
    }

    const parts = new Intl.DateTimeFormat('en-US', {
        timeZone: MARKET_TIME_ZONE,
        hour: 'numeric',
        minute: '2-digit',
        hourCycle: 'h23',
    }).formatToParts(date);
    const hour = Number(parts.find(part => part.type === 'hour')?.value ?? 0);
    const minute = parts.find(part => part.type === 'minute')?.value ?? '00';
    return minute === '00' ? String(hour) : `${hour}:${minute}`;
}

const marketChartOptions = {
    localization: {
        locale: 'en-US',
        timeFormatter: time => formatMarketChartTime(time, true, true),
    },
    timeScale: {
        tickMarkFormatter: (time, tickMarkType) => formatMarketAxisTick(time, tickMarkType),
    },
};

const VIEWPORT_CANDLES_BY_RESOLUTION = {
    '30m': 120,
    '1h': 120,
    '4h': 110,
    '12h': 100,
    '1d': 180,
    '5d': 160,
};

const VIEWPORT_CANDLES_BY_RANGE = {
    '3mo': 90,
    '1y': 140,
    '5y': 180,
    'max': 220,
};

function visibleCandleTarget(resolution, range) {
    const resolutionTarget = VIEWPORT_CANDLES_BY_RESOLUTION[resolution] || 120;
    const rangeTarget = VIEWPORT_CANDLES_BY_RANGE[range] || 140;
    return Math.min(resolutionTarget, rangeTarget);
}

function firstBuyCandleIndex(candles, tradesData) {
    const entryTimes = (tradesData?.trades || [])
        .filter(trade => ['buy', 'long'].includes(String(trade.side || '').toLowerCase()))
        .map(trade => toChartTime(trade.created_at))
        .filter(Number.isFinite)
        .sort((a, b) => a - b);
    if (!entryTimes.length) return -1;
    const firstBuyTime = entryTimes[0];
    let nearestIndex = 0;
    let nearestDistance = Math.abs(candles[0].time - firstBuyTime);
    for (let index = 1; index < candles.length; index += 1) {
        const distance = Math.abs(candles[index].time - firstBuyTime);
        if (distance < nearestDistance) {
            nearestDistance = distance;
            nearestIndex = index;
        }
    }
    return nearestIndex;
}

function applyInitialChartViewport(targetChart, candles, tradesData, resolution, range) {
    if (!targetChart || !candles?.length) return null;
    const target = Math.max(20, visibleCandleTarget(resolution, range));
    const buyIndex = firstBuyCandleIndex(candles, tradesData);
    const startIndex = buyIndex >= 0
        ? Math.max(0, buyIndex - 2)
        : Math.max(0, candles.length - target);
    const endIndex = Math.min(candles.length - 1, startIndex + target - 1);
    const logicalRange = { from: startIndex - 0.5, to: endIndex + 0.5 };
    targetChart.timeScale().setVisibleLogicalRange(logicalRange);
    return { startIndex, endIndex, buyIndex, target };
}

function recordChartRenderState(candles, tradesData, resolution, range, viewport, strategy, symbol, overlays = {}) {
    const container = document.getElementById('tv-chart');
    if (!container) return;
    container.dataset.renderStatus = candles.length ? 'ready' : 'empty';
    container.dataset.candleCount = String(candles.length);
    container.dataset.resolution = resolution;
    container.dataset.timeframe = range;
    container.dataset.strategy = strategy || '';
    container.dataset.symbol = symbol || '';
    container.dataset.firstBuyIndex = String(viewport?.buyIndex ?? -1);
    container.dataset.visibleStartIndex = String(viewport?.startIndex ?? -1);
    container.dataset.visibleEndIndex = String(viewport?.endIndex ?? -1);
    container.dataset.tradeCount = String(tradesData?.trades?.length ?? 0);
    container.dataset.markerCount = String(overlays.markerCount ?? 0);
    container.dataset.trendlinesReturned = String(overlays.trendlinesReturned ?? 0);
    container.dataset.trendlinesDrawn = String(overlays.trendlinesDrawn ?? 0);
}

function refreshMainChartLayout() {
    const container = document.getElementById('tv-chart');
    if (!container || !chart) return;
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;
    if (width > 50 && height > 50) chart.applyOptions({ width, height });
}

function getActiveTradingWindow() {
    return tradingWindowSelect?.value || 'regular market';
}

function tradingWindowFromLegacySessionPreferences(beforeValue, afterValue) {
    const beforeHours = beforeValue === 'true';
    const afterHours = afterValue === 'true';
    if (beforeHours && afterHours) return 'extended hours';
    if (beforeHours) return 'pre-market';
    if (afterHours) return 'after hours';
    return null;
}

function consumeLegacyTradingWindow() {
    const beforeValue = localStorage.getItem(LEGACY_BEFORE_HOURS_STORAGE_KEY);
    const afterValue = localStorage.getItem(LEGACY_AFTER_HOURS_STORAGE_KEY);
    if (beforeValue === null && afterValue === null) return null;
    localStorage.removeItem(LEGACY_BEFORE_HOURS_STORAGE_KEY);
    localStorage.removeItem(LEGACY_AFTER_HOURS_STORAGE_KEY);
    return tradingWindowFromLegacySessionPreferences(beforeValue, afterValue);
}

const TRADING_WINDOW_SESSIONS = {
    'regular market': ['regular market'],
    'pre-market': ['pre-market', 'regular market'],
    'after hours': ['regular market', 'after hours'],
    'extended hours': ['pre-market', 'regular market', 'after hours'],
    overnight: ['overnight', 'pre-market', 'regular market', 'after hours'],
};

function activeTradingWindowIncludes(session) {
    const sessions = TRADING_WINDOW_SESSIONS[getActiveTradingWindow()] || TRADING_WINDOW_SESSIONS['regular market'];
    return sessions.includes(session);
}

function filterCandlesForVisibleSessions(candles) {
    return candles.filter(candle => activeTradingWindowIncludes(sessionLabelForCandle(candle)));
}

function ensureIntradayResolutionForExtendedWindow() {
    const extended = getActiveTradingWindow() !== 'regular market';
    if (!extended) return;
    if (!['30m', '1h', '4h', '12h'].includes(activeResolution)) {
        activeResolution = '30m';
        activeTimeframe = '3mo';
        document.querySelectorAll('#resolution-btn-group .res-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.res === '30m');
        });
        document.querySelectorAll('#timeframe-btn-group .range-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.range === '3mo');
        });
        const resHint = document.getElementById('active-res-hint');
        const rangeHint = document.getElementById('active-range-hint');
        if (resHint) resHint.textContent = '30 Minutes (30m)';
        if (rangeHint) rangeHint.textContent = '3 Months (Yahoo 60d Max Intraday)';
    }
    if (['ytd', '1y', '5y'].includes(advActiveRange)) {
        advActiveRange = '1d';
        document.querySelectorAll('.adv-tf-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.advRange === '1d');
        });
        const advHint = document.getElementById('adv-range-hint');
        if (advHint) advHint.textContent = ADV_RANGE_CONFIG['1d'].label;
    }
}

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
const slopedAnchorBarsGroup = document.getElementById('sloped-anchor-bars-group');
const slopedAnchorBarsSelect = document.getElementById('sloped-anchor-bars-select');

function getFullCandleEnabled() {
    if (!slopedFullCandleCheckbox) return false;
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

function getMinAnchorBars() {
    if (!slopedAnchorBarsSelect) return 2;
    const val = parseInt(slopedAnchorBarsSelect.value, 10);
    return isNaN(val) ? 2 : val;
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
    if (slopedAnchorBarsGroup) slopedAnchorBarsGroup.style.display = isSloped ? 'flex' : 'none';
}

const bestParamsBadgeGroup = document.getElementById('best-params-badge-group');
const bestParamsBadge = document.getElementById('best-params-badge');

async function applyBestParametersIfAvailable(strategy, symbol) {
    if (!strategy || !symbol || strategy === 'all') {
        if (bestParamsBadgeGroup) bestParamsBadgeGroup.style.display = 'none';
        return;
    }
    try {
        const res = await fetch(`/api/best-parameters?strategy=${encodeURIComponent(strategy)}&symbol=${encodeURIComponent(symbol)}`);
        if (!res.ok) {
            if (bestParamsBadgeGroup) bestParamsBadgeGroup.style.display = 'none';
            return;
        }
        const result = await res.json();
        if (!result.found || !result.data || !result.data.parameters) {
            if (bestParamsBadgeGroup) bestParamsBadgeGroup.style.display = 'none';
            return;
        }

        const p = result.data.parameters;

        // Sloped Lines strategy controls
        if (strategy === 'sloped_lines' || strategy === 'slope_lines') {
            if (typeof p.full_candle === 'boolean' && slopedFullCandleCheckbox) {
                slopedFullCandleCheckbox.checked = p.full_candle;
            }
            if (typeof p.use_wick === 'boolean' && slopedWickCheckbox) {
                slopedWickCheckbox.checked = p.use_wick;
            }
            if (p.confirm_candles !== undefined && slopedConfirmCandlesSelect) {
                slopedConfirmCandlesSelect.value = String(p.confirm_candles);
            }
            if (typeof p.inverse_color_trigger === 'boolean' && slopedInverseColorCheckbox) {
                slopedInverseColorCheckbox.checked = p.inverse_color_trigger;
            }
            if (p.line_angle !== undefined && slopedLineAngleSelect) {
                const angleTarget = parseFloat(p.line_angle);
                for (const opt of slopedLineAngleSelect.options) {
                    if (parseFloat(opt.value) === angleTarget) {
                        slopedLineAngleSelect.value = opt.value;
                        break;
                    }
                }
            }
            if (p.stop_loss_mode && slopedStopLossSelect) {
                slopedStopLossSelect.value = p.stop_loss_mode;
            }
            if (p.min_anchor_bars !== undefined && slopedAnchorBarsSelect) {
                slopedAnchorBarsSelect.value = String(p.min_anchor_bars);
            }
        }

        // Enhanced Channel strategy controls
        if (strategy === 'enhanced_channel') {
            if (p.channel_multiplier !== undefined && channelMultSelect) {
                channelMultSelect.value = String(p.channel_multiplier);
            } else if (p.channel_mult !== undefined && channelMultSelect) {
                channelMultSelect.value = String(p.channel_mult);
            }
            if (p.lookback !== undefined && channelLookbackSelect) {
                channelLookbackSelect.value = String(p.lookback);
            }
            if (typeof p.use_stop_loss === 'boolean' && channelStoplossCheckbox) {
                channelStoplossCheckbox.checked = p.use_stop_loss;
            }
            if (typeof p.midline_cross === 'boolean' && channelMidlineCheckbox) {
                channelMidlineCheckbox.checked = p.midline_cross;
            }
            if (typeof p.lower_reclaim === 'boolean' && channelLowerReclaimCheckbox) {
                channelLowerReclaimCheckbox.checked = p.lower_reclaim;
            }
            if (p.channel_curl_mode && channelCurlSelect) {
                channelCurlSelect.value = p.channel_curl_mode;
            }
        }

        // Timeframe & Resolution if specified in config
        if (result.data.timeframe && result.data.timeframe !== activeResolution) {
            activeResolution = result.data.timeframe;
            document.querySelectorAll('#resolution-btn-group .res-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.res === activeResolution);
            });
        }
        if (result.data.period && result.data.period !== activeTimeframe) {
            activeTimeframe = result.data.period;
            document.querySelectorAll('#timeframe-btn-group .range-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.range === activeTimeframe);
            });
        }

        // Display Best Params badge
        if (bestParamsBadgeGroup && bestParamsBadge) {
            const perf = result.data.performance || {};
            const pnlText = perf.total_pnl_pct !== undefined
                ? ` (${perf.total_pnl_pct >= 0 ? '+' : ''}${perf.total_pnl_pct}%)`
                : '';
            const beatsText = perf.beats_bnh_pct !== undefined
                ? ` · ${perf.beats_bnh_pct >= 0 ? '+' : ''}${perf.beats_bnh_pct}% vs B&H (B&H: ${perf.buy_and_hold_pct}%)`
                : '';
            const baselineContext = [result.data.timeframe, result.data.period].filter(Boolean).join(' / ').toUpperCase();
            const updatedText = result.data.last_updated ? ` · captured ${result.data.last_updated}` : '';
            bestParamsBadge.innerHTML = `<span class="star-icon">★</span> Saved Best${pnlText} baseline`;
            bestParamsBadge.title = `Historical optimization snapshot for ${symbol} · ${strategy}${baselineContext ? ` · ${baselineContext}` : ''}${updatedText}${beatsText}. Current P&L cards are recalculated using the current strategy engine, data, range, and trading window.`;
            bestParamsBadgeGroup.style.display = 'flex';
        }
    } catch (e) {
        console.warn('[TV] Error applying best parameters:', e);
        if (bestParamsBadgeGroup) bestParamsBadgeGroup.style.display = 'none';
    }
}

// ----- Chart Globals (Regular Tab) -----
let chart = null;
let candlestickSeries = null;
let activeResolution = '1d'; // Default: 1D candles
let activeTimeframe = '1y';  // Default: 1-Year range
let trendlineSeries = []; // LineSeries for trendline overlays
let volumeChart = null;
let volumeSeries = null;
let rsiChart = null;
let rsiSeries = null;
let rsiUpperGuide = null;
let rsiLowerGuide = null;
let rsiBoundsSeries = null;
let currentCandles = [];
let sessionZoneFrame = null;
let chartDataUpdateInProgress = false;
let dashboardRequestGeneration = 0;

// ----- Chart Globals (Advanced Tab) -----
let advChart = null;
let advCandlestickSeries = null;
let advCurrentCandles = [];
let advActiveRange = '1y'; // Default: 1-Year daily
let advTrendlineSeries = [];

// ----- Tab State -----
let activeTab = 'regular';

function sessionLabelForCandle(candle) {
    if (candle?.session) return candle.session;
    if (!candle?.time) return 'regular market';
    const parts = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(new Date(candle.time * 1000));
    const hour = Number(parts.find(part => part.type === 'hour')?.value || 0);
    const minute = Number(parts.find(part => part.type === 'minute')?.value || 0);
    const clock = (hour * 60) + minute;
    if (clock >= 240 && clock < 570) return 'pre-market';
    if (clock >= 570 && clock < 960) return 'regular market';
    if (clock >= 960 && clock < 1200) return 'after hours';
    return 'overnight';
}

function ensureSessionZoneLayer(container) {
    if (!container) return null;
    let layer = container.querySelector(':scope > .session-zone-layer');
    if (!layer) {
        layer = document.createElement('div');
        layer.className = 'session-zone-layer';
        container.appendChild(layer);
    }
    return layer;
}

function renderSessionZones(targetChart, containerId, candles) {
    const container = document.getElementById(containerId);
    const layer = ensureSessionZoneLayer(container);
    if (!layer) return 0;
    layer.replaceChildren();
    if (!targetChart || !candles?.length || !['30m', '1h', '4h', '12h'].includes(activeResolution)) return 0;

    const points = candles.map(candle => ({
        candle,
        session: sessionLabelForCandle(candle),
        x: targetChart.timeScale().timeToCoordinate(candle.time),
    }));
    const groups = [];
    for (let index = 0; index < points.length; index += 1) {
        const point = points[index];
        if (!['pre-market', 'after hours'].includes(point.session) || point.x == null) continue;
        if (!activeTradingWindowIncludes(point.session)) continue;
        const previous = groups.at(-1);
        if (previous && previous.session === point.session && previous.end === index - 1) {
            previous.end = index;
        } else {
            groups.push({ session: point.session, start: index, end: index });
        }
    }

    const containerWidth = container.clientWidth;
    groups.forEach(group => {
        const first = points[group.start];
        const last = points[group.end];
        const previousX = points[group.start - 1]?.x;
        const nextX = points[group.end + 1]?.x;
        const fallbackStep = Math.max(2, Math.abs((nextX ?? last.x + 8) - (previousX ?? first.x - 8)) / Math.max(2, group.end - group.start + 2));
        const left = previousX == null ? first.x - fallbackStep / 2 : (previousX + first.x) / 2;
        const right = nextX == null ? last.x + fallbackStep / 2 : (last.x + nextX) / 2;
        const clippedLeft = Math.max(0, left);
        const clippedRight = Math.min(containerWidth, right);
        if (clippedRight <= clippedLeft) return;
        const zone = document.createElement('div');
        zone.className = `session-zone ${group.session.replace(' ', '-')}`;
        zone.style.left = `${clippedLeft}px`;
        zone.style.width = `${clippedRight - clippedLeft}px`;
        zone.title = group.session;
        layer.appendChild(zone);
    });
    return layer.childElementCount;
}

function renderAllSessionZones() {
    sessionZoneFrame = null;
    const zoneCount = renderSessionZones(chart, 'tv-chart', currentCandles);
    if (volumeChart) renderSessionZones(volumeChart, 'volume-chart', currentCandles);
    if (rsiChart) renderSessionZones(rsiChart, 'rsi-chart', currentCandles);
    const legend = document.getElementById('session-zone-legend');
    if (legend) {
        const visibleSessions = new Set(currentCandles.map(sessionLabelForCandle));
        const preMarketItem = legend.querySelector('.session-swatch.pre-market')?.parentElement;
        const afterHoursItem = legend.querySelector('.session-swatch.after-hours')?.parentElement;
        if (preMarketItem) preMarketItem.hidden = !activeTradingWindowIncludes('pre-market') || !visibleSessions.has('pre-market');
        if (afterHoursItem) afterHoursItem.hidden = !activeTradingWindowIncludes('after hours') || !visibleSessions.has('after hours');
        legend.hidden = zoneCount === 0;
    }
}

function scheduleSessionZoneRender() {
    if (sessionZoneFrame != null) cancelAnimationFrame(sessionZoneFrame);
    sessionZoneFrame = requestAnimationFrame(renderAllSessionZones);
}

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
    localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, tab);

    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    const sidebar = document.querySelector('.tab-sidebar');
    sidebar?.classList.toggle('advanced-mode', tab === 'advanced');
    document.getElementById('panel-regular')?.classList.add('active');
    updateIndicatorVisibility();

    refreshMainChartLayout();
    requestAnimationFrame(() => requestAnimationFrame(refreshMainChartLayout));
    scheduleSessionZoneRender();
    if (filtersLoaded) {
        ensureIntradayResolutionForExtendedWindow();
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
        ...marketChartOptions,
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
            ...marketChartOptions.timeScale,
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
                scheduleSessionZoneRender();
            }
        }
    }).observe(container);

    chart.timeScale().subscribeVisibleTimeRangeChange(range => {
        scheduleSessionZoneRender();
        if (!range || activeTab !== 'advanced' || chartDataUpdateInProgress) return;
        safelySetIndicatorRange(volumeChart, volumeIndicatorCheckbox?.checked, range);
        safelySetIndicatorRange(rsiChart, rsiIndicatorCheckbox?.checked, range);
    });
}

function createIndicatorChart(container, height) {
    const indicatorChart = LightweightCharts.createChart(container, {
        ...marketChartOptions,
        width: container.clientWidth || 800,
        height,
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#94A3B8',
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
        },
        timeScale: {
            ...marketChartOptions.timeScale,
            borderColor: 'rgba(255, 255, 255, 0.1)',
            timeVisible: true,
            secondsVisible: false,
        },
        rightPriceScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
            scaleMargins: { top: 0.12, bottom: 0.12 },
        },
        crosshair: {
            mode: 1,
            vertLine: { color: '#3B82F6', labelBackgroundColor: '#3B82F6' },
            horzLine: { color: '#3B82F6', labelBackgroundColor: '#3B82F6' },
        },
        handleScroll: false,
        handleScale: false,
    });

    new ResizeObserver(entries => {
        const width = container.clientWidth || entries[0]?.contentRect?.width || 800;
        if (width > 50) {
            indicatorChart.applyOptions({ width, height });
            scheduleSessionZoneRender();
        }
    }).observe(container);
    return indicatorChart;
}

function addLineSeriesCompat(targetChart, options) {
    if (typeof targetChart.addLineSeries === 'function') return targetChart.addLineSeries(options);
    if (typeof targetChart.addSeries === 'function' && LightweightCharts.LineSeries) {
        return targetChart.addSeries(LightweightCharts.LineSeries, options);
    }
    return null;
}

function initIndicatorCharts() {
    const volumeContainer = document.getElementById('volume-chart');
    if (!volumeChart && volumeContainer) {
        volumeChart = createIndicatorChart(volumeContainer, 138);
        const options = {
            priceFormat: { type: 'volume' },
            priceLineVisible: false,
            lastValueVisible: true,
        };
        if (typeof volumeChart.addHistogramSeries === 'function') {
            volumeSeries = volumeChart.addHistogramSeries(options);
        } else if (typeof volumeChart.addSeries === 'function' && LightweightCharts.HistogramSeries) {
            volumeSeries = volumeChart.addSeries(LightweightCharts.HistogramSeries, options);
        }
    }

    const rsiContainer = document.getElementById('rsi-chart');
    if (!rsiChart && rsiContainer) {
        rsiChart = createIndicatorChart(rsiContainer, 138);
        rsiSeries = addLineSeriesCompat(rsiChart, {
            color: '#A78BFA',
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: true,
        });
        rsiUpperGuide = addLineSeriesCompat(rsiChart, {
            color: 'rgba(239, 68, 68, 0.55)',
            lineWidth: 1,
            lineStyle: 2,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        rsiLowerGuide = addLineSeriesCompat(rsiChart, {
            color: 'rgba(16, 185, 129, 0.55)',
            lineWidth: 1,
            lineStyle: 2,
            priceLineVisible: false,
            lastValueVisible: false,
        });
        rsiBoundsSeries = addLineSeriesCompat(rsiChart, {
            color: 'rgba(0, 0, 0, 0)',
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
        });
    }
}

function calculateRSI(candles, period = 14) {
    if (!candles || candles.length <= period) return [];
    let gains = 0;
    let losses = 0;
    for (let i = 1; i <= period; i += 1) {
        const change = candles[i].close - candles[i - 1].close;
        gains += Math.max(change, 0);
        losses += Math.max(-change, 0);
    }
    let avgGain = gains / period;
    let avgLoss = losses / period;
    const values = [];
    const rsiValue = () => avgLoss === 0 ? 100 : 100 - (100 / (1 + (avgGain / avgLoss)));
    values.push({ time: candles[period].time, value: Number(rsiValue().toFixed(2)) });

    for (let i = period + 1; i < candles.length; i += 1) {
        const change = candles[i].close - candles[i - 1].close;
        avgGain = ((avgGain * (period - 1)) + Math.max(change, 0)) / period;
        avgLoss = ((avgLoss * (period - 1)) + Math.max(-change, 0)) / period;
        values.push({ time: candles[i].time, value: Number(rsiValue().toFixed(2)) });
    }
    return values;
}

function safelySetIndicatorRange(indicatorChart, enabled, range) {
    if (!indicatorChart || !enabled || !range) return;
    try {
        indicatorChart.timeScale().setVisibleRange(range);
    } catch (_) {
        // A series can briefly have no logical range while its data is replaced.
        // The post-render synchronization below will retry once every series is ready.
    }
}

function syncIndicatorRanges() {
    if (!chart || chartDataUpdateInProgress) return;
    let range;
    try {
        range = chart.timeScale().getVisibleRange();
    } catch (_) {
        return;
    }
    if (!range) return;
    safelySetIndicatorRange(volumeChart, volumeIndicatorCheckbox?.checked, range);
    safelySetIndicatorRange(rsiChart, rsiIndicatorCheckbox?.checked, range);
}

function renderAdvancedIndicators(candles) {
    if (!candles || activeTab !== 'advanced') return;
    initIndicatorCharts();

    if (volumeSeries) {
        const volumeData = candles.map(candle => ({
            time: candle.time,
            value: Number(candle.volume || 0),
            color: candle.close >= candle.open ? 'rgba(16, 185, 129, 0.65)' : 'rgba(239, 68, 68, 0.65)',
        }));
        volumeSeries.setData(volumeData);
        const latestVolume = volumeData.at(-1)?.value;
        const value = document.getElementById('volume-indicator-value');
        if (value) value.textContent = latestVolume == null ? '—' : Intl.NumberFormat(undefined, { notation: 'compact' }).format(latestVolume);
        const volumeContainer = document.getElementById('volume-chart');
        if (volumeContainer) volumeContainer.dataset.pointCount = String(volumeData.length);
    }

    const rsiData = calculateRSI(candles);
    if (rsiSeries) rsiSeries.setData(rsiData);
    if (rsiData.length > 0) {
        const firstTime = rsiData[0].time;
        const lastTime = rsiData[rsiData.length - 1].time;
        rsiUpperGuide?.setData([{ time: firstTime, value: 70 }, { time: lastTime, value: 70 }]);
        rsiLowerGuide?.setData([{ time: firstTime, value: 30 }, { time: lastTime, value: 30 }]);
        rsiBoundsSeries?.setData([{ time: firstTime, value: 0 }, { time: lastTime, value: 100 }]);
    }
    const rsiValue = document.getElementById('rsi-indicator-value');
    if (rsiValue) rsiValue.textContent = rsiData.length ? rsiData[rsiData.length - 1].value.toFixed(2) : '—';
    const rsiContainer = document.getElementById('rsi-chart');
    if (rsiContainer) rsiContainer.dataset.pointCount = String(rsiData.length);
    requestAnimationFrame(() => {
        syncIndicatorRanges();
        scheduleSessionZoneRender();
    });
}

function updateIndicatorVisibility() {
    const advanced = activeTab === 'advanced';
    const showVolume = advanced && Boolean(volumeIndicatorCheckbox?.checked);
    const showRsi = advanced && Boolean(rsiIndicatorCheckbox?.checked);
    indicatorStack?.classList.toggle('active', advanced && (showVolume || showRsi));
    volumeIndicatorPane?.classList.toggle('active', showVolume);
    rsiIndicatorPane?.classList.toggle('active', showRsi);
    if (advanced) {
        requestAnimationFrame(() => {
            renderAdvancedIndicators(currentCandles);
            syncIndicatorRanges();
            refreshMainChartLayout();
        });
    }
}

// ============================================================
// STEP 1b: Initialize Advanced TradingView chart
// ============================================================
function initAdvChart() {
    const container = document.getElementById('adv-chart');
    if (!container) return;

    container.innerHTML = '';

    advChart = LightweightCharts.createChart(container, {
        ...marketChartOptions,
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
            ...marketChartOptions.timeScale,
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
        const [res, marketRes] = await Promise.all([
            fetch('/api/filters'),
            fetch('/api/market-status', { cache: 'no-store' }),
        ]);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (marketRes.ok && tradingWindowSelect) {
            const marketData = await marketRes.json();
            const configuredWindow = marketData.configured_default_window || 'regular market';
            const migratedWindow = consumeLegacyTradingWindow();
            tradingWindowSelect.value = migratedWindow || configuredWindow;
            if (migratedWindow && migratedWindow !== configuredWindow) {
                try {
                    const selectedWindow = encodeURIComponent(migratedWindow);
                    const response = await fetch(`/api/trading-window?trading_window=${selectedWindow}`, { method: 'POST' });
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                } catch (err) {
                    console.warn('[TV] Could not persist migrated trading window:', err);
                }
            }
            ensureIntradayResolutionForExtendedWindow();
        }

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
        tickerSelect.onchange = async () => {
            await applyBestParametersIfAvailable(strategySelect.value, tickerSelect.value);
            ensureIntradayResolutionForExtendedWindow();
            updateDashboard();
            if (activeTab === 'advanced' && advChart) updateAdvDashboard();
        };
        strategySelect.onchange = async () => {
            syncChannelMultVisibility(strategySelect.value);
            await applyBestParametersIfAvailable(strategySelect.value, tickerSelect.value);
            ensureIntradayResolutionForExtendedWindow();
            updateDashboard();
            if (activeTab === 'advanced' && advChart) updateAdvDashboard();
        };
        if (tradingWindowSelect) {
            tradingWindowSelect.onchange = async () => {
                ensureIntradayResolutionForExtendedWindow();
                try {
                    const selectedWindow = encodeURIComponent(getActiveTradingWindow());
                    const response = await fetch(`/api/trading-window?trading_window=${selectedWindow}`, { method: 'POST' });
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                } catch (err) {
                    console.warn('[TV] Could not persist trading window:', err);
                }
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
                checkMarketAndRefresh();
            };
        }
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
        if (slopedAnchorBarsSelect) {
            slopedAnchorBarsSelect.onchange = () => {
                updateDashboard();
                if (activeTab === 'advanced' && advChart) updateAdvDashboard();
            };
        }
        syncChannelMultVisibility(strategySelect.value);
        filtersLoaded = true;
        ensureIntradayResolutionForExtendedWindow();

        // Trigger initial data load with best parameters if combination exists
        if (data.symbols && data.symbols.length > 0) {
            await applyBestParametersIfAvailable(strategySelect.value, tickerSelect.value);
            ensureIntradayResolutionForExtendedWindow();
            await updateDashboard();
        }

    } catch (err) {
        console.error('[TV] loadFilters failed:', err);
        tickerSelect.innerHTML = '<option value="">Error loading data</option>';
    }
}

// ============================================================
// Yahoo Finance auto-refresh during the configured market session
// ============================================================
function formatMarketTime(isoValue) {
    if (!isoValue) return '';
    const value = new Date(isoValue);
    if (Number.isNaN(value.getTime())) return '';
    return value.toLocaleString([], {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        timeZoneName: 'short',
    });
}

function renderMarketStatus(status, failed = false) {
    if (!marketRefreshStatus) return;
    const text = marketRefreshStatus.querySelector('.market-status-text');
    marketRefreshStatus.classList.toggle('open', Boolean(status?.is_open));
    marketRefreshStatus.classList.toggle('error', failed);
    if (failed) {
        if (text) text.textContent = 'Yahoo refresh status unavailable';
        return;
    }
    if (status.is_open) {
        const last = lastDataRefreshAt
            ? ` · updated ${new Date(lastDataRefreshAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
            : '';
        if (text) text.textContent = `${status.active_trading_window} active · Yahoo every ${status.refresh_minutes} min${last}`;
    } else {
        const next = formatMarketTime(status.next_refresh_at);
        if (text) text.textContent = next ? `Market closed · resumes ${next}` : 'Market closed';
    }
    marketRefreshStatus.title = `${status.market} · ${status.timezone}`;
}

async function checkMarketAndRefresh() {
    try {
        const tradingWindow = getActiveTradingWindow();
        const response = await fetch(`/api/market-status?trading_window=${encodeURIComponent(tradingWindow)}`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const status = await response.json();
        renderMarketStatus(status);

        const refreshMs = Number(status.refresh_minutes) * 60 * 1000;
        const refreshDue = !lastDataRefreshAt || Date.now() - lastDataRefreshAt >= refreshMs;
        if (!status.is_open || !refreshDue || autoRefreshInFlight) return;

        autoRefreshInFlight = true;
        try {
            if (activeTab === 'advanced' && advChart) {
                await updateAdvDashboard();
            } else {
                await updateDashboard();
            }
            renderMarketStatus(status);
        } finally {
            autoRefreshInFlight = false;
        }
    } catch (err) {
        console.warn('[TV] Market refresh check failed:', err);
        renderMarketStatus(null, true);
    }
}

function startMarketRefresh() {
    if (marketStatusTimer) clearInterval(marketStatusTimer);
    checkMarketAndRefresh();
    marketStatusTimer = setInterval(checkMarketAndRefresh, 60 * 1000);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) checkMarketAndRefresh();
    });
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

function getSlopedEntryMarkerStyle(reason, isLong) {
    if (reason === 'breakout' || reason === 'support_break') {
        return {
            markerClass: 'sloped-line-signal',
            prefix: reason === 'support_break' ? 'LINE SUPPORT BREAK ' : 'LINE BREAKOUT ',
            color: isLong ? '#059669' : '#DC2626',
        };
    }
    if (reason === 'exit_peak_reclaim') {
        return { markerClass: 'sloped-reentry', prefix: 'PEAK RECLAIM ', color: '#6EE7B7' };
    }
    if (reason === 'barrier_trap_reentry') {
        return { markerClass: 'sloped-reentry', prefix: 'TRAP REENTRY ', color: '#22D3EE' };
    }
    return { markerClass: 'sloped-other-entry', prefix: 'OTHER SIGNAL ', color: '#A78BFA' };
}

function getSlopedExitMarkerStyle(reason, isLong, isWin) {
    if (reason === 'support_break' || reason === 'resistance_break') {
        return {
            markerClass: 'sloped-line-signal',
            prefix: reason === 'support_break' ? 'LINE SUPPORT BREAK ' : 'LINE RESISTANCE BREAK ',
            color: reason === 'support_break' ? '#DC2626' : '#059669',
        };
    }
    if (reason === 'entry_barrier_break') {
        return { markerClass: 'sloped-protection', prefix: 'ENTRY BARRIER ', color: '#F59E0B' };
    }
    if (reason === 'atr_stop_buffer') {
        return { markerClass: 'sloped-protection', prefix: 'ATR STOP ', color: '#F97316' };
    }
    if (reason === 'end_of_data') {
        return { markerClass: 'sloped-end-of-data', prefix: 'END OF DATA ', color: '#94A3B8' };
    }
    return {
        markerClass: 'sloped-other-exit',
        prefix: 'OTHER EXIT ',
        color: isWin ? '#A78BFA' : '#7C3AED',
    };
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
            const isSlopedTrade = (trade.strategy === 'sloped_lines') || (strategy === 'sloped_lines');
            const isExitPeakReclaim = trade.entry_reason === 'exit_peak_reclaim';
            const isBarrierTrapReentry = trade.entry_reason === 'barrier_trap_reentry';
            const isMidlineCross = (trade.entry_reason === 'midline_cross') || (trade.notes && trade.notes.includes('midline_cross'));
            const isMidlineReclaim = (trade.entry_reason === 'midline_reclaim') || (trade.notes && trade.notes.includes('midline_reclaim'));
            const isChannelReclaim = (trade.entry_reason === 'channel_reclaim') || (trade.notes && trade.notes.includes('channel_reclaim'));
            const isChannelInflection = (trade.entry_reason === 'channel_inflection') || (trade.notes && trade.notes.includes('channel_inflection'));
            const isStopEntry = isStopLossReason(trade.entry_reason) || isStopLossReason(trade.notes);
            const slopedStyle = isSlopedTrade ? getSlopedEntryMarkerStyle(trade.entry_reason, isLong) : null;
            const entryPrefix = slopedStyle?.prefix || (isExitPeakReclaim ? 'EXIT PEAK RECLAIM ' : (isBarrierTrapReentry ? 'BARRIER TRAP REENTRY ' : (isStopEntry ? 'STOP LOSS ' : (isMidlineCross ? 'MID CROSS ' : (isMidlineReclaim ? 'MID RECLAIM ' : (isChannelReclaim ? 'LOWER RECLAIM ' : (isChannelInflection ? 'CHANNEL CURL ' : '')))))));
            const entryColor = slopedStyle?.color || (isMidlineCross ? '#0EA5E9' : (isMidlineReclaim ? '#3B82F6' : (isChannelReclaim ? '#06B6D4' : (isChannelInflection ? '#FACC15' : (isLong ? '#10B981' : '#F59E0B')))));

            // 1. Entry Marker
            markers.push({
                time: snappedEntry,
                position: isLong ? 'belowBar' : 'aboveBar',
                color: entryColor,
                shape: isLong ? 'arrowUp' : 'arrowDown',
                markerClass: slopedStyle?.markerClass || 'default-entry',
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
                const isSlopedTrade = (trade.strategy === 'sloped_lines') || (strategy === 'sloped_lines');
                const isSupportBreak = (trade.exit_reason === 'support_break');
                const isResistanceBreak = (trade.exit_reason === 'resistance_break');
                const isStopExit = isStopLossReason(trade.exit_reason) || isStopLossReason(trade.notes);
                const isMidlineCrossExit = (trade.exit_reason === 'midline_cross_exit') || (trade.notes && trade.notes.includes('midline_cross_exit'));
                const isMidStop = (trade.exit_reason === 'midline_stop_exit') || (trade.notes && trade.notes.includes('midline_stop'));
                const isChannelCurlExit = (trade.exit_reason === 'channel_curl_exit') || (trade.notes && trade.notes.includes('channel_curl_exit')) || (trade.exit_reason === 'channel_curl_sell');
                const slopedStyle = isSlopedTrade ? getSlopedExitMarkerStyle(trade.exit_reason, isLong, isWin) : null;
                const exitPrefix = slopedStyle?.prefix || (isSupportBreak ? 'SUPPORT BREAK ' : (isResistanceBreak ? 'RESISTANCE BREAK ' : (isChannelCurlExit ? 'CHANNEL CURL ' : (isMidlineCrossExit ? 'MID CROSS ' : (isMidStop ? 'MID STOP ' : (isStopExit ? 'STOP LOSS ' : ''))))));
                const action = isLong ? 'SELL' : 'COVER';
                const exitColor = slopedStyle?.color || (isSupportBreak ? '#3B82F6' : (isChannelCurlExit ? '#EC4899' : ((isMidStop || isStopExit) ? '#F43F5E' : (isWin ? '#10B981' : '#EF4444'))));

                markers.push({
                    time: snappedExit,
                    position: isLong ? 'aboveBar' : 'belowBar',
                    color: exitColor,
                    shape: isLong ? 'arrowDown' : 'arrowUp',
                    markerClass: slopedStyle?.markerClass || 'default-exit',
                    text: `${stratPrefix}${exitPrefix}${action} $${Number(trade.exit_price).toFixed(2)} (${pnlSign}${pnlPct.toFixed(1)}%)`
                });
            }
        }
    });

    // Consolidate markers sharing exact same candle time & position
    const consolidatedMap = new Map();
    markers.forEach(m => {
        const key = `${m.time}_${m.position}_${m.markerClass}`;
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

    const finalMarkers = Array.from(consolidatedMap.values()).map(({ markerClass, ...marker }) => marker);

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
async function fetchAndRenderTrendlines(symbol, chartInstance, candleData, existingSeriesList, strategy = 'enhanced_lines', fullCandle = true, timeframe = '1d', period = '1y', useWick = false, confirmCandles = 0, inverseColorTrigger = false, lineAngle = 0, stopLossMode = 'none', minAnchorBars = 2, isCurrent = () => true) {
    // Counts let the UI smoke test verify that returned trendlines were actually drawn.
    const summary = { returned: 0, drawn: 0 };
    try {
        const fullCandleParam = (strategy === 'sloped_lines' || strategy === 'slope_lines') ? `&full_candle=${fullCandle}&use_wick=${useWick}&confirm_candles=${confirmCandles}&inverse_color_trigger=${inverseColorTrigger}&line_angle=${lineAngle}&stop_loss_mode=${encodeURIComponent(stopLossMode)}&min_anchor_bars=${minAnchorBars}` : '';
        const tradingWindow = encodeURIComponent(getActiveTradingWindow());
        const res = await fetch(`/api/trendlines?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&timeframe=${encodeURIComponent(timeframe)}&period=${encodeURIComponent(period)}&trading_window=${tradingWindow}${fullCandleParam}`);
        if (!res.ok) return summary;
        const data = await res.json();
        if (!isCurrent()) return summary;
        existingSeriesList.forEach(s => {
            try { chartInstance.removeSeries(s); } catch (_) {}
        });
        existingSeriesList.length = 0;
        if (!data.trendlines || data.trendlines.length === 0) return summary;
        summary.returned = data.trendlines.length;

        if (candleData.length === 0) return summary;
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

            const addTrendlineSeries = (dataPoints, style, width, title) => {
                if (dataPoints.length < 2 || dataPoints[1].time <= dataPoints[0].time) return false;
                const seriesOptions = {
                    color,
                    lineWidth: width,
                    lineStyle: style,
                    crosshairMarkerVisible: false,
                    lastValueVisible: false,
                    priceLineVisible: false,
                    title,
                };
                let lineSeries;
                if (typeof chartInstance.addLineSeries === 'function') {
                    lineSeries = chartInstance.addLineSeries(seriesOptions);
                } else if (typeof chartInstance.addSeries === 'function' && typeof LightweightCharts.LineSeries !== 'undefined') {
                    lineSeries = chartInstance.addSeries(LightweightCharts.LineSeries, seriesOptions);
                }
                if (!lineSeries) return false;
                lineSeries.setData(dataPoints);
                existingSeriesList.push(lineSeries);
                return true;
            };

            const confirmationTime = tl.confirmation_time ? findNearestCandleTime(tl.confirmation_time, candleData) : null;
            if (
                strategy === 'sloped_lines'
                && confirmationTime != null
                && confirmationTime > snappedStart
                && confirmationTime < snappedEnd
            ) {
                const forming = addTrendlineSeries([
                    { time: snappedStart, value: tl.start_price },
                    { time: confirmationTime, value: tl.confirmation_price },
                ], 2, 1, `${tl.label || ''} (forming)`);
                const active = addTrendlineSeries([
                    { time: confirmationTime, value: tl.confirmation_price },
                    { time: snappedEnd, value: tl.end_price },
                ], 0, 2, `${tl.label || ''} (active)`);
                if (forming || active) summary.drawn += 1;
            } else if (addTrendlineSeries([
                { time: snappedStart, value: tl.start_price },
                { time: snappedEnd, value: tl.end_price },
            ], lineStyle, 2, tl.label || '')) {
                summary.drawn += 1;
            }
        });
    } catch (err) {
        console.warn('[TV] Trendline fetch error:', err);
    }
    return summary;
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
            <div class="channel-pill">Dashed = forming · Solid = active</div>
            <div class="channel-pill"><span style="color: #059669;">▲</span> Line breakout buy</div>
            <div class="channel-pill"><span style="color: #6EE7B7;">▲</span> Reclaim / re-entry buy</div>
            <div class="channel-pill"><span style="color: #DC2626;">▼</span> Line support-break sell</div>
            <div class="channel-pill"><span style="color: #F59E0B;">▼</span> Protection / other sell</div>
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

async function fetchAndRenderChannels(symbol, chartInstance, candleData, existingSeriesList, timeframe = '1d', period = '5y', isCurrent = () => true) {
    try {
        const mult = getSelectedChannelMult();
        const lb = getSelectedChannelLookback();
        const tradingWindow = encodeURIComponent(getActiveTradingWindow());
        const res = await fetch(`/api/channels?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&period=${encodeURIComponent(period)}&trading_window=${tradingWindow}&channel_mult=${mult}&lookback=${lb}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!isCurrent()) return;
        existingSeriesList.forEach(s => {
            try { chartInstance.removeSeries(s); } catch (_) {}
        });
        existingSeriesList.length = 0;
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
    const requestGeneration = ++dashboardRequestGeneration;
    const isCurrentRequest = () => requestGeneration === dashboardRequestGeneration;

    setLoading(true, 'loading');

    try {
        const reqResolution = activeResolution || '1d';
        const reqPeriod = activeTimeframe || '1y';
        const strategyWindow = getActiveTradingWindow();
        const strategyWindowParam = `&trading_window=${encodeURIComponent(strategyWindow)}`;

        const slopedParam = (strategy === 'sloped_lines' || strategy === 'slope_lines')
            ? `&full_candle=${getFullCandleEnabled()}&use_wick=${getWickEnabled()}&confirm_candles=${getConfirmCandles()}&inverse_color_trigger=${getInverseColorTriggerEnabled()}&line_angle=${getLineAngle()}&stop_loss_mode=${encodeURIComponent(getStopLossMode())}&min_anchor_bars=${getMinAnchorBars()}`
            : '';
        const multParam = (strategy === 'enhanced_channel')
            ? `&channel_mult=${getSelectedChannelMult()}&lookback=${getSelectedChannelLookback()}&use_stop_loss=${getChannelStoplossEnabled()}&midline_reentry=${getChannelMidlineEnabled()}&midline_cross=${getChannelMidlineEnabled()}&lower_reclaim=${getChannelLowerReclaimEnabled()}&channel_curl_mode=${encodeURIComponent(getChannelCurlMode())}&channel_inflection=${getChannelCurlEnabled()}`
            : slopedParam;

        const [candlesRes, tradesRes, statsRes] = await Promise.all([
            fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(reqResolution)}&period=${encodeURIComponent(reqPeriod)}${strategyWindowParam}`),
            fetch(`/api/trades?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&timeframe=${encodeURIComponent(reqResolution)}&period=${encodeURIComponent(reqPeriod)}${strategyWindowParam}${multParam}`),
            fetch(`/api/stats?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&timeframe=${encodeURIComponent(reqResolution)}&period=${encodeURIComponent(reqPeriod)}${strategyWindowParam}${multParam}`)
        ]);

        const candlesData = candlesRes.ok ? await candlesRes.json() : { candles: [] };
        const tradesData = tradesRes.ok ? await tradesRes.json() : { trades: [] };
        const statsData = statsRes.ok ? await statsRes.json() : {};
        if (!isCurrentRequest()) return;

        // Update range hint if actual period was clamped by Yahoo Finance (e.g. 30m max 60d)
        if (candlesData.period && candlesData.period !== reqPeriod) {
            const hintEl = document.getElementById('active-range-hint');
            if (hintEl) hintEl.textContent = `${reqPeriod.toUpperCase()} (${candlesData.period} Max Intraday)`;
        }

        // -- Candles --
        const rawCandles = filterCandlesForVisibleSessions(candlesData.candles || []);
        const sorted = rawCandles
            .filter(c => c && typeof c.time === 'number' && !isNaN(c.open) && !isNaN(c.high) && !isNaN(c.low) && !isNaN(c.close))
            .sort((a, b) => a.time - b.time)
            .filter((c, i, arr) => i === 0 || c.time !== arr[i - 1].time); // deduplicate

        currentCandles = sorted;

        chartDataUpdateInProgress = true;
        try {
            // Drop old overlays before swapping candles: removing them afterwards shifts the shared
            // time scale under the new candles and the library throws "Value is null" (BUG-001).
            if (chart) {
                trendlineSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
                trendlineSeries.length = 0;
                channelSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
                channelSeries.length = 0;
            }
            if (candlestickSeries) {
                candlestickSeries.setData(sorted);
            }
            renderAdvancedIndicators(sorted);
        } finally {
            chartDataUpdateInProgress = false;
        }

        // -- Trade Markers --
        const overlays = { markerCount: 0, trendlinesReturned: 0, trendlinesDrawn: 0 };
        if (candlestickSeries && tradesData.trades && sorted.length > 0) {
            try {
                const finalMarkers = buildMarkers(tradesData, sorted, strategy);
                if (typeof candlestickSeries.setMarkers === 'function') {
                    candlestickSeries.setMarkers(finalMarkers);
                    overlays.markerCount = finalMarkers.length;
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
            const trendlineSummary = await fetchAndRenderTrendlines(symbol, chart, sorted, trendlineSeries, strategy, getFullCandleEnabled(), reqResolution, reqPeriod, getWickEnabled(), getConfirmCandles(), getInverseColorTriggerEnabled(), getLineAngle(), getStopLossMode(), getMinAnchorBars(), isCurrentRequest);
            overlays.trendlinesReturned = trendlineSummary.returned;
            overlays.trendlinesDrawn = trendlineSummary.drawn;
        } else if (chart && strategy === 'enhanced_channel' && sorted.length > 0) {
            trendlineSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            trendlineSeries.length = 0;
            updateChannelLegend('channel-legend', true, strategy);
            await fetchAndRenderChannels(symbol, chart, sorted, channelSeries, reqResolution, reqPeriod, isCurrentRequest);
        } else {
            updateChannelLegend('channel-legend', false);
            trendlineSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            trendlineSeries.length = 0;
            channelSeries.forEach(s => { try { chart.removeSeries(s); } catch (_) {} });
            channelSeries.length = 0;
        }

        if (!isCurrentRequest()) return;

        if (chart) {
            const viewport = applyInitialChartViewport(chart, sorted, tradesData, reqResolution, reqPeriod);
            recordChartRenderState(sorted, tradesData, reqResolution, reqPeriod, viewport, strategy, symbol, overlays);
            requestAnimationFrame(() => {
                syncIndicatorRanges();
                scheduleSessionZoneRender();
                refreshMainChartLayout();
                setTimeout(scheduleSessionZoneRender, 250);
            });
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
        lastDataRefreshAt = Date.now();

    } catch (err) {
        if (isCurrentRequest()) console.error('[TV] updateDashboard failed:', err);
    } finally {
        if (isCurrentRequest()) setLoading(false, 'loading');
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
        const windowParam = `&trading_window=${encodeURIComponent(getActiveTradingWindow())}`;
        const slopedAdvParam = (strategy === 'sloped_lines' || strategy === 'slope_lines')
            ? `&full_candle=${getFullCandleEnabled()}&use_wick=${getWickEnabled()}&confirm_candles=${getConfirmCandles()}&inverse_color_trigger=${getInverseColorTriggerEnabled()}&line_angle=${getLineAngle()}&stop_loss_mode=${encodeURIComponent(getStopLossMode())}&min_anchor_bars=${getMinAnchorBars()}`
            : '';
        const multParam = (strategy === 'enhanced_channel')
            ? `&channel_mult=${getSelectedChannelMult()}&lookback=${getSelectedChannelLookback()}&use_stop_loss=${getChannelStoplossEnabled()}&midline_reentry=${getChannelMidlineEnabled()}&midline_cross=${getChannelMidlineEnabled()}&lower_reclaim=${getChannelLowerReclaimEnabled()}&channel_curl_mode=${encodeURIComponent(getChannelCurlMode())}&channel_inflection=${getChannelCurlEnabled()}`
            : slopedAdvParam;
        const [candlesRes, tradesRes, statsRes] = await Promise.all([
            fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(config.interval)}&period=${encodeURIComponent(config.period)}${windowParam}`),
            fetch(`/api/trades?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&timeframe=${encodeURIComponent(config.interval)}&period=${encodeURIComponent(config.period)}${windowParam}${multParam}`),
            fetch(`/api/stats?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&timeframe=${encodeURIComponent(config.interval)}&period=${encodeURIComponent(config.period)}${windowParam}${multParam}`)
        ]);

        const candlesData = candlesRes.ok ? await candlesRes.json() : { candles: [] };
        const tradesData = tradesRes.ok ? await tradesRes.json() : { trades: [] };
        const statsData = statsRes.ok ? await statsRes.json() : {};

        const rawCandles = filterCandlesForVisibleSessions(candlesData.candles || []);
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
            await fetchAndRenderTrendlines(symbol, advChart, sorted, advTrendlineSeries, strategy, getFullCandleEnabled(), config.interval, config.period, getWickEnabled(), getConfirmCandles(), getInverseColorTriggerEnabled(), getLineAngle(), getStopLossMode(), getMinAnchorBars());
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
        lastDataRefreshAt = Date.now();

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
            loadFilters().finally(startMarketRefresh);
            return;
        }
        initChart();
    } catch (err) {
        console.error('[TV] Chart initialization failed:', err);
    }
    initTabs();
    initTimeframeButtons();
    volumeIndicatorCheckbox?.addEventListener('change', updateIndicatorVisibility);
    rsiIndicatorCheckbox?.addEventListener('change', updateIndicatorVisibility);
    const savedActiveTab = localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
    if (savedActiveTab === 'advanced') switchTab('advanced');
    loadFilters().finally(startMarketRefresh);
})();
