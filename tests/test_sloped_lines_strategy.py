import sys
import json
import math
import random
import unittest
from unittest.mock import patch

from pathlib import Path

STRATEGY_DIR = Path(__file__).resolve().parents[1] / "strategies" / "sloped_lines"
if str(STRATEGY_DIR) not in sys.path:
    sys.path.insert(0, str(STRATEGY_DIR))

import sloped_lines_strategy as strategy

from sloped_lines_strategy import (
    _entry_barrier_exit_reason,
    build_ascending_support,
    build_descending_resistance,
)


class StrictTrendlineValidationTests(unittest.TestCase):
    def test_pre_line_protection_exit_is_not_labeled_as_a_slope_break(self):
        self.assertEqual(_entry_barrier_exit_reason("exit_peak_reclaim"), "entry_barrier_break")
        self.assertEqual(_entry_barrier_exit_reason("barrier_trap_reentry"), "entry_barrier_break")
        self.assertEqual(_entry_barrier_exit_reason("atr_stop_buffer"), "atr_stop_buffer")

    def test_resistance_rejects_candle_body_crossing(self):
        candles = [
            {"open": 110, "high": 111, "low": 109, "close": 110},
            {"open": 106, "high": 108, "low": 103, "close": 104},
            {"open": 100, "high": 101, "low": 99, "close": 100},
        ]

        line = build_descending_resistance(
            [(0, 110), (2, 100)],
            [110, 104, 100],
            current_bar=2,
            tolerance=0,
            min_anchor_bars=2,
            candles=candles,
            line_angle=0,
            use_wick=False,
        )

        self.assertIsNone(line)

    def test_support_rejects_candle_body_crossing(self):
        candles = [
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 104, "high": 107, "low": 103, "close": 106},
            {"open": 110, "high": 111, "low": 109, "close": 110},
        ]

        line = build_ascending_support(
            [(0, 100), (2, 110)],
            [100, 106, 110],
            current_bar=2,
            tolerance=0,
            min_anchor_bars=2,
            candles=candles,
            line_angle=0,
            use_wick=False,
        )

        self.assertIsNone(line)

    def test_wick_setting_controls_wick_cross_validation(self):
        candles = [
            {"open": 110, "high": 111, "low": 109, "close": 110},
            {"open": 104, "high": 108, "low": 103, "close": 104},
            {"open": 100, "high": 101, "low": 99, "close": 100},
        ]
        kwargs = {
            "confirmed_highs": [(0, 110), (2, 100)],
            "closes": [110, 104, 100],
            "current_bar": 2,
            "tolerance": 0,
            "min_anchor_bars": 2,
            "candles": candles,
            "line_angle": 0,
        }

        body_line = build_descending_resistance(**kwargs, use_wick=False)
        wick_line = build_descending_resistance(**kwargs, use_wick=True)

        self.assertIsNotNone(body_line)
        self.assertIsNone(wick_line)


