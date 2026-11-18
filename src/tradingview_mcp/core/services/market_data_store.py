"""Persistent, provider-independent candle history. SQLite only; no indicator dependencies.

Coverage describes successful provider queries, not an expected count of trading bars.
Each publication creates an immutable generation so concurrent chart/calculation
requests can pin the same revision. Network calls never hold a SQLite transaction.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import math
import os
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable


class MarketDataUnavailable(RuntimeError):
    def __init__(self, message, retry_after=60):
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


@dataclass(frozen=True)
class Series:
    provider: str
    symbol: str
    interval: str
    session: str = 'regular market'
    price_basis: str = 'adjusted'
    exchange_timezone: str = 'provider'

    @property
    def key(self):
        # Timezone is metadata; session/normalization version belong to identity.
        return json.dumps([self.provider.lower(), self.symbol.upper(), self.interval,
                           self.session, self.price_basis, 1], separators=(',', ':'))


@dataclass
class Download:
    candles: list[dict]
    limitation: str | None = None
    coverage_start: int | None = None
    coverage_end: int | None = None
    allow_empty: bool = False


@dataclass
class History:
    candles: list[dict]
    status: dict


_SCHEMA = '''
CREATE TABLE IF NOT EXISTS candle_series (
 id INTEGER PRIMARY KEY, identity TEXT NOT NULL UNIQUE, provider TEXT NOT NULL,
 symbol TEXT NOT NULL, interval TEXT NOT NULL, session TEXT NOT NULL,
 price_basis TEXT NOT NULL, exchange_timezone TEXT NOT NULL,
 active_generation INTEGER NOT NULL DEFAULT 0, audited_at REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS candles (
 series_id INTEGER NOT NULL REFERENCES candle_series(id), generation INTEGER NOT NULL,
 time INTEGER NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,
 close REAL NOT NULL, volume REAL NOT NULL, is_final INTEGER NOT NULL,
 fetched_at REAL NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(series_id,generation,time));
CREATE TABLE IF NOT EXISTS fetch_coverage (
 series_id INTEGER NOT NULL REFERENCES candle_series(id), generation INTEGER NOT NULL,
 start INTEGER NOT NULL, end INTEGER NOT NULL, checked_at REAL NOT NULL,
 complete INTEGER NOT NULL, limitation TEXT,
 PRIMARY KEY(series_id,generation,start,end));
CREATE TABLE IF NOT EXISTS fetch_state (
 key TEXT PRIMARY KEY, last_attempt REAL, last_success REAL, retry_at REAL DEFAULT 0,
 error TEXT, failures INTEGER DEFAULT 0, lease_owner TEXT, lease_until REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS candle_snapshots (
 id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, series_identity TEXT NOT NULL,
 start INTEGER NOT NULL, end INTEGER NOT NULL, created_at REAL NOT NULL,
 origin TEXT NOT NULL, row_count INTEGER NOT NULL, provenance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshot_candles (
 snapshot_id TEXT NOT NULL REFERENCES candle_snapshots(id), time INTEGER NOT NULL,
 open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
 volume REAL NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(snapshot_id,time));
CREATE TABLE IF NOT EXISTS saved_best_runs (
 fingerprint TEXT PRIMARY KEY, strategy TEXT NOT NULL, symbol TEXT NOT NULL,
 snapshot_id TEXT NOT NULL REFERENCES candle_snapshots(id), parameters TEXT NOT NULL,
 costs TEXT NOT NULL, engine_revision TEXT NOT NULL, expected TEXT NOT NULL,
 observed TEXT NOT NULL, verification TEXT NOT NULL, created_at REAL NOT NULL);
PRAGMA user_version=1;
'''


def database_path():
    return Path(os.environ.get('MARKET_DATA_DB_PATH') or
                Path(__file__).resolve().parents[4] / 'data' / 'market_data.sqlite3')


def request_bounds(period, start_date=None, end_date=None, now=None):
    now = now or datetime.now(timezone.utc)
    if start_date:
        start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + timedelta(days=1)
    else:
        # Stable day boundaries allow the same rolling query to reuse coverage.
        end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        if period == 'max':
            start = datetime(1970, 1, 1, tzinfo=timezone.utc)
        elif period.endswith('mo') or period.endswith('y'):
            months = int(period[:-2]) if period.endswith('mo') else int(period[:-1]) * 12
            index = now.year * 12 + now.month - 1 - months
            year, month = divmod(index, 12)
            month += 1
            start = now.replace(year=year, month=month,
                                day=min(now.day, calendar.monthrange(year, month)[1]),
                                hour=0, minute=0, second=0, microsecond=0)
        elif period.endswith('d'):
            start = (end - timedelta(days=int(period[:-1]) + 1))
        else:
            raise ValueError(f'Unsupported history period: {period}')
    return int(start.timestamp()), int(end.timestamp())


def yahoo_request_bounds(symbol, period, session='regular market', start_date=None, end_date=None, now=None):
    """Yahoo 1d/5d periods mean trading sessions, including the last closed day."""
    now = now or datetime.now(timezone.utc)
    bounds = request_bounds(period, start_date, end_date, now=now)
    if start_date or period not in ('1d', '5d') or symbol.upper().endswith('-USD') or '.' in symbol or '=' in symbol:
        return bounds
    if symbol.startswith('^') and symbol not in {'^GSPC','^VIX','^DJI','^IXIC','^RUT'}:
        return bounds
    from zoneinfo import ZoneInfo
    from tradingview_mcp.core.services.market_hours import load_market_config
    config = load_market_config()
    local = now.astimezone(ZoneInfo(config['timezone']))
    opening = config['trading_windows'][session]['start_time']
    day = local.date() - timedelta(days=int(local.strftime('%H:%M') < opening))
    remaining = int(period[:-1])
    holidays = set(config.get('holidays', []))
    for _ in range(3700):
        if day.weekday() in config['weekdays'] and day.isoformat() not in holidays:
            remaining -= 1
            if remaining == 0:
                return int(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).timestamp()), bounds[1]
        day -= timedelta(days=1)
    raise ValueError('No trading sessions found in the configured calendar')


def interval_seconds(interval):
    return int(interval[:-1]) * {'m': 60, 'h': 3600, 'd': 86400}[interval[-1]]


def fingerprint(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


class MarketDataStore:
    def __init__(self, path=None, clock=time.time):
        self.path = Path(path or database_path())
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._workers = ThreadPoolExecutor(max_workers=4, thread_name_prefix='market-history')
        self._jobs = set()
        self._jobs_lock = threading.Lock()
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(_SCHEMA)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=5000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def close(self):
        self._workers.shutdown(wait=True)

    def _series(self, series):
        with self.connection() as db:
            db.execute('INSERT OR IGNORE INTO candle_series(identity,provider,symbol,interval,session,price_basis,exchange_timezone) VALUES (?,?,?,?,?,?,?)',
                       (series.key, series.provider, series.symbol.upper(), series.interval,
                        series.session, series.price_basis, series.exchange_timezone))
            return dict(db.execute('SELECT * FROM candle_series WHERE identity=?', (series.key,)).fetchone())

    @staticmethod
    def _missing(start, end, coverage):
        cursor, gaps = start, []
        for row in sorted(coverage, key=lambda r: r['start']):
            if not row['complete'] or row['end'] <= cursor:
                continue
            if row['start'] > cursor:
                gaps.append((cursor, min(end, row['start'])))
            cursor = max(cursor, row['end'])
            if cursor >= end:
                break
        if cursor < end:
            gaps.append((cursor, end))
        return [(a, b) for a, b in gaps if a < b]

    def _read(self, series, start, end, revision=None):
        info = self._series(series)
        sid, generation = info['id'], info['active_generation']
        if revision:
            try:
                requested_sid, generation = map(int, revision.split(':'))
            except (ValueError, AttributeError):
                raise ValueError('Invalid data_revision')
            if requested_sid != sid:
                raise ValueError('data_revision does not match this source, symbol, resolution or session')
        with self.connection() as db:
            coverage = [dict(r) for r in db.execute('SELECT * FROM fetch_coverage WHERE series_id=? AND generation=?', (sid, generation))]
            candles = [json.loads(r[0]) for r in db.execute('SELECT payload FROM candles WHERE series_id=? AND generation=? AND time>=? AND time<? ORDER BY time', (sid, generation, start, end))]
            state = db.execute('SELECT * FROM fetch_state WHERE key=?', ('series:' + series.key,)).fetchone()
            provider = db.execute('SELECT * FROM fetch_state WHERE key=?', ('provider:' + series.provider,)).fetchone()
        return info, generation, coverage, candles, dict(state or {}), dict(provider or {})

    def history(self, series: Series, start: int, end: int, fetch: Callable,
                *, require_complete=True, revision=None, snapshot_id=None):
        if start >= end:
            raise ValueError('History start must precede end')
        if snapshot_id:
            return self.snapshot_history(snapshot_id, series, start, end)
        info, generation, coverage, rows, state, provider = self._read(series, start, end, revision)
        missing = self._missing(start, end, coverage)
        now = self.clock()
        checked = max((r['checked_at'] for r in coverage if r['end'] > start and r['start'] < end), default=0)
        historical = end <= now - 86400
        stale = now - checked > (86400 if historical else 60)
        limited = next((r['limitation'] for r in coverage if r['limitation'] and r['end'] > start and r['start'] < end), None)
        retry_at = max(state.get('retry_at') or 0, provider.get('retry_at') or 0)
        if revision and (not coverage or missing):
            raise MarketDataUnavailable('Requested data revision does not cover this window')
        if missing and not revision and not limited:
            if retry_at > now:
                if require_complete or not rows:
                    raise MarketDataUnavailable(state.get('error') or provider.get('error') or 'Provider cooling down', retry_at - now)
            elif rows and not require_complete:
                self._schedule(series, start, end, fetch)
            else:
                self._refresh(series, start, end, fetch, cold=True)
                return self.history(series, start, end, fetch, require_complete=require_complete)
        refreshing = False
        if stale and not revision and retry_at <= now:
            refreshing = self._schedule(series, start, end, fetch)
        complete = not missing
        if require_complete and not rows and complete:
            raise MarketDataUnavailable('There are no trading candles in the requested window')
        if require_complete and not complete:
            raise MarketDataUnavailable(limited or 'Requested historical coverage is incomplete', max(60, retry_at - now))
        status = {'source': 'sqlite', 'provider': series.provider, 'as_of': rows[-1]['time'] if rows else None,
                  'last_refresh': checked or None, 'stale': stale, 'complete': complete,
                  'refreshing': refreshing or (state.get('lease_until') or 0) > now,
                  'error': state.get('error') or provider.get('error'),
                  'retry_after': max(0, int(retry_at - now)), 'limitation': limited,
                  'data_revision': f'{info["id"]}:{generation}'}
        return History(rows, status)

    def _schedule(self, series, start, end, fetch):
        with self._jobs_lock:
            if series.key in self._jobs:
                return True
            self._jobs.add(series.key)
        def run():
            try:
                self._refresh(series, start, end, fetch)
            except Exception:
                pass  # Persisted in fetch_state; cached data remains readable.
            finally:
                with self._jobs_lock:
                    self._jobs.discard(series.key)
        self._workers.submit(run)
        return True

    def _lease(self, keys, owner):
        now = self.clock()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            for key in keys:
                db.execute('INSERT OR IGNORE INTO fetch_state(key) VALUES (?)', (key,))
                row = db.execute('SELECT * FROM fetch_state WHERE key=?', (key,)).fetchone()
                if row['retry_at'] > now:
                    raise MarketDataUnavailable(row['error'] or 'Provider cooling down', row['retry_at'] - now)
                if row['lease_until'] > now:
                    return False
            for key in keys:
                db.execute('UPDATE fetch_state SET lease_owner=?,lease_until=?,last_attempt=? WHERE key=?', (owner, now + 180, now, key))
        return True

    def _release(self, keys, owner, error=None):
        now = self.clock()
        with self.connection() as db:
            for key in keys:
                row = db.execute('SELECT failures FROM fetch_state WHERE key=? AND lease_owner=?', (key, owner)).fetchone()
                if row is None:
                    continue
                failures = row[0] + 1 if error else 0
                # A provider-wide cooldown prevents parallel endpoints hammering Yahoo.
                delay = min(900, 60 * 2 ** min(failures - 1, 4)) if error else 0
                delay = max(delay, getattr(error, 'retry_after', 0) or 0)
                headers = getattr(error, 'headers', None)
                if headers:
                    try:
                        delay = max(delay, int(headers.get('Retry-After', 0)))
                    except (TypeError, ValueError):
                        pass
                db.execute('UPDATE fetch_state SET lease_owner=NULL,lease_until=0,retry_at=?,error=?,failures=?,last_success=CASE WHEN ? IS NULL THEN ? ELSE last_success END WHERE key=? AND lease_owner=?',
                           (now + delay if error else 0, str(error) if error else None, failures,
                            str(error) if error else None, now, key, owner))

    def _refresh(self, series, start, end, fetch, cold=False):
        owner = uuid.uuid4().hex
        keys = ['series:' + series.key]
        if series.provider == 'yahoo':
            keys.append('provider:yahoo')
        deadline = time.monotonic() + 45
        while not self._lease(keys, owner):
            if not cold:
                return
            if time.monotonic() >= deadline:
                raise MarketDataUnavailable('History refresh is still running; please retry', 5)
            time.sleep(.05)
            # A competing process may have completed exactly this request.
            _, _, coverage, _, _, _ = self._read(series, start, end)
            if not self._missing(start, end, coverage):
                return
        try:
            info, generation, coverage, _, _, _ = self._read(series, start, end)
            missing = self._missing(start, end, coverage)
            now = self.clock()
            checked = max((r['checked_at'] for r in coverage if r['end'] > start and r['start'] < end), default=0)
            if cold and not missing and now - checked < (86400 if end <= now - 86400 else 60):
                self._release(keys, owner)
                return
            audit = series.provider == 'yahoo' and now - info['audited_at'] >= 7 * 86400
            if audit and coverage:
                ranges = [(min(start, min(r['start'] for r in coverage)), max(end, max(r['end'] for r in coverage)))]
            elif any(r['limitation'] for r in coverage):
                # A known retention floor must not freeze the recent tail forever.
                base_seconds = 86400 if series.interval == '5d' else interval_seconds(series.interval)
                ranges = [(max(start, end - 4990 * base_seconds), end)]
            elif missing:
                ranges = missing
            else:
                ranges = [(max(start, end - max(7 * 86400, 5 * interval_seconds(series.interval))), end)]
            downloads = []
            for a, b in ranges:
                downloaded = fetch(a, b)
                downloaded = downloaded if isinstance(downloaded, Download) else Download(downloaded)
                validated = self._validate(downloaded.candles, a, b)
                if not validated and not downloaded.allow_empty:
                    raise MarketDataUnavailable('Provider returned no usable candles; cached history was preserved')
                downloads.append((a, b, downloaded, validated))
            if series.price_basis == 'adjusted' and coverage and not audit:
                # A changed overlap can indicate a dividend/split adjustment affecting
                # the whole series. Publish a coherent replacement, never mixed bases.
                with self.connection() as db:
                    previous = {r['time']: (r['open'], r['high'], r['low'], r['close']) for r in db.execute(
                        'SELECT time,open,high,low,close FROM candles WHERE series_id=? AND generation=?', (info['id'], generation))}
                changed = any(row['time'] in previous and previous[row['time']] != tuple(row[k] for k in ('open','high','low','close'))
                              for _, _, _, rows in downloads for row in rows if row['time'] + interval_seconds(series.interval) < now - 86400)
                if changed:
                    a, b = min(start, min(r['start'] for r in coverage)), max(end, max(r['end'] for r in coverage))
                    downloaded = fetch(a, b)
                    downloaded = downloaded if isinstance(downloaded, Download) else Download(downloaded)
                    validated = self._validate(downloaded.candles, a, b)
                    if not validated:
                        raise MarketDataUnavailable('Adjusted history rebuild returned no candles')
                    downloads = [(a, b, downloaded, validated)]
                    audit = True
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                new_generation = generation + 1
                db.execute('INSERT INTO candles SELECT series_id,?,time,open,high,low,close,volume,is_final,fetched_at,payload FROM candles WHERE series_id=? AND generation=?', (new_generation, info['id'], generation))
                db.execute('INSERT INTO fetch_coverage SELECT series_id,?,start,end,checked_at,complete,limitation FROM fetch_coverage WHERE series_id=? AND generation=?', (new_generation, info['id'], generation))
                for a, b, downloaded, validated in downloads:
                    # Replace an audited/tail interval, including provider-deleted rows.
                    db.execute('DELETE FROM candles WHERE series_id=? AND generation=? AND time>=? AND time<?', (info['id'], new_generation, a, b))
                    for row in validated:
                        db.execute('INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                                   (info['id'], new_generation, row['time'], row['open'], row['high'], row['low'], row['close'], row.get('volume', 0),
                                    int(self._is_final(series, row, now)), now, json.dumps(row, allow_nan=False)))
                    ca, cb = downloaded.coverage_start or a, downloaded.coverage_end or b
                    db.execute('INSERT OR REPLACE INTO fetch_coverage VALUES (?,?,?,?,?,?,?)', (info['id'], new_generation, ca, cb, now, 1, downloaded.limitation))
                zones = {row.get('exchange_timezone') for _, _, _, rows in downloads for row in rows if row.get('exchange_timezone')}
                if len(zones) == 1:
                    db.execute('UPDATE candle_series SET exchange_timezone=? WHERE id=?', (zones.pop(), info['id']))
                db.execute('UPDATE candle_series SET active_generation=?,audited_at=CASE WHEN ? THEN ? ELSE audited_at END WHERE id=?', (new_generation, audit, now, info['id']))
            self._release(keys, owner)
        except Exception as exc:
            self._release(keys, owner, exc)
            if isinstance(exc, MarketDataUnavailable):
                raise
            raise MarketDataUnavailable(str(exc), getattr(exc, 'retry_after', 60)) from exc

    @staticmethod
    def _is_final(series, row, now):
        if series.provider == 'yahoo' and series.interval == '1d' and not series.symbol.upper().endswith('-USD'):
            from zoneinfo import ZoneInfo
            # Yahoo exchange-local daily labels are retained in payloads.
            # Use exchange metadata when available, US market close as legacy default.
            zone = ZoneInfo(row.get('exchange_timezone') or (series.exchange_timezone if series.exchange_timezone != 'provider' else 'America/New_York'))
            day = datetime.fromisoformat(row['date'][:10]).replace(tzinfo=zone)
            close = day.replace(hour=16, minute=15) if str(zone) == 'America/New_York' else day + timedelta(days=1)
            return now >= close.timestamp()
        return row['time'] + interval_seconds(series.interval) <= now

    @staticmethod
    def _validate(rows, start, end):
        result = {}
        for original in rows:
            row = dict(original)
            ts = int(row['time'])
            values = [float(row[k]) for k in ('open', 'high', 'low', 'close')]
            volume = float(row.get('volume') or 0)
            if not all(math.isfinite(v) for v in values + [volume]) or volume < 0:
                raise ValueError('Invalid non-finite OHLCV data')
            o, h, l, c = values
            if l > min(o, c) or h < max(o, c) or l > h:
                raise ValueError('Invalid OHLC price ordering')
            if start <= ts < end:
                row.update(time=ts, open=o, high=h, low=l, close=c, volume=volume)
                result[ts] = row
        return [result[t] for t in sorted(result)]

    def save_snapshot(self, series, start, end, history, *, origin='original', provenance=None):
        if not history.status.get('complete') or not history.candles:
            raise ValueError('A snapshot requires complete, nonempty history')
        content = {'series': series.key, 'start': start, 'end': end, 'candles': history.candles}
        digest = fingerprint(content)
        snapshot_id = fingerprint({'content': digest, 'origin': origin})
        with self.connection() as db:
            db.execute('INSERT OR IGNORE INTO candle_snapshots VALUES (?,?,?,?,?,?,?,?,?)',
                       (snapshot_id, digest, series.key, start, end, self.clock(), origin,
                        len(history.candles), json.dumps(provenance or {})))
            for row in history.candles:
                db.execute('INSERT OR IGNORE INTO snapshot_candles VALUES (?,?,?,?,?,?,?,?)',
                           (snapshot_id, row['time'], row['open'], row['high'], row['low'], row['close'], row.get('volume', 0), json.dumps(row)))
        return snapshot_id

    def snapshot_history(self, snapshot_id, series, start, end):
        with self.connection() as db:
            snapshot = db.execute('SELECT * FROM candle_snapshots WHERE id=?', (snapshot_id,)).fetchone()
            if not snapshot or snapshot['series_identity'] != series.key or snapshot['start'] != start or snapshot['end'] != end:
                raise ValueError('Snapshot does not match this source, symbol, resolution, session and date window')
            rows = [json.loads(r[0]) for r in db.execute('SELECT payload FROM snapshot_candles WHERE snapshot_id=? ORDER BY time', (snapshot_id,))]
        return History(rows, {'source': 'snapshot', 'snapshot_id': snapshot_id,
                             'origin': snapshot['origin'], 'complete': True, 'stale': False,
                             'refreshing': False, 'last_refresh': snapshot['created_at'],
                             'as_of': rows[-1]['time'] if rows else None,
                             'data_revision': 'snapshot:' + snapshot_id})

    def bind_saved_run(self, record, strategy, symbol, snapshot_id, *, engine_revision,
                       observed=None, costs=None):
        key = fingerprint({'strategy': strategy, 'symbol': symbol.upper(), 'record': record})
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO saved_best_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (key, strategy, symbol.upper(), snapshot_id, json.dumps(record.get('parameters', {})),
                        json.dumps(costs or {}), engine_revision, json.dumps(record.get('performance', {})),
                        json.dumps(observed or {}), 'verified' if observed == record.get('performance') else 'captured', self.clock()))
        return key

    def saved_run(self, record, strategy, symbol):
        key = fingerprint({'strategy': strategy, 'symbol': symbol.upper(), 'record': record})
        with self.connection() as db:
            row = db.execute('SELECT r.*,s.origin,s.start AS snapshot_start,s.end AS snapshot_end,s.series_identity FROM saved_best_runs r JOIN candle_snapshots s ON s.id=r.snapshot_id WHERE fingerprint=?', (key,)).fetchone()
        return dict(row) if row else None


_stores = {}
_stores_lock = threading.Lock()


def get_market_store():
    path = str(database_path().resolve())
    with _stores_lock:
        if path not in _stores:
            _stores[path] = MarketDataStore(path)
        return _stores[path]
