import asyncio
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from tradingview_mcp.ui import server
from tradingview_mcp.core.services.strategy_config import get_best_parameters
from tests.test_yahoo_refresh_cache import FakeFrame
from tests.test_sloped_lines_strategy import descending_waves_then_breakout


class SavedBacktestWindowTests(unittest.TestCase):
    def setUp(self):
        server._yahoo_candle_cache.clear()

    def test_aapl_has_the_reproduced_captured_window(self):
        window = get_best_parameters("sloped_lines", "AAPL")["backtest_window"]
        self.assertEqual(window["start_date"], "2025-09-26")
        self.assertEqual(window["end_date"], "2026-09-25")

    def test_dates_are_validated_before_fetching(self):
        for start, end in [("2026-09-01", None), (None, "2026-09-30"),
                           ("2026-09-30", "2026-09-01"), ("bad", "2026-09-30")]:
            with self.subTest(start=start, end=end), self.assertRaises(HTTPException) as error:
                server.validate_backtest_window(start, end)
            self.assertEqual(error.exception.status_code, 422)

    def test_yahoo_end_is_inclusive_and_cache_separates_rolling_from_fixed(self):
        ticker = Mock()
        ticker.history.return_value = FakeFrame()
        with patch.object(server.yf, "Ticker", return_value=ticker):
            server.fetch_market_candles("AAPL", "1d", "1y", "regular market")
            fixed = server.fetch_market_candles("AAPL", "1d", "1y", "regular market", "2026-09-01", "2026-09-23")
            ticker.history.assert_called_with(start="2026-09-01", end="2026-09-24", interval="1d", prepost=False)
            self.assertEqual(fixed[0][0]["date"], "2026-09-23")
            server.fetch_market_candles("AAPL", "1d", "1y", "regular market", "2026-09-01", "2026-09-23")
            self.assertEqual(ticker.history.call_count, 2)

    def test_every_dashboard_data_endpoint_uses_the_same_bounds(self):
        candles = descending_waves_then_breakout()
        for endpoint in (server.api_candles, server.api_chart_candles, server.api_trades,
                         server.api_stats, server.api_trendlines):
            with self.subTest(endpoint=endpoint.__name__):
                arguments = dict(symbol="TEST", start_date="2025-09-26", end_date="2026-09-25")
                if endpoint not in (server.api_candles, server.api_chart_candles):
                    arguments.update(strategy="sloped_lines", line_breakout_buy=True, entry_barrier_sell=True)
                with patch.object(server, "fetch_market_candles", return_value=(candles, "1d", "1y")) as fetch:
                    result = asyncio.run(endpoint(**arguments))
                self.assertNotIn("error", result)
                self.assertEqual(fetch.call_args.args[-2:], ("2025-09-26", "2026-09-25"))


if __name__ == "__main__":
    unittest.main()
