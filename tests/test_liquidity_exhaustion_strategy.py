"""
Unit tests for Liquidity & Capitulation Exhaustion Strategy.
"""
import unittest
from strategies.liquidity_exhaustion.liquidity_exhaustion_strategy import (
    calc_sma,
    calc_ema,
    calc_atr,
    align_multi_asset_data,
    run_liquidity_exhaustion,
    apply_costs,
    calc_metrics,
)


class TestLiquidityExhaustion(unittest.TestCase):

    def test_calc_sma(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        sma = calc_sma(values, 3)
        self.assertIsNone(sma[0])
        self.assertIsNone(sma[1])
        self.assertEqual(sma[2], 20.0)
        self.assertEqual(sma[3], 30.0)
        self.assertEqual(sma[4], 40.0)

    def test_calc_ema(self):
        values = [10.0, 10.0, 10.0, 20.0]
        ema = calc_ema(values, 3)
        self.assertIsNone(ema[0])
        self.assertIsNone(ema[1])
        self.assertEqual(ema[2], 10.0)
        self.assertGreater(ema[3], 10.0)

    def test_align_multi_asset_data_forward_fill(self):
        primary = [
            {"date": "2026-01-01", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 1000},
            {"date": "2026-01-02", "open": 102, "high": 106, "low": 101, "close": 105, "volume": 1200},
            {"date": "2026-01-03", "open": 105, "high": 107, "low": 104, "close": 106, "volume": 1100},
        ]
        # Aux ticker missing 2026-01-02
        aux = {
            "^VIX": [
                {"date": "2026-01-01", "close": 20.0},
                {"date": "2026-01-03", "close": 25.0},
            ]
        }
        aligned = align_multi_asset_data(primary, aux)
        self.assertEqual(len(aligned), 3)
        self.assertEqual(aligned[0]["^VIX"], 20.0)
        self.assertEqual(aligned[1]["^VIX"], 20.0)  # Forward-filled
        self.assertEqual(aligned[2]["^VIX"], 25.0)

    def test_apply_costs_and_metrics(self):
        trades = [
            {
                "entry_price": 100.0,
                "exit_price": 110.0,
                "side": "long",
                "entry_date": "2026-01-01",
                "exit_date": "2026-01-10",
                "entry_reason": "capitulation_bottom",
                "exit_reason": "trailing_stop",
            },
            {
                "entry_price": 100.0,
                "exit_price": 95.0,
                "side": "long",
                "entry_date": "2026-01-15",
                "exit_date": "2026-01-20",
                "entry_reason": "capitulation_bottom",
                "exit_reason": "stop_loss",
            },
        ]
        adjusted = apply_costs(trades, commission_pct=0.1, slippage_pct=0.05)
        self.assertEqual(len(adjusted), 2)
        self.assertAlmostEqual(adjusted[0]["return_pct"], 9.7, places=1)
        self.assertAlmostEqual(adjusted[1]["return_pct"], -5.3, places=1)

        metrics = calc_metrics(adjusted, initial_capital=10000.0)
        self.assertEqual(metrics["total_trades"], 2)
        self.assertEqual(metrics["winning_trades"], 1)
        self.assertEqual(metrics["losing_trades"], 1)
        self.assertEqual(metrics["win_rate_pct"], 50.0)
        self.assertGreater(metrics["final_capital"], 10000.0)


if __name__ == "__main__":
    unittest.main()
