"""Offline checks for accounting, signals, validation, and broker safeguards."""
from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tradingview_mcp.core.services import backtest_service as bt
from tradingview_mcp.core.services import signal_service as signals
from tradingview_mcp.core.services.execution_service import AlpacaAdapter, BitgetAdapter


def candles(count=300, descending=False):
    out = []
    for i in range(count):
        base = 400 - i if descending else 100 + i
        out.append({
            "date": str(date(2020, 1, 1) + timedelta(days=i)),
            "open": base,
            "high": base + 1,
            "low": base - 2,
            "close": base + 1,
            "volume": 1000,
        })
    return out


class BacktestRegressions(unittest.TestCase):
    def test_donchian_can_enter_and_exit(self):
        series = candles(70)
        down = candles(40, descending=True)
        for i, bar in enumerate(down):
            bar["date"] = str(date(2020, 1, 1) + timedelta(days=70 + i))
            bar.update(open=120 - i, high=121 - i, low=118 - i, close=121 - i)
        trades = bt._run_donchian(series + down)
        self.assertGreaterEqual(len(trades), 1)
        self.assertLess(trades[0]["entry_date"], trades[0]["exit_date"])

    def test_share_exposure_changes_account_by_dollars_traded(self):
        trade = {
            "entry_date": "2020-01-01", "exit_date": "2020-01-10",
            "entry_price": 100, "exit_price": 110, "return_pct": 10,
            "shares": 1, "side": "long",
        }
        self.assertEqual(bt._calc_metrics([trade], 10_000)["final_capital"], 10_010)
        self.assertEqual(bt._build_trade_log([trade], 10_000)[0]["pnl_usd"], 10)
        self.assertEqual(bt._build_equity_curve([trade], 10_000)[-1]["equity"], 10_010)

    def test_fractional_size_is_reflected_in_account_return(self):
        trade = {
            "entry_date": "2020-01-01", "exit_date": "2020-01-10",
            "entry_price": 100, "exit_price": 120, "return_pct": 20,
            "size_pct": 0.25,
        }
        self.assertEqual(bt._calc_metrics([trade], 10_000)["total_return_pct"], 5)

    def test_walk_forward_no_trades_has_no_robust_verdict(self):
        with patch.object(bt, "_fetch_ohlcv", return_value=candles()):
            result = bt.walk_forward_backtest("TEST", "rsi")
        self.assertEqual(result["oos_total_trades"], 0)
        self.assertIsNone(result["robustness_score"])
        self.assertTrue(result["verdict"].startswith("INSUFFICIENT EVIDENCE"))

    def test_live_entry_and_synthetic_exit(self):
        flat = candles(60)
        for bar in flat:
            bar.update(open=100, high=101, low=99, close=100)
        flat[-1].update(open=100, high=100, low=49, close=50)
        with patch.object(signals, "_fetch_ohlcv", return_value=flat):
            self.assertEqual(signals.get_live_signal("TEST", "rsi")["signal"], "long")
        with patch.object(signals, "_fetch_ohlcv", return_value=candles()):
            self.assertEqual(signals.get_live_signal("TEST", "buy_and_protect")["signal"], "none")

    def test_incomplete_daily_and_hourly_bars_are_excluded(self):
        daily = [{"date": "2026-09-18"}, {"date": "2026-09-21"}]
        morning = datetime(2026, 9, 21, 14, 3, tzinfo=timezone.utc)
        evening = datetime(2026, 9, 21, 21, 0, tzinfo=timezone.utc)
        self.assertEqual(len(bt._completed_candles(daily, "AAPL", "1d", morning)), 1)
        self.assertEqual(len(bt._completed_candles(daily, "AAPL", "1d", evening)), 2)
        self.assertEqual(len(bt._completed_candles(daily, "BTC-USD", "1d", evening)), 1)
        hourly = [{"date": "2026-09-21 13:00"}, {"date": "2026-09-21 14:00"}]
        self.assertEqual(len(bt._completed_candles(hourly, "AAPL", "1h", morning)), 1)

    def test_enhanced_channel_does_not_pretend_short_history_is_macro_history(self):
        from importlib.util import module_from_spec, spec_from_file_location
        path = Path(__file__).resolve().parents[1] / "strategies/enhanced_channel/enhanced_channel_strategy.py"
        spec = spec_from_file_location("enhanced_channel_for_test", path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        values = [float(i) for i in range(300)]
        line = module.calc_linear_regression_channel(values, 200)[0]
        self.assertTrue(all(value is None for value in line[:199]))
        self.assertIsNotNone(line[199])
        self.assertEqual(line[:250], module.calc_linear_regression_channel(values[:250], 200)[0])

    def test_enhanced_channel_research_entry_mask_is_optional(self):
        import json
        snapshot = Path(__file__).resolve().parents[1] / "docs/returns_baseline_completed_2026-09-18.json"
        series = json.loads(snapshot.read_text())["data"]["GOOGL"]["candles"]
        runner = bt._STRATEGY_MAP["enhanced_channel"]
        baseline = runner(series)
        self.assertTrue(baseline)
        self.assertEqual(baseline, runner(series, long_entry_mask=[True] * len(series)))
        self.assertEqual([], runner(series, long_entry_mask=[False] * len(series)))
        with self.assertRaisesRegex(ValueError, "one value per candle"):
            runner(series, long_entry_mask=[True])

    def test_enhanced_channel_backtest_accepts_shared_candles(self):
        import json
        from importlib.util import module_from_spec, spec_from_file_location
        snapshot = Path(__file__).resolve().parents[1] / "docs/returns_baseline_completed_2026-09-18.json"
        series = json.loads(snapshot.read_text())["data"]["AAPL"]["candles"]
        path = Path(__file__).resolve().parents[1] / "strategies/enhanced_channel/enhanced_channel_strategy.py"
        spec = spec_from_file_location("enhanced_channel_shared_candles_test", path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, "fetch_ohlcv", side_effect=AssertionError("must use supplied candles")):
            result = module.run_backtest("AAPL", period="1y", interval="1d",
                                         channel_curl_mode="none", candles=series)
        self.assertEqual(result["candles_analyzed"], len(series))
        self.assertEqual(result["parameters"]["channel_curl_mode"], "none")


class BrokerRegressions(unittest.TestCase):
    def test_bitget_rejects_unlinked_protection_before_entry(self):
        adapter = object.__new__(BitgetAdapter)

        class Exchange:
            def create_order(self, **kwargs):
                raise AssertionError("An order must not be submitted")

        adapter._exchange = Exchange()
        with self.assertRaisesRegex(ValueError, "linked OCO"):
            adapter.place_market_order("BTC/USDT", "buy", 0.1, stop_loss=50)

    def test_alpaca_one_leg_uses_oto_and_two_use_bracket(self):
        adapter = object.__new__(AlpacaAdapter)

        class Order:
            id = "test"
            status = "filled"
            filled_avg_price = "100.00"
            filled_qty = "1"
            symbol = "AAPL"
            side = "buy"

        class API:
            def __init__(self):
                self.params = []

            def submit_order(self, **kwargs):
                self.params.append(kwargs)
                return Order()

            def get_order(self, order_id):
                return Order()

        adapter._api = API()
        adapter.place_market_order("AAPL", "buy", 1, stop_loss=90)
        adapter.place_market_order("AAPL", "buy", 1, stop_loss=90, take_profit=110)
        self.assertEqual([p["order_class"] for p in adapter._api.params], ["oto", "bracket"])


if __name__ == "__main__":
    unittest.main()
