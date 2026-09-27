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
    build_ascending_support,
    build_descending_resistance,
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

    def test_api_forwards_selected_pivot_lookback(self):
        candles = descending_waves_then_breakout()
        with patch.object(server, "fetch_market_candles", return_value=(candles, "1d", "1y")):
            with patch("sloped_lines_strategy.run_sloped_lines_with_trendlines", return_value={"trendlines": []}) as run:
                asyncio.run(server.api_trendlines(
                    symbol="TEST",
                    strategy="sloped_lines",
                    pivot_lookback=2,
                ))

        self.assertEqual(run.call_args.kwargs["pivot_lookback"], 2)

    def test_api_rejects_unsupported_pivot_lookback(self):
        with self.assertRaisesRegex(ValueError, "pivot_lookback must be one of"):
            server._resolve_sloped_params("TEST", pivot_lookback=9)


if __name__ == "__main__":
    unittest.main()
