"""Causal signal and fill checks for the volume-confirmed breakout."""

import unittest
from datetime import date, timedelta
from unittest.mock import patch

from tradingview_mcp.core.services.opportunity_service import scan_symbol_candles
from tradingview_mcp.core.services.signal_service import get_live_signal
from tradingview_mcp.core.services.volume_price_breakout import run_volume_price_breakout


def base_candles():
    candles = []
    for i in range(60):
        candles.append({"date": str(date(2025, 1, 1) + timedelta(days=i)),
                        "open": 100.0, "high": 101.0, "low": 99.0,
                        "close": 100.0, "volume": 100.0})
    candles[-1].update(open=100.0, high=105.0, low=100.0,
                       close=104.0, volume=250.0)
    return candles


class VolumePriceBreakoutTests(unittest.TestCase):
    def test_last_bar_is_pending_and_next_open_is_entry(self):
        candles = base_candles()
        self.assertEqual(run_volume_price_breakout(candles), [])
        pending = run_volume_price_breakout(candles, include_open=True)[-1]
        self.assertTrue(pending["pending_entry"])
        self.assertEqual(pending["signal_date"], candles[-1]["date"])
        self.assertEqual(scan_symbol_candles("TEST", candles,
                         {"volume_price_breakout": run_volume_price_breakout})[0]["signal"], "buy")
        with patch("tradingview_mcp.core.services.signal_service._fetch_ohlcv", return_value=candles):
            signal = get_live_signal("TEST", "volume_price_breakout")
        self.assertEqual(signal["signal"], "long")
        self.assertEqual(signal["signal_context"], {"price_gain_pct": 4.0, "volume_ratio": 2.5})

        candles.append({"date": "2025-03-02", "open": 105.0, "high": 106.0,
                        "low": 104.0, "close": 105.0, "volume": 100.0})
        live_row = scan_symbol_candles("TEST", candles,
                       {"volume_price_breakout": run_volume_price_breakout})[0]
        self.assertEqual(live_row["signal"], "none")  # Today's fill was yesterday's signal.
        with patch("tradingview_mcp.core.services.signal_service._fetch_ohlcv", return_value=candles):
            signal = get_live_signal("TEST", "volume_price_breakout")
        self.assertEqual(signal["signal"], "none")
        self.assertEqual(run_volume_price_breakout(candles, include_open=True)[-1]["entry_price"], 105.0)

        candles.append({"date": "2025-03-03", "open": 106.0, "high": 116.0,
                        "low": 105.0, "close": 115.0, "volume": 100.0})
        trade = run_volume_price_breakout(candles)[0]
        self.assertEqual(trade["entry_date"], "2025-03-02")
        self.assertEqual(trade["entry_price"], 105.0)
        self.assertEqual(trade["exit_reason"], "take_profit")

    def test_gap_stop_uses_open_and_spike_needs_both_conditions(self):
        candles = base_candles()
        candles[-1]["volume"] = 150.0
        self.assertEqual(run_volume_price_breakout(candles, include_open=True), [])
        candles[-1]["volume"] = 250.0
        candles[-1]["close"] = 102.0
        self.assertEqual(run_volume_price_breakout(candles, include_open=True), [])
        candles[-1]["close"] = 104.0
        candles.append({"date": "2025-03-02", "open": 105.0, "high": 106.0,
                        "low": 104.0, "close": 105.0, "volume": 100.0})
        candles.append({"date": "2025-03-03", "open": 95.0, "high": 96.0,
                        "low": 94.0, "close": 95.0, "volume": 100.0})
        trade = run_volume_price_breakout(candles)[0]
        self.assertEqual(trade["exit_reason"], "gap_stop")
        self.assertEqual(trade["exit_price"], 95.0)


if __name__ == "__main__":
    unittest.main()
