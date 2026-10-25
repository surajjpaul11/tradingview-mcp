import asyncio
import json
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from tradingview_mcp.core.services.market_data_store import (
    Download, History, MarketDataStore, MarketDataUnavailable, Series, request_bounds,
)


def bar(timestamp, close=101):
    return dict(time=timestamp, date='2026-09-23', open=100, high=max(102, close), low=99,
                close=close, volume=1000, session='regular market')


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.now = 1_800_000_000
        self.store = MarketDataStore(Path(self.directory.name) / 'market.sqlite3', clock=lambda: self.now)
        self.series = Series('yahoo', 'AAPL', '1d')
        self.start, self.end = self.now - 10 * 86400, self.now + 86400
        self.calls = []

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def fetch(self, a, b):
        self.calls.append((a, b))
        return [bar(a + 100)]

    def history(self, **kwargs):
        return self.store.history(self.series, self.start, self.end, self.fetch, **kwargs)

    def test_persistence_across_restart_and_no_repeat_download(self):
        first = self.history()
        self.assertTrue(first.status['complete'])
        self.store.close()
        self.store = MarketDataStore(self.store.path, clock=lambda: self.now)
        self.assertEqual(first.candles, self.history().candles)
        self.assertEqual(len(self.calls), 1)

    def test_wider_window_downloads_only_uncovered_prefix(self):
        self.history()
        self.store.history(self.series, self.start - 1000, self.end, self.fetch)
        self.assertEqual(self.calls[-1], (self.start - 1000, self.start))

    def test_series_isolation(self):
        self.history()
        for series in [Series('yahoo','SPY','1d'), Series('yahoo','AAPL','1h'),
                       Series('yahoo','AAPL','1d','extended hours'),
                       Series('yahoo','AAPL','1d',price_basis='raw'),
                       Series('hyperliquid','AAPL','1d')]:
            self.store.history(series, self.start, self.end, self.fetch)
        self.assertEqual(len(self.calls), 6)

    def test_two_connections_coalesce_concurrent_requests(self):
        other = MarketDataStore(self.store.path, clock=lambda: self.now)
        entered, release = threading.Event(), threading.Event()
        def slow(a, b):
            entered.set()
            release.wait(3)
            return self.fetch(a, b)
        try:
            with ThreadPoolExecutor(2) as pool:
                first = pool.submit(self.store.history, self.series, self.start, self.end, slow)
                self.assertTrue(entered.wait(1))
                second = pool.submit(other.history, self.series, self.start, self.end, slow)
                release.set()
                self.assertEqual(first.result().candles, second.result().candles)
            self.assertEqual(len(self.calls), 1)
        finally:
            other.close()

    def test_provider_cooldown_applies_to_other_symbols(self):
        def fail(a,b):
            raise RuntimeError('HTTP 429')
        with self.assertRaises(MarketDataUnavailable):
            self.store.history(self.series, self.start, self.end, fail)
        with self.assertRaises(MarketDataUnavailable):
            self.store.history(Series('yahoo','SPY','1d'), self.start, self.end, self.fetch)
        self.assertEqual(self.calls, [])

    def test_stale_reads_return_immediately_and_failure_preserves_generation(self):
        first = self.history()
        self.now += 120
        entered, release = threading.Event(), threading.Event()
        def fail(a,b):
            entered.set()
            release.wait(2)
            raise RuntimeError('provider down')
        second = self.store.history(self.series, self.start, self.end, fail)
        self.assertEqual(first.candles, second.candles)
        self.assertTrue(second.status['stale'])
        self.assertTrue(entered.wait(1))
        release.set()
        self.store.close()
        fallback = self.history()
        self.assertEqual(first.status['data_revision'], fallback.status['data_revision'])
        self.assertIn('provider down', fallback.status['error'])

    def test_weekend_gap_coverage_is_not_inferred_from_bar_count(self):
        self.history()
        self.history()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.history().candles), 1)

    def test_explicit_empty_closed_window_is_cached(self):
        calls=[]
        def closed(a,b):
            calls.append(1)
            return Download([], allow_empty=True)
        self.store.history(self.series,self.start,self.end,closed,require_complete=False)
        result=self.store.history(self.series,self.start,self.end,closed,require_complete=False)
        self.assertEqual(result.candles,[])
        self.assertEqual(len(calls),1)

    def test_invalid_or_unexplained_empty_responses_do_not_publish(self):
        for case, rows in enumerate([[], [bar(self.start+100, float('nan'))], [dict(bar(self.start+100),volume=-1)]]):
            with self.subTest(rows=rows), self.assertRaises(MarketDataUnavailable):
                # Separate providers avoid sharing the previous failure's cooldown.
                self.store.history(Series('test'+str(case), 'BAD', '1d'), self.start, self.end, lambda a,b: rows)
                self.calls.append(1)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM candles').fetchone()[0], 0)

    def test_retention_limit_is_visible_and_blocks_backtests(self):
        def limited(a,b):
            return Download([bar(a+500)],'provider retention',coverage_start=a+500)
        result=self.store.history(self.series,self.start,self.end,limited,require_complete=False)
        self.assertFalse(result.status['complete'])
        with self.assertRaises(MarketDataUnavailable):
            self.store.history(self.series,self.start,self.end,limited)

    def test_retention_limited_tail_can_still_refresh(self):
        series=Series('hyperliquid','BTC','1m','24/7','raw')
        def limited(a,b):
            return Download([bar(b-500)],'retention limit',coverage_start=b-500)
        first=self.store.history(series,self.start,self.end,limited,require_complete=False)
        self.now+=120
        self.store._refresh(series,self.start,self.end,lambda a,b:Download([bar(b-100)],'retention limit',coverage_start=b-100))
        second=self.store.history(series,self.start,self.end,limited,require_complete=False)
        self.assertGreater(second.status['as_of'],first.status['as_of'])
        self.assertFalse(second.status['complete'])

    def test_pinned_revision_survives_background_updates(self):
        first=self.history()
        self.now+=120
        self.store._refresh(self.series,self.start,self.end,lambda a,b:[bar(a+100,105)])
        pinned=self.history(revision=first.status['data_revision'])
        self.assertEqual(pinned.candles,first.candles)
        self.assertNotEqual(self.history().status['data_revision'],first.status['data_revision'])
        with self.assertRaises(ValueError):
            self.store.history(Series('yahoo','SPY','1d'),self.start,self.end,self.fetch,revision=first.status['data_revision'])

    def test_adjustment_change_rebuilds_entire_covered_span_atomically(self):
        # Populate the same completed bar that will fall in the overlapping tail.
        ts=self.end-3*86400
        self.store.history(self.series,self.start,self.end,lambda a,b:[bar(ts)])
        self.now+=120
        calls=[]
        def revised(a,b):
            calls.append((a,b))
            return [bar(ts,105)]
        self.store._refresh(self.series,self.start,self.end,revised)
        self.assertEqual(calls[-1],(self.start,self.end))
        self.assertEqual(len(calls),2)
        self.assertEqual(self.history().candles[0]['close'],105)

    def test_weekly_audit_fetches_entire_cached_window(self):
        self.history()
        self.now+=8*86400
        self.store._refresh(self.series,self.start,self.end,self.fetch)
        self.assertEqual(self.calls[-1],(self.start,self.end))

    def test_snapshot_is_immutable_validated_and_binds_full_preset(self):
        first=self.history()
        snapshot=self.store.save_snapshot(self.series,self.start,self.end,first,origin='reconstructed')
        record={'parameters':{'compounding':True},'performance':{'return':49.01}}
        self.store.bind_saved_run(record,'sloped_lines','AAPL',snapshot,engine_revision='abc',observed={'return':48})
        self.now+=120
        self.store._refresh(self.series,self.start,self.end,lambda a,b:[bar(a+100,105)])
        frozen=self.history(snapshot_id=snapshot)
        self.assertEqual(frozen.candles,first.candles)
        self.assertEqual(frozen.status['origin'],'reconstructed')
        self.assertEqual(self.store.saved_run(record,'sloped_lines','AAPL')['snapshot_id'],snapshot)
        self.assertIsNone(self.store.saved_run(dict(record,parameters={'compounding':False}),'sloped_lines','AAPL'))
        with self.assertRaises(ValueError):
            self.store.snapshot_history(snapshot,Series('yahoo','SPY','1d'),self.start,self.end)
        with self.assertRaises(ValueError):
            self.store.snapshot_history(snapshot,self.series,self.start+1,self.end)

    def test_yahoo_day_periods_include_the_previous_session_on_weekends(self):
        from datetime import datetime, timezone
        from tradingview_mcp.core.services.market_data_store import yahoo_request_bounds
        now=datetime(2026,10,25,12,tzinfo=timezone.utc)
        start,end=yahoo_request_bounds('AAPL','1d',now=now)
        self.assertEqual(datetime.fromtimestamp(start,timezone.utc).date().isoformat(),'2026-10-23')
        start,end=yahoo_request_bounds('AAPL','5d',now=now)
        self.assertEqual(datetime.fromtimestamp(start,timezone.utc).date().isoformat(),'2026-10-19')

    def test_expired_process_lease_is_recoverable(self):
        with self.store.connection() as db:
            db.execute('INSERT INTO fetch_state(key,lease_owner,lease_until) VALUES (?,?,?)',('provider:yahoo','dead',self.now-1))
        self.assertTrue(self.history().status['complete'])


