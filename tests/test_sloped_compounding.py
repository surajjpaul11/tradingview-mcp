import asyncio
import math
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from tests.test_sloped_lines_strategy import descending_waves_then_breakout
from sloped_lines_strategy import apply_costs, size_trades, calc_metrics, run_backtest
from tradingview_mcp.ui import server


class CompoundingTests(unittest.TestCase):
    def trades(self, returns):
        return apply_costs([dict(entry_price=200, exit_price=200 * (1 + r / 100), side="long")
                            for r in returns], 0, 0)

    def test_reinvests_gains_and_reduces_exposure_after_losses(self):
        trades = size_trades(self.trades([10, -10, 0]), 1000)
        for trade, balance, quantity in zip(trades, [1000, 1100, 990], [5, 5.5, 4.95]):
            self.assertAlmostEqual(trade["balance_before"], balance)
            self.assertAlmostEqual(trade["position_value"], balance)
            self.assertAlmostEqual(trade["quantity"], quantity)
        self.assertAlmostEqual(trades[-1]["balance_after"], 990)

    def test_fixed_budget_does_not_reinvest_profit_or_borrow_after_loss(self):
        trades = size_trades(self.trades([10, -20, 10]), 1000, False)
        self.assertEqual([t["position_value"] for t in trades], [1000, 1000, 900])
        self.assertEqual([t["cash_at_entry"] for t in trades], [0, 100, 0])
        self.assertAlmostEqual(trades[-1]["balance_after"], 990)
        self.assertEqual(calc_metrics(trades, 1000)["total_return_pct"], -1)

    def test_fractional_shares_costs_and_dollar_pnl_reconcile(self):
        raw = [dict(entry_price=200, exit_price=220, side="long")]
        trades = size_trades(apply_costs(raw, 0.1, 0.05), 100)
        trade = trades[0]
        self.assertEqual(trade["quantity"], 0.5)
        self.assertAlmostEqual(trade["costs_usd"], 0.3)
        self.assertAlmostEqual(trade["gross_pnl_usd"] - trade["costs_usd"], trade["pnl_usd"])
        self.assertAlmostEqual(trade["balance_after"], 109.7)

    def test_exhausted_account_stops_taking_positions(self):
        trades = size_trades(self.trades([-100, 20]), 100)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["balance_after"], 0)

    def test_sizing_does_not_change_buy_sell_signals(self):
        candles = descending_waves_then_breakout()
        results = [run_backtest(candles=candles, line_breakout_buy=True, entry_barrier_sell=True,
                                initial_capital=100, compounding=mode) for mode in (True, False)]
        signal_fields = ("entry_date", "exit_date", "entry_reason", "exit_reason")
        self.assertEqual([[tuple(t.get(key) for key in signal_fields) for t in r["trade_log"]]
                          for r in results][0],
                         [[tuple(t.get(key) for key in signal_fields) for t in r["trade_log"]]
                          for r in results][1])
        for result in results:
            self.assertAlmostEqual(sum(t["pnl_usd"] for t in result["trade_log"]),
                                   result["final_capital"] - 100, delta=0.005)

    def test_trade_and_stats_endpoints_share_account_ledger(self):
        candles = descending_waves_then_breakout()
        for mode in (True, False):
            options = dict(symbol="TEST", strategy="sloped_lines", line_breakout_buy=True,
                           entry_barrier_sell=True, compounding=mode, initial_capital=100)
            with patch.object(server, "fetch_market_candles", return_value=(candles, "1d", "1y")):
                trades = asyncio.run(server.api_trades(**options))["trades"]
                stats = asyncio.run(server.api_stats(**options))
            self.assertTrue(trades)
            self.assertEqual(stats["compounding"], mode)
            self.assertAlmostEqual(sum(t["pnl_usd"] for t in trades), stats["total_pnl_usd"], delta=0.005)
            for trade in trades:
                self.assertGreater(trade["quantity"], 0)
                self.assertLessEqual(trade["position_value"], trade["balance_before"])

    def test_invalid_capital_is_rejected(self):
        for amount in (0, -1, math.inf, math.nan):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                size_trades([], amount)
            with self.subTest(amount=amount), self.assertRaises(HTTPException):
                asyncio.run(server.api_stats(symbol="TEST", strategy="sloped_lines", initial_capital=amount))


if __name__ == "__main__":
    unittest.main()
