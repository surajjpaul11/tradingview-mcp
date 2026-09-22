"""Offline checks for the research-only cross-stock scanner."""

import unittest
from datetime import date, timedelta

from tradingview_mcp.core.services.opportunity_service import (
    _wilson_interval,
    scan_opportunities,
    scan_symbol_candles,
)


class OpportunityServiceTests(unittest.TestCase):
    def test_small_history_is_not_reported_as_a_probability(self):
        candles = [{"date": str(date(2025, 1, 1) + timedelta(days=i)),
                    "close": 100.0, "open": 100.0, "high": 101.0,
                    "low": 99.0, "volume": 1000} for i in range(60)]

        def runner(series, include_open=False):
            trades = [
                {"entry_date": candles[5]["date"], "exit_date": candles[10]["date"],
                 "entry_price": 100, "exit_price": 110, "side": "long"},
                {"entry_date": candles[12]["date"], "exit_date": candles[14]["date"],
                 "entry_price": 100, "exit_price": 80, "side": "short"},
            ]
            if include_open and len(series) == 60:
                trades.append({"entry_date": candles[-1]["date"],
                               "entry_price": 100, "side": "long", "exit_date": None})
            return trades

        row = scan_symbol_candles("TEST", candles, {"example": runner})[0]
        self.assertEqual(row["signal"], "buy")
        self.assertEqual(row["closed_trades"], 1)  # A short is not evidence for a buy.
        self.assertEqual(row["average_net_trade_return_pct"], 9.7)
        self.assertEqual(row["evidence_status"], "limited_history")
        self.assertIsNone(row["calibrated_gain_probability_pct"])

    def test_interval_and_watchlist_validation(self):
        self.assertEqual(_wilson_interval(9, 10), (59.6, 98.2))
        with self.assertRaises(ValueError):
            scan_opportunities(["BAD/SYMBOL"], fetcher=lambda *_: [])


if __name__ == "__main__":
    unittest.main()
