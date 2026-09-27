import unittest
from tradingview_mcp.core.services.strategy_config import load_best_parameters, get_best_parameters


class TestStrategyConfig(unittest.TestCase):
    def test_load_config(self):
        config = load_best_parameters()
        self.assertIn("strategies", config)
        self.assertIn("sloped_lines", config["strategies"])

    def test_get_best_parameters_aapl(self):
        aapl_cfg = get_best_parameters("sloped_lines", "AAPL")
        self.assertIsNotNone(aapl_cfg)
        params = aapl_cfg["parameters"]
        self.assertEqual(params["full_candle"], False)
        self.assertEqual(params["use_wick"], False)
        self.assertEqual(params["confirm_candles"], 0)
        self.assertEqual(params["inverse_color_trigger"], False)
        self.assertEqual(params["line_angle"], 3.0)
        self.assertEqual(params["stop_loss_mode"], "exit_peak_reclaim")
        self.assertEqual(params["min_anchor_bars"], 2)

        perf = aapl_cfg["performance"]
        self.assertEqual(perf["total_pnl"], 4670.62)
        self.assertEqual(perf["total_pnl_pct"], 46.71)
        self.assertEqual(perf["buy_and_hold_pct"], 33.72)
        self.assertEqual(perf["beats_bnh_pct"], 12.99)
        self.assertEqual(perf["win_rate_pct"], 42.1)
        self.assertEqual(perf["total_trades"], 38)

    def test_get_best_parameters_nvda(self):
        nvda_cfg = get_best_parameters("sloped_lines", "NVDA")
        self.assertIsNotNone(nvda_cfg)
        params = nvda_cfg["parameters"]
        self.assertEqual(params["full_candle"], False)
        self.assertEqual(params["use_wick"], False)
        self.assertEqual(params["confirm_candles"], 0)
        self.assertEqual(params["inverse_color_trigger"], True)
        self.assertEqual(params["line_angle"], 3.0)
        self.assertEqual(params["stop_loss_mode"], "barrier_trap_reentry")
        self.assertEqual(params["min_anchor_bars"], 3)

        perf = nvda_cfg["performance"]
        self.assertEqual(perf["total_pnl_pct"], 55.77)
        self.assertEqual(perf["buy_and_hold_pct"], 27.74)
        self.assertEqual(perf["beats_bnh_pct"], 28.03)

    def test_get_best_parameters_amd(self):
        amd_cfg = get_best_parameters("sloped_lines", "AMD")
        self.assertIsNotNone(amd_cfg)
        params = amd_cfg["parameters"]
        self.assertEqual(params["confirm_candles"], 1)
        self.assertEqual(params["line_angle"], 0.0)
        self.assertEqual(params["stop_loss_mode"], "barrier_trap_reentry")
        self.assertEqual(params["min_anchor_bars"], 4)

        perf = amd_cfg["performance"]
        self.assertEqual(perf["total_pnl_pct"], 384.75)
        self.assertEqual(perf["buy_and_hold_pct"], 282.55)
        self.assertEqual(perf["beats_bnh_pct"], 102.20)

    def test_get_best_parameters_spy(self):
        spy_cfg = get_best_parameters("sloped_lines", "SPY")
        self.assertIsNotNone(spy_cfg)
        perf = spy_cfg["performance"]
        self.assertEqual(perf["total_pnl_pct"], 17.07)
        self.assertEqual(perf["buy_and_hold_pct"], 17.89)
        self.assertEqual(perf["beats_bnh_pct"], -0.82)


if __name__ == "__main__":
    unittest.main()
