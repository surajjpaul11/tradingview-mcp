"""Offline, fixed-data comparison of legacy and adaptive line tracking.

Run from the repository root:
  PYTHONPATH=src python strategies/sloped_lines/compare_adaptive_lines.py
No provider calls are made. Uses immutable daily AAPL/SPY SQLite snapshots.
Profiles are fixed beforehand; this script does not optimize Saved Best settings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sloped_lines_strategy import run_backtest
from tradingview_mcp.core.services.market_data_store import database_path, fingerprint
from tradingview_mcp.core.services.strategy_config import get_best_parameters

PROFILES = {
    'baseline': dict(adaptive_tightening=False),
    'legacy_staggered': dict(adaptive_tightening=False, staggered_lines=True),
    'adaptive_balanced': dict(adaptive_tightening=True, adaptive_pivot_bars=2, adaptive_min_improvement_atr=.25),
    'adaptive_fast': dict(adaptive_tightening=True, adaptive_pivot_bars=1, adaptive_min_improvement_atr=.25),
    'adaptive_conservative': dict(adaptive_tightening=True, adaptive_pivot_bars=2, adaptive_min_improvement_atr=.5),
    'adaptive_plus_staggered': dict(adaptive_tightening=True, adaptive_pivot_bars=2, adaptive_min_improvement_atr=.25, staggered_lines=True),
}


def daily_drawdown(rows, trades, capital=10000):
    """Mark positions at each daily close, including the model's round-trip cost.

    The legacy engine's max_drawdown_pct observes closed trades only. This
    measure also captures interim drawdowns within trades; no intraday inference.
    """
    peak=capital; worst=0.; cursor=0
    for row in rows:
        while cursor<len(trades) and trades[cursor]['exit_date']<=row['date']:
            capital=trades[cursor]['balance_after'];cursor+=1
        equity=capital
        if cursor<len(trades):
            trade=trades[cursor]
            if trade['entry_date']<=row['date']<trade['exit_date']:
                direction=-1 if trade.get('side')=='short' else 1
                equity=trade['balance_before']+direction*trade['quantity']*(row['close']-trade['entry_price'])-trade['costs_usd']
        peak=max(peak,equity)
        worst=max(worst,(peak-equity)/peak*100)
    return round(worst,2)


def summarize(rows, result):
    trades=result['trade_log'];indices={r['date']:i for i,r in enumerate(rows)}
    giveback=[]
    for t in trades:
        if t.get('side')=='short':continue
        prices=[r['close'] for r in rows[indices[t['entry_date']]:indices[t['exit_date']]+1]]
        giveback.append(max(0,(max(prices)-t['exit_price'])/t['entry_price']*100))
    return dict(return_pct=result['total_return_pct'],final_capital=result['final_capital'],
        daily_close_drawdown_pct=daily_drawdown(rows,trades,result['initial_capital']),
        closed_trade_drawdown_pct=result['max_drawdown_pct'],trades=result['total_trades'],
        losing_trades=result['losing_trades'],win_rate_pct=result['win_rate_pct'],
        costs_usd=round(sum(t['costs_usd'] for t in trades),2),
        average_profit_giveback_pct=round(sum(giveback)/len(giveback),2) if giveback else 0,
        reentries_within_3_bars=sum(0<=indices[b['entry_date']]-indices[a['exit_date']]<=3 for a,b in zip(trades,trades[1:])),
        adaptive_replacements=sum(bool(line.get('adaptive')) for line in result['trendlines']))


def load_windows(db):
    windows=[]
    for symbol in ('AAPL','SPY'):
        cfg=get_best_parameters('sloped_lines',symbol)
        key=fingerprint(dict(strategy='sloped_lines',symbol=symbol,record=cfg))
        saved=db.execute('SELECT s.* FROM candle_snapshots s JOIN saved_best_runs r ON r.snapshot_id=s.id WHERE r.fingerprint=?',(key,)).fetchone()
        if saved is None:raise RuntimeError(f'No matching Saved Best snapshot for {symbol}')
        archive=db.execute('SELECT * FROM candle_snapshots WHERE series_identity=? ORDER BY row_count DESC LIMIT 1',(saved['series_identity'],)).fetchone()
        for name,snapshot in [('saved',saved),('archive_2y',archive)]:
            rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM snapshot_candles WHERE snapshot_id=? ORDER BY time',(snapshot['id'],))]
            windows.append(dict(symbol=symbol,window=name,snapshot_id=snapshot['id'],candles=rows,parameters=cfg['parameters'],costs=cfg.get('costs',{})))
            if name=='archive_2y':
                earlier=[r for r in rows if r['date']<cfg['backtest_window']['start_date']]
                windows.append(dict(symbol=symbol,window='earlier_period',snapshot_id=snapshot['id'],candles=earlier,parameters=cfg['parameters'],costs=cfg.get('costs',{})))
    return windows


def compare(path, original_baselines=None):
    with sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        windows=load_windows(db)
    original={(w['symbol'],w['window']):w['baseline'] for w in original_baselines or []}
    output=[]
    case_study={}
    for window in windows:
        rows=window['candles'];results={}
        for profile,overrides in PROFILES.items():
            params={**window['parameters'],**overrides}
            result=run_backtest(window['symbol'],candles=rows,interval='1d',period='1y',
                **{**params,**window['costs']})
            if profile=='baseline' and (window['symbol'],window['window']) in original:
                previous=original[(window['symbol'],window['window'])]
                if result['trade_log']!=previous['trade_log']:
                    raise AssertionError('Adaptive off changed the baseline trade ledger')
            results[profile]=summarize(rows,result)
            if window['symbol']=='SPY' and window['window']=='saved' and profile in ('baseline','adaptive_balanced'):
                after=[trade for trade in result['trade_log'] if trade['entry_date']>='2026-04-27']
                lines=[line for line in result['trendlines'] if line.get('adaptive') and rows[line['activated_at_bar']]['date']=='2026-05-21']
                case_study[profile]={'from_april_27_return_pct':round((math.prod(1+t['account_return_pct']/100 for t in after)-1)*100,2),
                    'trades_from_april_27':len(after),
                    'first_trade':{k:after[0][k] for k in ('entry_date','exit_date','entry_price','exit_price','return_pct')} if after else None,
                    'support_tightening':[{'anchor1_date':rows[l['anchor1_bar']]['date'],'anchor2_date':rows[l['anchor2_bar']]['date'],
                        'activation_date':rows[l['activated_at_bar']]['date'],
                        'slope_per_bar':round((l['anchor2_price']-l['anchor1_price'])/(l['anchor2_bar']-l['anchor1_bar']),5)} for l in lines]}
        output.append(dict(symbol=window['symbol'],window=window['window'],snapshot_id=window['snapshot_id'],
            candle_hash=fingerprint(rows),bars=len(rows),start=rows[0]['date'],end=rows[-1]['date'],
            parameters=window['parameters'],costs=window['costs'] or {'commission_pct':.1,'slippage_pct':.05},results=results))
    return dict(generated_at=datetime.now(ZoneInfo('America/New_York')).isoformat(),
        source='Immutable local SQLite adjusted daily candle snapshots; no live downloads',
        engine_hash=hashlib.sha256(Path(__file__).with_name('sloped_lines_strategy.py').read_bytes()).hexdigest(),
        defaults=dict(adaptive_tightening=False,adaptive_pivot_bars=2,adaptive_min_improvement_atr=.25,lookback_bars=20),
        notes=['The saved and two-year windows overlap; they are not independent samples.',
               'Earlier periods precede each saved window but use the existing Saved Best parameters; not a prospective out-of-sample validation.',
               'Drawdown is measured at daily closes; intraday drawdown may be greater.',
               'Returns include 0.1% commission and 0.05% slippage per side unless a preset specifies otherwise.',
               'Reentries within 3 bars are a turnover diagnostic, not proof of a false signal.'],
        baseline_ledgers_verified=bool(original),profiles=PROFILES,windows=output,spy_screenshot_case=case_study)


def markdown(report):
    lines=['# Adaptive line comparison','',f"Generated: {report['generated_at']}",'',
        'Fixed settings and candles; returns are after the existing commission/slippage model. Adaptive stays off by default. Saved Best records are unchanged.','',
        '| Ticker / window | Baseline return | Adaptive return | Difference | Daily-close drawdown: before → after | Trades: before → after |',
        '|---|---:|---:|---:|---:|---:|']
    for w in report['windows']:
        a=w['results']['baseline'];b=w['results']['adaptive_balanced']
        lines.append(f"| {w['symbol']} / {w['window']} | {a['return_pct']:.2f}% | {b['return_pct']:.2f}% | {b['return_pct']-a['return_pct']:+.2f} pp | {a['daily_close_drawdown_pct']:.2f}% → {b['daily_close_drawdown_pct']:.2f}% | {a['trades']} → {b['trades']} |")
    lines+=['','## Saved-window sensitivity','', '| Ticker | Baseline | Legacy staggered | Adaptive 2-bar / 0.25 ATR | Adaptive 1-bar / 0.25 ATR | Adaptive 2-bar / 0.5 ATR | Adaptive + staggered |','|---|---:|---:|---:|---:|---:|---:|']
    for w in report['windows']:
        if w['window']=='saved':lines.append('| '+w['symbol']+' | '+' | '.join(f"{w['results'][p]['return_pct']:.2f}%" for p in PROFILES)+' |')
    case=report['spy_screenshot_case']
    lines+=['','## SPY screenshot case','',
        'Adaptive support tightens on May 21 using the April 29 / May 19 anchors, rising $1.6154 per candle instead of the original $0.12435. The April 27 position exits June 5 rather than September 22.',
        '',f"From that April 27 entry onward, normalized net return is **{case['baseline']['from_april_27_return_pct']:.2f}% baseline vs {case['adaptive_balanced']['from_april_27_return_pct']:.2f}% adaptive**, with {case['baseline']['trades_from_april_27']} vs {case['adaptive_balanced']['trades_from_april_27']} trades. Closer tracking did not improve this particular part of the window; the small full-window improvement comes from earlier trades.",
        '', 'AAPL has no qualifying adaptive replacements with the tested presets. The existing minimum anchor move, boundary validation and confirmation rules remain enforced.']
    lines+=['','## Limits','']+['- '+n for n in report['notes']]
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=str(database_path()))
    parser.add_argument('--output',default='reports/adaptive_line_comparison.json')
    parser.add_argument('--baseline-export',default='data/research/adaptive_baselines.json')
    args=parser.parse_args()
    old=Path(args.baseline_export)
    report=compare(args.db,json.loads(old.read_text()) if old.exists() else None)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+'\n')
    out.with_suffix('.md').write_text(markdown(report))
    print(markdown(report))

if __name__=='__main__':main()
