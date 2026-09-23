import unittest
from datetime import datetime, timezone
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

        with patch.object(server.yf, "Ticker", return_value=ticker) as ticker_factory, patch.object(
            server, "load_market_config", return_value={"yahoo_cache_seconds": 60}
        ):
            first = server.fetch_market_candles("AAPL", "1d", "1y")
            second = server.fetch_market_candles("AAPL", "1d", "1y")

        self.assertEqual(first, second)
        self.assertEqual(len(first[0]), 1)
        ticker_factory.assert_called_once_with("AAPL")
        ticker.history.assert_called_once_with(period="1y", interval="1d")


if __name__ == "__main__":
    unittest.main()
