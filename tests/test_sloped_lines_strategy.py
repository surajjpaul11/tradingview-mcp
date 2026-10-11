import asyncio
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

STRATEGY_DIR = Path(__file__).resolve().parents[1] / "strategies" / "sloped_lines"
if str(STRATEGY_DIR) not in sys.path:
    sys.path.insert(0, str(STRATEGY_DIR))

from sloped_lines_strategy import (
    _entry_barrier_exit_reason,
    _validation_boundary,
    build_ascending_support,
    build_descending_resistance,
    build_staggered_resistance,
    build_staggered_support,
    is_body_gap_down,
    is_body_gap_up,
    recovery_reentry_signals,
    recovery_reentry_triggered,
    run_sloped_lines,
)
from tradingview_mcp.ui import server


def descending_waves_then_breakout(bars=160, breakout_bar=120):
    """Daily candles whose swing highs fall along a line, then break above it."""
    candles = []
    for i in range(bars):
        if i < breakout_bar:
            mid = 150 - i * 0.35 + 8 * math.sin(i * 2 * math.pi / 20)
        else:
            mid = 150 - breakout_bar * 0.35 + (i - breakout_bar) * 1.5
        candles.append({
            "time": 1_700_000_000 + i * 86_400,
            "date": f"2023-11-14+{i}",
            "open": mid - 0.5,
            "high": mid + 0.8,
            "low": mid - 0.8,
            "close": mid + 0.5,
            "volume": 1_000,
        })
    return candles


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

    def test_resistance_cannot_resurrect_after_post_anchor_crossing(self):
        candles = [
            {"open": 110, "high": 111, "low": 109, "close": 110},
            {"open": 104, "high": 105, "low": 103, "close": 104},
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 96, "high": 97, "low": 94, "close": 96},
            {"open": 89, "high": 90, "low": 88, "close": 89},
        ]

        line = build_descending_resistance(
            [(0, 110, 0), (2, 100, 4)],
            [110, 104, 100, 96, 89],
            current_bar=4,
            tolerance=0,
            min_anchor_bars=2,
            candles=candles,
            line_angle=0,
            use_wick=False,
        )

        self.assertIsNone(line)

    def test_post_anchor_touch_ignores_formation_tolerance(self):
        candles = [
            {"open": 110, "high": 111, "low": 109, "close": 110},
            {"open": 104, "high": 105, "low": 103, "close": 104},
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 95, "high": 96, "low": 94, "close": 95},
            {"open": 89, "high": 90, "low": 88, "close": 89},
        ]

        line = build_descending_resistance(
            [(0, 110, 0), (2, 100, 4)],
            [110, 104, 100, 95, 89],
            current_bar=4,
            tolerance=0.015,
            min_anchor_bars=2,
            candles=candles,
            line_angle=0,
            use_wick=False,
        )

        self.assertIsNone(line)

    def test_support_cannot_resurrect_after_post_anchor_crossing(self):
        candles = [
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 106, "high": 107, "low": 105, "close": 106},
            {"open": 110, "high": 111, "low": 109, "close": 110},
            {"open": 114, "high": 116, "low": 114, "close": 114},
            {"open": 121, "high": 122, "low": 120, "close": 121},
        ]

        line = build_ascending_support(
            [(0, 100, 0), (2, 110, 4)],
            [100, 106, 110, 114, 121],
            current_bar=4,
            tolerance=0,
            min_anchor_bars=2,
            candles=candles,
            line_angle=0,
            use_wick=False,
        )

        self.assertIsNone(line)

    def test_line_uses_actual_swing_confirmation_bar(self):
        candles = [
            {"open": 110, "high": 111, "low": 109, "close": 110},
            {"open": 104, "high": 105, "low": 103, "close": 104},
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 94, "high": 95, "low": 93, "close": 94},
            {"open": 89, "high": 90, "low": 88, "close": 89},
        ]

        line = build_descending_resistance(
            [(0, 110, 0), (2, 100, 4)],
            [110, 104, 100, 94, 89],
            current_bar=4,
            tolerance=0,
            min_anchor_bars=2,
            candles=candles,
            line_angle=0,
            use_wick=False,
        )

        self.assertIsNotNone(line)
        self.assertEqual(line["anchor2"], (2, 100.0))
        self.assertEqual(line["confirmed_at_bar"], 4)


