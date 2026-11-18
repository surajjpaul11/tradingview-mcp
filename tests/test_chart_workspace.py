import json
import unittest
from unittest.mock import patch
from tradingview_mcp.ui import server

class _Response:
    def __init__(self,payload): self.payload=payload
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def read(self): return json.dumps(self.payload).encode()

class ChartWorkspaceBackendTests(unittest.TestCase):
    def test_aggregate_candles(self):
        candles=[{"time":0,"open":1,"high":2,"low":1,"close":2,"volume":3},{"time":60,"open":2,"high":4,"low":1.5,"close":3,"volume":5}]
        self.assertEqual(server._aggregate_candles(candles,120)[0]["volume"],8)
        self.assertEqual(server._aggregate_candles(candles,120)[0]["close"],3)

    def test_hyperliquid_history_is_normalized_and_deduplicated(self):
        raw=[{"t":2000,"o":"2","h":"3","l":"1","c":"2.5","v":"4"},{"t":1000,"o":"1","h":"2","l":".5","c":"1.5","v":"3"},{"t":2000,"o":"2","h":"4","l":"1","c":"3","v":"5"}]
        with patch.object(server.urllib.request,"urlopen",return_value=_Response(raw)):
            candles,tf,period=server._download_hyperliquid_candles("BTC","1m","1d")
        self.assertEqual([c["time"] for c in candles],[1,2])
        self.assertEqual(candles[-1]["close"],3)
        self.assertEqual((tf,period),("1m","1d"))

    def test_source_dispatch_keeps_yahoo_default(self):
        with patch.object(server,"fetch_market_candles",return_value=([],"1d","1y")) as fetch:
            server.fetch_source_candles("yahoo","AAPL","1d","1y","regular market")
        fetch.assert_called_once_with("AAPL","1d","1y","regular market")

if __name__=='__main__': unittest.main()
