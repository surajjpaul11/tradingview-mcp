import asyncio
import unittest
from unittest.mock import patch

from tests.test_sloped_lines_strategy import descending_waves_then_breakout
from sloped_lines_strategy import run_sloped_lines, run_sloped_lines_trades, run_sloped_lines_with_trendlines, run_backtest
from tradingview_mcp.ui import server


class PeakReclaimFullCandleTests(unittest.TestCase):
    def candles(self, use_wick=True):
        bars = [(100, 101, 102, 99), (103, 105, 106, 102),
                (104, 103, 105, 102), (101, 99, 102, 98),
                (100, 101, 104, 99) if use_wick else (104, 100, 105, 99),
                (100, 104, 105, 99), (104, 105, 106, 103)]
        return [dict(date=f"day-{i}", time=1700000000 + i * 86400,
                     open=o, close=c, high=h, low=l, volume=1000)
                for i, (o, c, h, l) in enumerate(bars)]

    def test_peak_confirmation_and_fill_are_independent_of_general_full_candle(self):
        for use_wick in (False, True):
            for general_full in (False, True):
                for peak_full in (False, True):
                    with self.subTest(wick=use_wick, general=general_full, peak=peak_full):
                        trades, _ = run_sloped_lines(
                            self.candles(use_wick), gap_up=True, gap_down=True,
                            line_angle=100, use_wick=use_wick, full_candle=general_full,
                            peak_reclaim_full_candle=peak_full,
                        )
                        reclaim = next(t for t in trades if t.get("entry_reason") == "exit_peak_reclaim")
                        self.assertEqual(reclaim["entry_date"], "day-5" if peak_full else "day-4")
                        self.assertEqual(reclaim["entry_price"], 104 if peak_full or not use_wick else 102)

    def test_equal_close_is_not_a_reclaim(self):
        candles = self.candles()
        candles[5].update(open=100, close=102)
        candles[6].update(open=101, close=105)
        trades, _ = run_sloped_lines(candles, gap_up=True, gap_down=True, line_angle=100,
                                    use_wick=True, peak_reclaim_full_candle=True)
        reclaim = next(t for t in trades if t.get("entry_reason") == "exit_peak_reclaim")
        self.assertEqual(reclaim["entry_date"], "day-6")
        self.assertEqual(reclaim["entry_price"], 105)

    def test_wrappers_and_api_forward_the_independent_setting(self):
        candles = self.candles()
        for wrapper in (run_sloped_lines_trades, run_sloped_lines_with_trendlines, run_backtest):
            with self.subTest(wrapper=wrapper.__name__):
                with patch("sloped_lines_strategy.run_sloped_lines", return_value=([], [])) as engine:
                    wrapper(candles=candles, full_candle=False, peak_reclaim_full_candle=True)
                self.assertTrue(engine.call_args.kwargs["peak_reclaim_full_candle"])
        for endpoint in (server.api_trades, server.api_stats, server.api_trendlines):
            with self.subTest(endpoint=endpoint.__name__):
                target = "run_sloped_lines_with_trendlines" if endpoint == server.api_trendlines else "run_backtest"
                with patch.object(server, "fetch_market_candles", return_value=(candles, "1d", "1y")):
                    with patch(f"sloped_lines_strategy.{target}", return_value={}) as runner:
                        asyncio.run(endpoint(symbol="TEST", strategy="sloped_lines", full_candle=False,
                                             peak_reclaim_full_candle=True))
                self.assertTrue(runner.call_args.kwargs["peak_reclaim_full_candle"])
                self.assertFalse(runner.call_args.kwargs["full_candle"])

    def test_peak_setting_does_not_change_line_breakout_signals(self):
        candles = descending_waves_then_breakout()
        for general_full in (False, True):
            results = [run_sloped_lines(candles, line_breakout_buy=True, stop_loss_mode="none",
                                        full_candle=general_full, peak_reclaim_full_candle=peak)[0]
                       for peak in (False, True)]
            self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