class StaggeredLineTests(unittest.TestCase):
    @staticmethod
    def candles(values):
        return [
            {"open": value, "high": value + 0.5, "low": value - 0.5, "close": value}
            for value in values
        ]

    def test_support_promotes_two_later_confirmed_higher_lows(self):
        candles = self.candles([100, 101, 102, 108, 110, 112, 114, 118])
        active = {
            "type": "support", "direction": "ascending",
            "anchor1": (0, 100), "anchor2": (2, 102), "level": 1,
        }

        promoted = build_staggered_support(
            active, [(4, 110, 5), (6, 114, 7)], [c["close"] for c in candles],
            current_bar=7, tolerance=0, min_anchor_bars=2, candles=candles,
            line_angle=0, validation_boundary="body",
        )

        self.assertIsNotNone(promoted)
        self.assertEqual(promoted["anchor1"], (4, 110.0))
        self.assertEqual(promoted["anchor2"], (6, 114.0))
        self.assertEqual(promoted["confirmed_at_bar"], 7)
        self.assertEqual(promoted["level"], 2)

    def test_resistance_reuses_latest_touch_and_next_confirmed_local_high(self):
        candles = self.candles([110, 109, 108, 105, 100, 95, 89])
        active = {
            "type": "resistance", "direction": "descending",
            "anchor1": (0, 110), "anchor2": (3, 105), "level": 1,
        }

        promoted = build_staggered_resistance(
            active, [(5, 95, 6)], [c["close"] for c in candles],
            current_bar=6, tolerance=0, min_anchor_bars=2, candles=candles,
            line_angle=0, validation_boundary="body",
        )

        self.assertIsNotNone(promoted)
        self.assertEqual(promoted["anchor1"], (3, 105.0))
        self.assertEqual(promoted["anchor2"], (5, 95.0))
        self.assertEqual(promoted["confirmed_at_bar"], 6)
        self.assertEqual(promoted["level"], 2)

    def test_does_not_promote_without_a_later_confirmed_extremum(self):
        active = {"type": "support", "anchor1": (0, 100), "anchor2": (2, 102), "level": 1}
        candles = self.candles([100, 101, 102, 108])
        self.assertIsNone(build_staggered_support(
            active, [], [c["close"] for c in candles], current_bar=3, candles=candles, line_angle=0
        ))


class BodyGapSignalTests(unittest.TestCase):
    @staticmethod
    def candle(date, open_price, close_price):
        return {
            "time": 1_700_000_000,
            "date": date,
            "open": open_price,
            "high": max(open_price, close_price) + 0.5,
            "low": min(open_price, close_price) - 0.5,
            "close": close_price,
            "volume": 1_000,
        }

    def test_gap_rules_require_consecutive_colors_and_strict_body_separation(self):
        green1 = self.candle("g1", 100, 102)
        green2 = self.candle("g2", 103, 105)
        touching_green = self.candle("g3", 105, 106)
        red1 = self.candle("r1", 104, 103)
        red2 = self.candle("r2", 102, 100)

        self.assertTrue(is_body_gap_up(green1, green2))
        self.assertFalse(is_body_gap_up(green2, touching_green))
        self.assertTrue(is_body_gap_down(red1, red2))
        self.assertFalse(is_body_gap_up(red1, green2))
        self.assertFalse(is_body_gap_down(green1, red2))

    def test_enabled_gap_up_buys_and_gap_down_sells_on_second_completed_candle(self):
        candles = [
            self.candle("2026-07-30", 100, 102),
            self.candle("2026-07-31", 103, 105),
            self.candle("2026-08-03", 104, 103),
            self.candle("2026-08-04", 102, 100),
        ]

        trades, _ = run_sloped_lines(
            candles,
            pivot_lookback=2,
            line_angle=0,
            stop_loss_mode="none",
            gap_up=True,
            gap_down=True,
        )

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["entry_date"], "2026-07-31")
        self.assertEqual(trades[0]["entry_price"], 105)
        self.assertEqual(trades[0]["entry_reason"], "gap_up")
        self.assertEqual(trades[0]["exit_date"], "2026-08-04")
        self.assertEqual(trades[0]["exit_price"], 100)
        self.assertEqual(trades[0]["exit_reason"], "gap_down")