class ExecutionTimingTests(unittest.TestCase):
    """Controlled lines isolate execution timing from pivot selection."""

    def candles(self):
        prices = [
            (104, 105, 103, 104), (100, 101, 99, 100),
            (97, 100, 96, 99), (110, 114, 109, 112),
            (113, 115, 111, 114), (116, 118, 115, 117),
        ]
        return [dict(date=f"2026-01-{i + 1:02d}", open=o, high=h, low=l,
                     close=c, volume=1000)
                for i, (o, h, l, c) in enumerate(prices)]

    def run_strategy(self, candles=None, support=None, second_resistance=None, **kwargs):
        def resistance(*args, current_bar, **options):
            if current_bar == 1:
                return dict(type="resistance", direction="descending",
                            anchor1=(0, 102), anchor2=(1, 100), confirmed_at_bar=1)
            if second_resistance is not None and current_bar == 5:
                return second_resistance
            return None

        def ascending(*args, current_bar, **options):
            return support if current_bar == 3 else None

        with patch.object(strategy, "build_descending_resistance", side_effect=resistance), \
             patch.object(strategy, "build_ascending_support", side_effect=ascending):
            return strategy.run_sloped_lines(
                candles if candles is not None else self.candles(),
                line_angle=3, stop_loss_mode=kwargs.pop("stop_loss_mode", "none"), **kwargs)

    def test_body_signal_waits_for_next_open_including_gap(self):
        trades, lines = self.run_strategy()
        self.assertEqual(trades[0]["entry_signal_date"], "2026-01-03")
        self.assertEqual(trades[0]["entry_date"], "2026-01-04")
        self.assertEqual(trades[0]["entry_price"], 110)
        self.assertEqual(lines[0]["break_bar"], 2)
        self.assertEqual(lines[0]["fill_bar"], 3)
        self.assertEqual(lines[0]["break_price"], 110)

    def test_close_and_color_filters_delay_wick_signals(self):
        for options in ({"full_candle": True}, {"inverse_color_trigger": True}):
            with self.subTest(options=options):
                trades, _ = self.run_strategy(use_wick=True, **options)
                self.assertEqual(trades[0]["entry_date"], "2026-01-04")
                self.assertEqual(trades[0]["entry_price"], 110)

    def test_additional_confirmation_uses_open_after_confirmation(self):
        trades, _ = self.run_strategy(use_wick=True, confirm_candles=1)
        self.assertEqual(trades[0]["entry_signal_date"], "2026-01-04")
        self.assertEqual(trades[0]["entry_date"], "2026-01-05")
        self.assertEqual(trades[0]["entry_price"], 113)

    def test_unfiltered_wick_touch_keeps_intraday_fill(self):
        trades, _ = self.run_strategy(use_wick=True)
        self.assertEqual(trades[0]["entry_date"], "2026-01-03")
        self.assertEqual(trades[0]["entry_price"], 98)

    def test_unfiltered_wick_gap_fills_at_open(self):
        candles = self.candles()
        candles[2].update(open=101, high=104, low=100, close=102)
        trades, _ = self.run_strategy(candles, use_wick=True)
        self.assertEqual(trades[0]["entry_price"], 101)

    def test_final_bar_signal_does_not_invent_entry(self):
        for options, length in (({}, 3), ({"use_wick": True, "confirm_candles": 1}, 4)):
            with self.subTest(options=options):
                trades, lines = self.run_strategy(self.candles()[:length], **options)
                self.assertEqual(trades, [])
                self.assertIsNone(lines[0]["fill_date"])
                self.assertIsNone(lines[0]["break_price"])

    def test_fill_does_not_depend_on_fill_candle_close(self):
        for close in (109, 112, 130):
            with self.subTest(close=close):
                candles = self.candles()[:4]
                candles[3].update(close=close, high=max(114, close))
                trades, _ = self.run_strategy(candles)
                self.assertEqual(trades[0]["entry_price"], 110)
                self.assertEqual(trades[0]["entry_date"], "2026-01-04")

    def test_failed_confirmation_does_not_buy(self):
        candles = self.candles()[:4]
        candles[3].update(open=99, close=97, high=100, low=96)
        trades, _ = self.run_strategy(candles, use_wick=True, confirm_candles=1)
        self.assertEqual(trades, [])

    def support_line(self):
        return dict(type="support", direction="ascending", anchor1=(1, 90),
                    anchor2=(3, 100), confirmed_at_bar=3)

    def test_support_exit_and_short_reversal_wait_for_next_open(self):
        candles = self.candles()
        candles[4].update(open=103, high=104, low=99, close=101)
        candles[5].update(open=80, high=82, low=79, close=81)
        trades, lines = self.run_strategy(candles, support=self.support_line(), enable_short=True)
        self.assertEqual(trades[0]["exit_signal_date"], "2026-01-05")
        self.assertEqual(trades[0]["exit_date"], "2026-01-06")
        self.assertEqual(trades[0]["exit_price"], 80)
        self.assertEqual(trades[0]["exit_reason"], "support_break")
        self.assertEqual(trades[1]["side"], "short")
        self.assertEqual(trades[1]["entry_price"], 80)
        self.assertEqual(lines[1]["fill_bar"], 5)

    def test_short_cover_and_long_reversal_use_same_next_open(self):
        candles = self.candles()
        candles[4].update(open=103, high=104, low=99, close=101)
        candles[5].update(open=80, high=82, low=79, close=81)
        candles.extend([
            dict(date="2026-01-07", open=84, high=87, low=83, close=86, volume=1000),
            dict(date="2026-01-08", open=95, high=97, low=94, close=96, volume=1000),
        ])
        resistance = dict(type="resistance", direction="descending", anchor1=(3, 90),
                          anchor2=(5, 85), confirmed_at_bar=5)
        trades, _ = self.run_strategy(candles, support=self.support_line(),
                                     second_resistance=resistance, enable_short=True)
        self.assertEqual(trades[1]["exit_reason"], "resistance_break")
        self.assertEqual(trades[1]["exit_price"], 95)
        self.assertEqual(trades[1]["exit_date"], "2026-01-08")
        self.assertEqual(trades[2]["side"], "long")
        self.assertEqual(trades[2]["entry_price"], 95)

    def test_final_bar_exit_signal_remains_end_of_data_mark(self):
        candles = self.candles()[:5]
        candles[4].update(open=103, high=104, low=99, close=101)
        trades, lines = self.run_strategy(candles, support=self.support_line())
        self.assertEqual(trades[0]["exit_reason"], "end_of_data")
        self.assertEqual(trades[0]["exit_price"], 101)
        self.assertIsNone(lines[1]["fill_date"])

    def test_green_support_break_does_not_sell_with_color_filter(self):
        candles = self.candles()
        candles[4].update(open=101, high=104, low=99, close=103)
        trades, _ = self.run_strategy(candles, support=self.support_line(), inverse_color_trigger=True)
        self.assertEqual(trades[0]["exit_reason"], "end_of_data")

    def test_reentries_wait_for_next_open(self):
        for mode in ("exit_peak_reclaim", "barrier_trap_reentry"):
            with self.subTest(mode=mode):
                candles = self.candles()
                candles[4].update(open=103, high=104, low=99, close=101)
                candles[5].update(open=100, high=109, low=99, close=108)
                candles.extend([
                    dict(date="2026-01-07", open=112, high=116, low=111, close=115, volume=1000),
                    dict(date="2026-01-08", open=120, high=123, low=119, close=122, volume=1000),
                ])
                trades, _ = self.run_strategy(candles, support=self.support_line(), stop_loss_mode=mode)
                self.assertEqual(trades[1]["entry_reason"], mode)
                self.assertEqual(trades[1]["entry_signal_date"], "2026-01-07")
                self.assertEqual(trades[1]["entry_date"], "2026-01-08")
                self.assertEqual(trades[1]["entry_price"], 120)

    def test_body_entry_barrier_exit_waits_for_next_open(self):
        candles = self.candles()
        candles[4].update(open=95, high=96, low=90, close=91)
        candles[5].update(open=85, high=87, low=84, close=86)
        trades, _ = self.run_strategy(candles)
        self.assertEqual(trades[0]["exit_reason"], "entry_barrier_break")
        self.assertEqual(trades[0]["exit_signal_date"], "2026-01-05")
        self.assertEqual(trades[0]["exit_date"], "2026-01-06")
        self.assertEqual(trades[0]["exit_price"], 85)


    def test_next_open_entry_can_trigger_protection_on_fill_candle(self):
        candles = self.candles()
        candles[3].update(low=90, close=91)
        candles[4].update(open=80, high=82, low=79, close=81)
        trades, _ = self.run_strategy(candles)
        self.assertEqual(trades[0]["entry_date"], "2026-01-04")
        self.assertEqual(trades[0]["exit_signal_date"], "2026-01-04")
        self.assertEqual(trades[0]["exit_date"], "2026-01-05")
        self.assertEqual(trades[0]["exit_price"], 80)
        self.assertEqual(trades[0]["exit_reason"], "entry_barrier_break")

    def test_current_bar_atr_stop_waits_for_next_open_even_in_wick_mode(self):
        candles = self.candles()
        candles[3].update(open=99, high=100, low=95, close=99)
        candles[4].update(open=90, high=92, low=89, close=91)
        with patch.object(strategy, "calc_atr", return_value=[0.5] * len(candles)):
            trades, _ = self.run_strategy(candles, use_wick=True, stop_loss_mode="atr_stop_buffer")
        self.assertEqual(trades[0]["exit_signal_date"], "2026-01-04")
        self.assertEqual(trades[0]["exit_date"], "2026-01-05")
        self.assertEqual(trades[0]["exit_price"], 90)
        self.assertEqual(trades[0]["exit_reason"], "atr_stop_buffer")

    def test_configured_strategies_fill_at_open_after_signal_with_real_pivots(self):
        rng = random.Random(42)
        candles = []
        price = 100.0
        for i in range(600):
            opening = price * math.exp(rng.gauss(0, 0.005))
            price = opening * math.exp(rng.gauss(0.0003, 0.02))
            candles.append(dict(date=str(i), open=opening, close=price,
                                high=max(opening, price) * 1.005,
                                low=min(opening, price) * 0.995, volume=1000))
        config = json.loads((STRATEGY_DIR.parent / "best_parameters.json").read_text())
        for symbol, settings in config["strategies"]["sloped_lines"]["tickers"].items():
            with self.subTest(symbol=symbol):
                trades, _ = strategy.run_sloped_lines(candles, **settings["parameters"])
                self.assertTrue(trades)
                for trade in trades:
                    signal = int(trade["entry_signal_date"])
                    self.assertEqual(int(trade["entry_date"]), signal + 1)
                    self.assertEqual(trade["entry_price"], candles[signal + 1]["open"])
                    if trade["exit_reason"] != "end_of_data":
                        signal = int(trade["exit_signal_date"])
                        self.assertEqual(int(trade["exit_date"]), signal + 1)
                        self.assertEqual(trade["exit_price"], candles[signal + 1]["open"])

    def test_backtest_and_overlay_serializers_keep_signal_and_fill_dates(self):
        trades_and_lines = self.run_strategy()
        with patch.object(strategy, "run_sloped_lines", return_value=trades_and_lines):
            result = strategy.run_backtest("TEST", candles=self.candles())
            overlays = strategy.run_sloped_lines_with_trendlines(self.candles())
        self.assertEqual(result["trade_log"][0]["entry_price"], 110)
        self.assertEqual(result["trade_log"][0]["entry_signal_date"], "2026-01-03")
        self.assertEqual(result["trendlines"][0]["break_date"], "2026-01-03")
        self.assertEqual(result["trendlines"][0]["fill_date"], "2026-01-04")
        self.assertEqual(overlays["trendlines"][0]["fill_date"], "2026-01-04")


if __name__ == "__main__":
    unittest.main()
