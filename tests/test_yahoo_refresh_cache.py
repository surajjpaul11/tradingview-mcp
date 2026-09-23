import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from tradingview_mcp.ui import server


class FakeFrame:
    empty = False

    def iterrows(self):
        yield datetime(2026, 9, 23, tzinfo=timezone.utc), {
            "Open": 100.0,
            "High": 102.0,
            "Low": 99.0,
            "Close": 101.0,
            "Volume": 1_000.0,
        }


class YahooRefreshCacheTests(unittest.TestCase):
    def setUp(self):
        server._yahoo_candle_cache.clear()

    def test_repeated_dashboard_requests_share_recent_yahoo_candles(self):
        ticker = Mock()
        ticker.history.return_value = FakeFrame()

        with patch.object(server.yf, "Ticker", return_value=ticker) as ticker_factory:
            first = server.fetch_market_candles("AAPL", "1d", "1y")
            second = server.fetch_market_candles("AAPL", "1d", "1y")

        self.assertEqual(first, second)
        self.assertEqual(len(first[0]), 1)
        ticker_factory.assert_called_once_with("AAPL")
        ticker.history.assert_called_once_with(period="1y", interval="1d", prepost=False)

    def test_window_is_part_of_cache_key_and_extended_hours_are_requested(self):
        ticker = Mock()
        ticker.history.return_value = FakeFrame()

        with patch.object(server.yf, "Ticker", return_value=ticker) as ticker_factory:
            server.fetch_market_candles("AAPL", "1d", "1y", "regular market")
            server.fetch_market_candles("AAPL", "1d", "1y", "after hours")

        self.assertEqual(ticker_factory.call_count, 2)
        self.assertEqual(ticker.history.call_args_list[0].kwargs["prepost"], False)
        self.assertEqual(ticker.history.call_args_list[1].kwargs["prepost"], True)

    def test_homepage_window_selection_is_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "market_hours.json"
            path.write_text(json.dumps(server.load_market_config()), encoding="utf-8")
            with patch.dict(os.environ, {"MARKET_HOURS_CONFIG": str(path)}):
                result = asyncio.run(server.api_set_trading_window("pre-market"))

            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(result["active_trading_window"], "pre-market")
            self.assertEqual(saved["active_trading_window"], "pre-market")


if __name__ == "__main__":
    unittest.main()
