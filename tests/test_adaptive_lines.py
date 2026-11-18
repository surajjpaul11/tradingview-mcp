import asyncio
import math
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'strategies/sloped_lines'))
from sloped_lines_strategy import build_adaptive_line, run_sloped_lines, run_sloped_lines_with_trendlines, run_sloped_lines_trades
from tradingview_mcp.ui import server


def waves(count=300):
    # Fixed synthetic tape with both trends and noisy pullbacks.
    rng=random.Random(2)
    rows=[];price=100
    for i in range(count):
        price=max(20,price+.12+rng.gauss(0,1.5))
        rows.append(dict(time=1700000000+i*86400,date=f'bar-{i:04d}',open=price-.3,close=price+.3,high=price+1,low=price-1,volume=1000))
    return rows


class AdaptiveLineTests(unittest.TestCase):
    def setUp(self):
        self.closes=[92,94,94,97,101,104,105,109,111]
        self.active=dict(type='support',anchor1=(0,90),anchor2=(2,92),confirmed_at_bar=2)
        self.pivots=[(4,100,5),(6,104,7)]

    def build(self,**kwargs):
        args=dict(active_line=self.active,confirmed_pivots=self.pivots,closes=self.closes,current_bar=8,atr_value=2)
        args.update(kwargs)
        return build_adaptive_line(**args)

    def test_reuses_latest_anchor_and_selects_closest_valid_support(self):
        line=self.build()
        self.assertEqual(line['anchor1'],(2,92))
        self.assertEqual(line['anchor2'],(6,104))
        self.assertEqual(line['activated_at_bar'],8)
        self.assertEqual(line['effective_from_bar'],9)
        self.assertTrue(line['adaptive'])

    def test_mirrored_resistance_is_tightened_downward(self):
        line=self.build(active_line=dict(type='resistance',anchor1=(0,110),anchor2=(2,108)),
            confirmed_pivots=[(4,100,5),(6,96,7)],closes=[200-x for x in self.closes])
        self.assertEqual(line['anchor1'],(2,108))
        self.assertEqual(line['anchor2'],(6,96))

    def test_two_recent_pivots_can_replace_an_aged_anchor(self):
        line=self.build(lookback_bars=5)
        self.assertEqual(line['anchor1'],(4,100))
        self.assertEqual(line['anchor2'],(6,104))

    def test_future_pivots_and_pre_trade_swings_are_not_used(self):
        self.assertIsNone(self.build(confirmed_pivots=[(4,100,5),(6,104,9)]))
        self.assertIsNone(self.build(since_bar=7))

    def test_crossed_line_cannot_be_resurrected_and_margin_filters_noise(self):
        closes=list(self.closes);closes[7]=100
        self.assertIsNone(self.build(closes=closes))
        self.assertIsNone(self.build(min_improvement_atr=100))
        self.assertIsNone(self.build(atr_value=0))
        self.assertIsNone(self.build(line_angle=30))

    def test_disabled_mode_preserves_trades_and_line_geometry(self):
        rows=waves()
        p=dict(anchor_source='any_valid_candle',line_angle=0,line_breakout_buy=True,entry_barrier_sell=True)
        self.assertEqual(run_sloped_lines(rows,**p),run_sloped_lines(rows,adaptive_tightening=False,adaptive_pivot_bars=1,adaptive_min_improvement_atr=.5,**p))

    def test_prefix_replay_never_changes_already_closed_trades(self):
        rows=waves()
        p=dict(anchor_source='any_valid_candle',line_angle=0,line_breakout_buy=True,entry_barrier_sell=True,
               adaptive_tightening=True,adaptive_pivot_bars=2,adaptive_min_improvement_atr=.25)
        trades,lines=run_sloped_lines(rows,**p)
        self.assertTrue(any(line.get('adaptive') for line in lines))
        for length in (100,150,200,250):
            partial,_=run_sloped_lines(rows[:length],**p)
            dates={c['date'] for c in rows[:length]}
            expected=[t for t in trades if t['exit_date'] in dates and t['exit_reason']!='end_of_data']
            actual=[t for t in partial if t['exit_reason']!='end_of_data']
            self.assertEqual(actual,expected)
        for line in lines:
            if line.get('adaptive'):
                self.assertGreater(line['effective_from_bar'],line['activated_at_bar'])
                self.assertLessEqual(line['confirmed_at_bar'],line['activated_at_bar'])
                if line.get('break_bar') is not None:
                    self.assertGreaterEqual(line['break_bar'],line['effective_from_bar'])

    def test_mcp_compatibility_runner_forwards_adaptive_settings(self):
        rows=waves()
        params=dict(anchor_source='any_valid_candle',line_angle=0,line_breakout_buy=True,entry_barrier_sell=True,
            adaptive_tightening=True,adaptive_pivot_bars=1,adaptive_min_improvement_atr=.5)
        expected,_=run_sloped_lines(rows,**params)
        self.assertEqual(run_sloped_lines_trades(rows,**params),expected)

    def test_overlay_reports_activation_and_normalized_slope(self):
        result=run_sloped_lines_with_trendlines(waves(),anchor_source='any_valid_candle',line_angle=0,
            line_breakout_buy=True,entry_barrier_sell=True,adaptive_tightening=True)
        lines=[line for line in result['trendlines'] if line['adaptive']]
        self.assertTrue(lines)
        self.assertTrue(all(line['activation_date']==line['confirmation_date'] for line in lines))
        self.assertTrue(all('slope_pct_per_bar' in line for line in lines))

    def test_daily_drawdown_includes_an_unrealized_pullback_after_costs(self):
        from compare_adaptive_lines import daily_drawdown
        rows=[dict(date=f'2026-01-0{i+1}',close=close) for i,close in enumerate([100,120,90,110])]
        trades=[dict(entry_date='2026-01-01',exit_date='2026-01-04',entry_price=100,quantity=100,
            balance_before=10000,balance_after=10970,costs_usd=30,side='long')]
        self.assertEqual(daily_drawdown(rows,trades),25.06)

    def test_api_controls_default_off_and_validate_before_fetching(self):
        self.assertFalse(server._resolve_sloped_params('SPY')['adaptive_tightening'])
        params=server._resolve_sloped_params('SPY',adaptive_tightening=True,adaptive_pivot_bars=1,adaptive_min_improvement_atr=.5)
        self.assertTrue(params['adaptive_tightening']);self.assertEqual(params['adaptive_pivot_bars'],1)
        for kwargs in [dict(adaptive_pivot_bars=3),dict(adaptive_min_improvement_atr=-.1),dict(adaptive_min_improvement_atr=float('nan'))]:
            with patch.object(server,'fetch_backtest_candles') as fetch:
                with self.assertRaises(server.HTTPException) as error:
                    asyncio.run(server.api_stats(symbol='SPY',strategy='sloped_lines',**kwargs))
                self.assertEqual(error.exception.status_code,422)
                fetch.assert_not_called()
