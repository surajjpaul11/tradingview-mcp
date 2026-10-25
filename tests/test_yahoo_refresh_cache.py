import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from tradingview_mcp.ui import server
from tradingview_mcp.ui.server import _format_trade_candle_datetime


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


class FakeAfterHoursFrame(FakeFrame):
    def iterrows(self):
        yield datetime(2026, 9, 23, 22, 0, tzinfo=timezone.utc), {
            "Open": 100.0,
            "High": 102.0,
            "Low": 99.0,
            "Close": 101.0,
            "Volume": 0.0,
        }


class TradeMarkerTimestampTests(unittest.TestCase):
    def test_intraday_trade_marker_uses_exact_candle_epoch(self):
        candles = [{
            "time": 1784628000,
            "date": "2026-07-21 06:00",
        }]

        value = _format_trade_candle_datetime("2026-07-21 06:00", candles, "09:30:00")

        self.assertEqual(value, "2026-07-21T10:00:00+00:00")


class YahooRefreshCacheTests(unittest.TestCase):
    def setUp(self):
        from tradingview_mcp.core.services.market_data_store import MarketDataStore, request_bounds, yahoo_request_bounds
        self.directory = tempfile.TemporaryDirectory()
        self.store = MarketDataStore(Path(self.directory.name) / 'market.sqlite3')
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.store.close)
        store_patch = patch.object(server, 'get_market_store', return_value=self.store)
        store_patch.start()
        self.addCleanup(store_patch.stop)
        bounds_patch = patch.object(server, 'request_bounds', side_effect=lambda period, start=None, end=None:
            request_bounds(period, start, end, now=datetime(2026, 9, 24, tzinfo=timezone.utc)))
        bounds_patch.start()
        self.addCleanup(bounds_patch.stop)
        yahoo_bounds_patch = patch.object(server, 'yahoo_request_bounds', side_effect=lambda symbol, period, session, start=None, end=None:
            yahoo_request_bounds(symbol, period, session, start, end, now=datetime(2026, 9, 24, tzinfo=timezone.utc)))
        yahoo_bounds_patch.start()
        self.addCleanup(yahoo_bounds_patch.stop)

    def test_repeated_dashboard_requests_share_recent_yahoo_candles(self):
        ticker = Mock()
        ticker.history.return_value = FakeFrame()

        with patch.object(server.yf, "Ticker", return_value=ticker) as ticker_factory:
            first = server.fetch_market_candles("AAPL", "1d", "1y", "regular market")
            second = server.fetch_market_candles("AAPL", "1d", "1y", "regular market")

        self.assertEqual(first, second)
        self.assertEqual(len(first[0]), 1)
        ticker_factory.assert_called_once_with("AAPL")
        ticker.history.assert_called_once_with(start="2025-09-24", end="2026-09-25", interval="1d", prepost=False, auto_adjust=True)

    def test_window_is_part_of_cache_key_and_extended_hours_are_requested(self):
        ticker = Mock()
        ticker.history.return_value = FakeFrame()

        with patch.object(server.yf, "Ticker", return_value=ticker) as ticker_factory:
            server.fetch_market_candles("AAPL", "1d", "1y", "regular market")
            server.fetch_market_candles("AAPL", "1d", "1y", "after hours")

        self.assertEqual(ticker_factory.call_count, 2)
        self.assertEqual(ticker.history.call_args_list[0].kwargs["prepost"], False)
        self.assertEqual(ticker.history.call_args_list[1].kwargs["prepost"], True)

    def test_intraday_candles_include_a_chart_session_label(self):
        ticker = Mock()
        ticker.history.return_value = FakeAfterHoursFrame()

        with patch.object(server.yf, "Ticker", return_value=ticker):
            candles, _, _ = server.fetch_market_candles("AAPL", "30m", "5d", "after hours")

        self.assertEqual(candles[0]["session"], "after hours")

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
