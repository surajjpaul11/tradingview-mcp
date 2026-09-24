import sys
import unittest
from pathlib import Path

STRATEGY_DIR = Path(__file__).resolve().parents[1] / "strategies" / "sloped_lines"
if str(STRATEGY_DIR) not in sys.path:
    sys.path.insert(0, str(STRATEGY_DIR))

from sloped_lines_strategy import build_ascending_support, build_descending_resistance


class StrictTrendlineValidationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
