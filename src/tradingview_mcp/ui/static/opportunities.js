const watchlistInput = document.getElementById('watchlist');
const scanButton = document.getElementById('scan');
const statusText = document.getElementById('status');
const activeSummary = document.getElementById('active-summary');
const activeTable = document.getElementById('active-table');
const allTable = document.getElementById('all-table');

function cell(row, value, className = '') {
  const td = document.createElement('td');
  td.textContent = value == null ? '—' : String(value);
  if (className) td.className = className;
  row.appendChild(td);
}

function pct(value) {
  return value == null ? '—' : `${Number(value).toFixed(1)}%`;
}

function renderRows(table, rows, activeOnly = false) {
  const body = table.querySelector('tbody');
  body.replaceChildren();
  for (const item of rows) {
    const tr = document.createElement('tr');
    cell(tr, item.symbol);
    cell(tr, item.strategy_label || item.strategy);
    if (activeOnly) {
      cell(tr, item.signal_date);
      cell(tr, item.signal_context
        ? `Price +${pct(item.signal_context.price_gain_pct)} · volume ${Number(item.signal_context.volume_ratio).toFixed(1)}×`
        : '—');
      cell(tr, item.closed_trades
        ? `${pct(item.observed_win_rate_pct)} (${item.profitable_trades}/${item.closed_trades})`
        : 'No closed longs');
      const bounds = item.observed_win_rate_95pct_interval;
      cell(tr, bounds ? `${pct(bounds[0])}–${pct(bounds[1])}` : '—');
      cell(tr, pct(item.average_net_trade_return_pct));
      cell(tr, item.evidence_status === 'limited_history' ? 'Limited history' : 'Historical only');
    } else {
      cell(tr, item.signal === 'buy' ? 'BUY signal' : item.signal, item.signal === 'buy' ? 'buy' : 'muted');
      cell(tr, item.closed_trades);
      cell(tr, pct(item.observed_win_rate_pct));
      cell(tr, pct(item.average_net_trade_return_pct));
      cell(tr, pct(item.worst_trade_pct));
    }
    body.appendChild(tr);
  }
  table.hidden = rows.length === 0;
}

async function scan() {
  scanButton.disabled = true;
  statusText.textContent = 'Checking completed candles and strategy signals…';
  try {
    const params = new URLSearchParams({ symbols: watchlistInput.value });
    const response = await fetch(`/api/opportunities?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Scan failed');
    renderRows(activeTable, data.active_buy_signals, true);
    renderRows(allTable, data.rows);
    activeSummary.textContent = data.active_buy_signals.length
      ? `${data.active_buy_signals.length} current buy signal(s). None has a calibrated gain probability yet.`
      : 'No current buy signals among the supported strategies on the latest completed bars.';
    const dates = Object.entries(data.as_of_completed_bar).map(([symbol, date]) => `${symbol}: ${date}`).join(' · ');
    const errors = data.errors.map(e => `${e.symbol}: ${e.error}`).join(' · ');
    statusText.textContent = `Checked ${data.watchlist.length} stocks and ${data.strategies_scanned.length} strategies. Completed bars: ${dates}.${errors ? ` Errors: ${errors}` : ''}`;
    statusText.className = '';
  } catch (error) {
    statusText.textContent = `Scan failed: ${error.message}`;
    statusText.className = 'bad';
  } finally {
    scanButton.disabled = false;
  }
}

scanButton.addEventListener('click', scan);
watchlistInput.addEventListener('keydown', event => { if (event.key === 'Enter') scan(); });