class RecoveryReentryTests(unittest.TestCase):
    def test_any_and_all_apply_only_to_enabled_signals(self):
        enabled = {"rsi": True, "ema": True, "price": False, "volume": False}
        matched = {"rsi": True, "ema": False, "price": True, "volume": True}

        self.assertTrue(recovery_reentry_triggered(enabled, matched, "any"))
        self.assertFalse(recovery_reentry_triggered(enabled, matched, "all"))
        self.assertFalse(recovery_reentry_triggered({name: False for name in enabled}, matched, "any"))

    def test_completed_candle_signal_enters_at_next_open(self):
        candles = []
        for i in range(20):
            candles.append({
                "time": 1_700_000_000 + i * 86_400,
                "date": f"base-{i:02d}",
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.0,
                "volume": 1_000,
            })

        def add(date, open_price, close_price):
            i = len(candles)
            candles.append({
                "time": 1_700_000_000 + i * 86_400,
                "date": date,
                "open": open_price,
                "high": max(open_price, close_price) + 0.5,
                "low": min(open_price, close_price) - 0.5,
                "close": close_price,
                "volume": 1_000,
            })

        add("entry-setup", 100, 101)
        add("gap-entry", 102, 103)
        add("exit-setup", 106, 104)
        add("gap-exit", 101, 99)
        add("recovery-signal", 104, 105)
        add("recovery-fill", 106, 107)
        add("end", 107, 108)

        trades, _ = run_sloped_lines(
            candles,
            pivot_lookback=2,
            line_angle=100,
            stop_loss_mode="none",
            gap_up=True,
            gap_down=True,
            reentry_mode="any",
            reentry_ema=True,
        )

        recovery_trade = next(t for t in trades if t.get("entry_reason") == "recovery_reentry")
        self.assertEqual(recovery_trade["signal_date"], "recovery-signal")
        self.assertEqual(recovery_trade["entry_date"], "recovery-fill")
        self.assertEqual(recovery_trade["entry_price"], 106)
        self.assertEqual(recovery_trade["entry_signals"], ["close_above_ema20"])

    def test_signal_values_cover_rsi_ema_price_and_volume(self):
        candles = [
            {"high": 100, "close": 99, "volume": 100}
            for _ in range(20)
        ] + [{"high": 112, "close": 111, "volume": 130}]
        closes = [float(c["close"]) for c in candles]
        rsi_values = [None] * 19 + [49.0, 51.0]
        ema_values = [None] * 20 + [105.0]

        self.assertEqual(recovery_reentry_signals(candles, closes, rsi_values, ema_values, 20), {
            "rsi_cross_50": True,
            "close_above_ema20": True,
            "close_above_5_bar_high": True,
            "volume_above_1_2x_average20": True,
        })


