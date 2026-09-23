import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from tradingview_mcp.core.services.market_hours import (
    DEFAULT_CONFIG,
    get_market_status,
    timestamp_in_trading_window,
)


EASTERN = ZoneInfo("America/New_York")


def config(**overrides):
    value = dict(DEFAULT_CONFIG)
    value.update(overrides)
    return value


class MarketHoursTests(unittest.TestCase):
    def test_market_is_open_during_configured_session(self):
        status = get_market_status(datetime(2026, 9, 23, 10, 15, tzinfo=EASTERN), config())

        self.assertTrue(status["is_open"])
        self.assertEqual(status["next_refresh_at"], "2026-09-23T10:30:00-04:00")

    def test_market_is_closed_at_configured_close(self):
        status = get_market_status(datetime(2026, 9, 23, 16, 0, tzinfo=EASTERN), config())

        self.assertFalse(status["is_open"])
        self.assertEqual(status["next_refresh_at"], "2026-09-24T09:30:00-04:00")

    def test_weekends_and_configured_holidays_are_closed(self):
        weekend = get_market_status(datetime(2026, 9, 26, 11, 0, tzinfo=EASTERN), config())
        holiday = get_market_status(
            datetime(2026, 9, 24, 11, 0, tzinfo=EASTERN),
            config(holidays=["2026-09-24"]),
        )

        self.assertFalse(weekend["is_open"])
        self.assertEqual(weekend["next_refresh_at"], "2026-09-28T09:30:00-04:00")
        self.assertFalse(holiday["is_open"])
        self.assertEqual(holiday["next_refresh_at"], "2026-09-25T09:30:00-04:00")

    def test_early_close_overrides_normal_close(self):
        cfg = config(early_closes={"2026-11-27": "13:00"})

        before_close = get_market_status(datetime(2026, 11, 27, 12, 45, tzinfo=EASTERN), cfg)
        after_close = get_market_status(datetime(2026, 11, 27, 13, 0, tzinfo=EASTERN), cfg)

        self.assertTrue(before_close["is_open"])
        self.assertEqual(before_close["session_close"], "2026-11-27T13:00:00-05:00")
        self.assertFalse(after_close["is_open"])

    def test_each_trading_window_expands_the_active_session(self):
        at_five_am = datetime(2026, 9, 23, 5, 0, tzinfo=EASTERN)
        at_six_pm = datetime(2026, 9, 23, 18, 0, tzinfo=EASTERN)
        at_two_am = datetime(2026, 9, 23, 2, 0, tzinfo=EASTERN)

        self.assertFalse(get_market_status(at_five_am, config(), "regular market")["is_open"])
        self.assertTrue(get_market_status(at_five_am, config(), "pre-market")["is_open"])
        self.assertTrue(get_market_status(at_six_pm, config(), "after hours")["is_open"])
        self.assertTrue(get_market_status(at_two_am, config(), "overnight")["is_open"])

    def test_intraday_candles_are_filtered_by_selected_window(self):
        premarket = datetime(2026, 9, 23, 8, 0, tzinfo=EASTERN)
        after_hours = datetime(2026, 9, 23, 18, 0, tzinfo=EASTERN)

        self.assertFalse(timestamp_in_trading_window(premarket, "regular market", config()))
        self.assertTrue(timestamp_in_trading_window(premarket, "pre-market", config()))
        self.assertFalse(timestamp_in_trading_window(after_hours, "pre-market", config()))
        self.assertTrue(timestamp_in_trading_window(after_hours, "after hours", config()))
        self.assertTrue(timestamp_in_trading_window(after_hours, "overnight", config()))


if __name__ == "__main__":
    unittest.main()