class EndpointTests(unittest.TestCase):
    def test_slow_provider_does_not_block_page_and_reports_errors(self):
        from tradingview_mcp.ui import server
        async def scenario():
            entered=threading.Event()
            def slow(*args):
                entered.set()
                time.sleep(.15)
                raise MarketDataUnavailable('rate limited',90)
            with patch.object(server,'fetch_market_candles',side_effect=slow):
                request=asyncio.create_task(server.api_candles(symbol='AAPL'))
                await asyncio.to_thread(entered.wait,1)
                html=await asyncio.wait_for(server.read_root(),.1)
                self.assertIn('<html',html.lower())
                with self.assertRaises(server.HTTPException) as exc:
                    await request
                self.assertEqual(exc.exception.status_code,503)
                self.assertEqual(exc.exception.headers['Retry-After'],'90')
        asyncio.run(scenario())

    def test_metadata_and_partial_failure_are_not_lost_by_strategy_fallbacks(self):
        from tradingview_mcp.ui import server
        with tempfile.TemporaryDirectory() as directory:
            store=MarketDataStore(Path(directory)/'cache.sqlite3')
            def fail(*args):
                return server._stored_history(Series('yahoo','AAPL','1d'),1,100,lambda a,b:[]), '1d','1y'
            try:
                with patch.object(server,'get_market_store',return_value=store),patch.object(server,'fetch_market_candles',side_effect=fail):
                    with self.assertRaises(server.HTTPException) as exc:
                        asyncio.run(server.api_stats(symbol='AAPL',strategy='sloped_lines'))
                self.assertEqual(exc.exception.status_code,503)
            finally:
                store.close()

class AdapterAndSavedRunTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = MarketDataStore(Path(self.directory.name) / 'cache.sqlite3')
        from tradingview_mcp.ui import server
        self.server = server
        self.patcher = patch.object(server, 'get_market_store', return_value=self.store)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.store.close()
        self.directory.cleanup()

    def test_chart_metadata_revision_and_invalid_snapshot_http_status(self):
        start,end=request_bounds('1y')
        def download(*args): return [bar(start+100)],'1d','1y'
        with patch.object(self.server,'_download_market_candles',side_effect=download):
            result=asyncio.run(self.server.api_chart_candles(symbol='AAPL'))
            self.assertEqual(result['data_status']['source'],'sqlite')
            revision=result['data_status']['data_revision']
            again=asyncio.run(self.server.api_candles(symbol='AAPL',data_revision=revision))
            self.assertEqual(result['candles'],again['candles'])
            with self.assertRaises(self.server.HTTPException) as error:
                asyncio.run(self.server.api_chart_candles(symbol='SPY',snapshot_id='missing'))
            self.assertEqual(error.exception.status_code,422)

    def test_saved_cost_parameters_reach_the_engine_and_reject_invalid_values(self):
        async def check():
            context={'costs':{'commission_pct':.25,'slippage_pct':.02}}
            token=self.server._history_context.set(context)
            try:
                resolved=self.server._resolve_sloped_params('AAPL')
                self.assertEqual(resolved['commission_pct'],.25)
                self.assertEqual(resolved['slippage_pct'],.02)
            finally:
                self.server._history_context.reset(token)
            with self.assertRaises(self.server.HTTPException) as error:
                await self.server.api_stats(symbol='AAPL',commission_pct=-1)
            self.assertEqual(error.exception.status_code,422)
        asyncio.run(check())

    def test_closed_weekend_coverage_does_not_call_yahoo(self):
        from datetime import datetime, timezone
        start=int(datetime(2026,10,24,tzinfo=timezone.utc).timestamp())
        end=start+2*86400
        with patch.object(self.server,'_download_market_candles') as fetch:
            result=asyncio.run(self.server.api_chart_candles(symbol='AAPL',start_date='2026-10-24',end_date='2026-10-25'))
        self.assertEqual(result['candles'],[])
        self.assertTrue(result['data_status']['complete'])
        fetch.assert_not_called()

    def test_research_adapter_preserves_raw_prices_and_uses_sqlite(self):
        from tradingview_mcp.core.services import backtest_service as service
        start,end=request_bounds('1y')
        with patch.object(service,'_download_ohlcv',return_value=[bar(start+100)]) as fetch, \
             patch('tradingview_mcp.core.services.market_data_store.get_market_store',return_value=self.store):
            first=service._fetch_ohlcv('AAPL','1y')
            second=service._fetch_ohlcv('AAPL','1y')
        self.assertEqual(first,second)
        self.assertNotIn('time',first[0])
        fetch.assert_called_once()
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT price_basis FROM candle_series').fetchone()[0],'raw')

    def test_legacy_saved_best_reconstructs_once_without_overwriting_record(self):
        cfg={'timeframe':'1d','period':'1y','parameters':{},'performance':{'total_pnl_pct':17.07},
             'backtest_window':{'start_date':'2025-09-23','end_date':'2026-09-22','trading_window':'regular market'}}
        start,end=request_bounds('1y','2025-09-23','2026-09-22')
        with patch('tradingview_mcp.core.services.strategy_config.get_best_parameters',return_value=cfg), \
             patch.object(self.server,'_download_market_candles',return_value=([bar(start+100)],'1d','1y')) as fetch:
            first=asyncio.run(self.server.api_best_parameters(strategy='other',symbol='SPY',capture_snapshot=True))
            second=asyncio.run(self.server.api_best_parameters(strategy='other',symbol='SPY',capture_snapshot=True))
        self.assertEqual(first['data']['snapshot_id'],second['data']['snapshot_id'])
        self.assertEqual(first['data']['snapshot_origin'],'reconstructed')
        self.assertEqual(first['data']['performance']['total_pnl_pct'],17.07)
        self.assertNotIn('snapshot_id',cfg)
        fetch.assert_called_once()

    def test_new_best_preserves_original_supplied_candles(self):
        from tradingview_mcp.core.services import strategy_config
        start,end=request_bounds('1y','2025-09-23','2026-09-22')
        path=Path(self.directory.name)/'best.json'
        with patch.object(strategy_config,'get_config_path',return_value=path), \
             patch('tradingview_mcp.core.services.market_data_store.get_market_store',return_value=self.store):
            record=strategy_config.set_best_parameters('sloped_lines','AAPL',{'compounding':True},
                    performance={'total_pnl_pct':1},observed={'total_pnl_pct':1},candles=[bar(start+100)],
                    backtest_window={'start_date':'2025-09-23','end_date':'2026-09-22'})
        run=self.store.saved_run(record,'sloped_lines','AAPL')
        self.assertEqual(run['origin'],'original')
        self.assertEqual(run['verification'],'verified')
        self.assertTrue(path.exists())