class TrendlineApiTests(unittest.TestCase):
    def fetch(self, candles):
        with patch.object(server, "fetch_market_candles", return_value=(candles, "1d", "1y")):
            return asyncio.run(server.api_trendlines(symbol="TEST", strategy="sloped_lines"))

    def test_api_returns_drawable_resistance_line(self):
        candles = descending_waves_then_breakout()

        data = self.fetch(candles)

        self.assertNotIn("error", data)
        self.assertGreater(len(data["trendlines"]), 0)
        line = data["trendlines"][0]
        self.assertEqual(line["type"], "resistance")
        self.assertEqual(line["level"], 1)
        self.assertIn("Resistance L1", line["label"])
        # Fields the dashboard needs to draw the line on the chart.
        times = {c["time"] for c in candles}
        self.assertIn(line["start_time"], times)
        self.assertIn(line["anchor2_time"], times)
        self.assertIn(line["confirmation_time"], times)
        self.assertIn(line["end_time"], times)
        self.assertLess(line["start_time"], line["end_time"])
        self.assertGreater(line["start_price"], line["end_price"])
        self.assertIsNotNone(line["break_date"])
        self.assertGreater(len(line["points"]), 2)
        self.assertEqual(line["points"][0]["time"], line["start_time"])
        self.assertEqual(line["points"][-1]["time"], line["end_time"])

    def test_api_reports_missing_candles_instead_of_lines(self):
        data = self.fetch([])

        self.assertEqual(data["trendlines"], [])
        self.assertIn("error", data)

    def test_explicit_validation_boundary_selects_body_close_or_wick(self):
        candles = [{"open": 100, "high": 110, "low": 90, "close": 105}]
        closes = [105]

        self.assertEqual(_validation_boundary(candles, closes, 0, "resistance", False, "body"), 105)
        self.assertEqual(_validation_boundary(candles, closes, 0, "resistance", False, "close"), 105)
        self.assertEqual(_validation_boundary(candles, closes, 0, "resistance", False, "wick"), 110)
        self.assertEqual(_validation_boundary(candles, closes, 0, "support", False, "body"), 100)
        self.assertEqual(_validation_boundary(candles, closes, 0, "support", False, "wick"), 90)

    def test_api_forwards_selected_tuning_parameters(self):
        candles = descending_waves_then_breakout()
        with patch.object(server, "fetch_market_candles", return_value=(candles, "1d", "1y")):
            with patch("sloped_lines_strategy.run_sloped_lines_with_trendlines", return_value={"trendlines": []}) as run:
                asyncio.run(server.api_trendlines(
                    symbol="TEST",
                    strategy="sloped_lines",
                    pivot_lookback=2,
                    anchor_source="any_valid_candle",
                    validation_boundary="close",
                    trendline_tolerance=0.015,
                    gap_up=True,
                    gap_down=True,
                    staggered_lines=True,
                    reentry_mode="all",
                    reentry_rsi=True,
                    reentry_ema=True,
                    reentry_price_breakout=True,
                    reentry_volume=True,
                ))

        self.assertEqual(run.call_args.kwargs["pivot_lookback"], 2)
        self.assertEqual(run.call_args.kwargs["anchor_source"], "any_valid_candle")
        self.assertEqual(run.call_args.kwargs["validation_boundary"], "close")
        self.assertEqual(run.call_args.kwargs["trendline_tolerance"], 0.015)
        self.assertTrue(run.call_args.kwargs["gap_up"])
        self.assertTrue(run.call_args.kwargs["gap_down"])
        self.assertTrue(run.call_args.kwargs["staggered_lines"])
        self.assertEqual(run.call_args.kwargs["reentry_mode"], "all")
        self.assertTrue(run.call_args.kwargs["reentry_rsi"])
        self.assertTrue(run.call_args.kwargs["reentry_ema"])
        self.assertTrue(run.call_args.kwargs["reentry_price_breakout"])
        self.assertTrue(run.call_args.kwargs["reentry_volume"])

    def test_api_rejects_unsupported_tuning_parameters(self):
        with self.assertRaisesRegex(ValueError, "pivot_lookback must be one of"):
            server._resolve_sloped_params("TEST", pivot_lookback=9)
        with self.assertRaisesRegex(ValueError, "anchor_source must be one of"):
            server._resolve_sloped_params("TEST", anchor_source="future_candles")
        with self.assertRaisesRegex(ValueError, "validation_boundary must be one of"):
            server._resolve_sloped_params("TEST", validation_boundary="average")
        with self.assertRaisesRegex(ValueError, "trendline_tolerance must be one of"):
            server._resolve_sloped_params("TEST", trendline_tolerance=0.007)


if __name__ == "__main__":
    unittest.main()
