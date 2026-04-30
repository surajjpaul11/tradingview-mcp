"""
Trade Tracking Database — tradingview-mcp

SQLite-based persistent storage for all executed and simulated trades.
Tracks strategy attribution, P&L, and provides data for charting.

Usage:
    from tradingview_mcp.core.services.trade_db import (
        init_db, log_trade, close_trade, get_trade_history,
        get_pnl_summary, get_equity_curve,
    )
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ─── Database Path ────────────────────────────────────────────────────────────

def _get_db_path() -> str:
    """Return the path to the SQLite database file, creating dirs if needed."""
    # Look for project root by checking for pyproject.toml
    # Walk up from this file's location
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists():
            db_dir = parent / "data"
            db_dir.mkdir(exist_ok=True)
            return str(db_dir / "trades.db")
    # Fallback to cwd
    db_dir = Path.cwd() / "data"
    db_dir.mkdir(exist_ok=True)
    return str(db_dir / "trades.db")


def _get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Get a connection to the database."""
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─── Schema ───────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT UNIQUE NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    broker          TEXT NOT NULL,
    quantity        REAL NOT NULL,
    entry_price     REAL NOT NULL,
    stop_loss       REAL,
    take_profit     REAL,
    capital_usd     REAL NOT NULL,
    mode            TEXT NOT NULL,
    order_id        TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    interval        TEXT DEFAULT '1d',
    signal_price    REAL,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trade_exits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT NOT NULL REFERENCES trades(trade_id),
    exit_price      REAL NOT NULL,
    exit_reason     TEXT,
    pnl_usd         REAL NOT NULL,
    pnl_pct         REAL NOT NULL,
    holding_seconds INTEGER,
    fees_usd        REAL DEFAULT 0,
    closed_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS strategy_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy        TEXT NOT NULL,
    broker          TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    cumulative_pnl  REAL NOT NULL DEFAULT 0,
    total_trades    INTEGER NOT NULL DEFAULT 0,
    winning_trades  INTEGER NOT NULL DEFAULT 0,
    losing_trades   INTEGER NOT NULL DEFAULT 0,
    win_rate_pct    REAL,
    snapshot_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_broker ON trades(broker);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at);
CREATE INDEX IF NOT EXISTS idx_trade_exits_trade_id ON trade_exits(trade_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_strategy ON strategy_snapshots(strategy);
"""


def init_db(db_path: Optional[str] = None) -> None:
    """Create all tables and indexes if they don't exist."""
    conn = _get_connection(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ─── Trade Logging ────────────────────────────────────────────────────────────

def log_trade(
    symbol: str,
    side: str,
    strategy: str,
    broker: str,
    quantity: float,
    entry_price: float,
    capital_usd: float,
    mode: str = "dry_run",
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    order_id: Optional[str] = None,
    interval: str = "1d",
    signal_price: Optional[float] = None,
    notes: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """
    Log a new trade to the database.

    Returns the generated trade_id (UUID).
    """
    trade_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO trades
               (trade_id, symbol, side, strategy, broker, quantity, entry_price,
                stop_loss, take_profit, capital_usd, mode, order_id, status,
                interval, signal_price, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)""",
            (trade_id, symbol, side, strategy, broker, quantity, entry_price,
             stop_loss, take_profit, capital_usd, mode, order_id,
             interval, signal_price, notes, now, now),
        )
        conn.commit()
    finally:
        conn.close()

    return trade_id


def close_trade(
    trade_id: str,
    exit_price: float,
    exit_reason: str = "manual",
    fees_usd: float = 0.0,
    db_path: Optional[str] = None,
) -> dict:
    """
    Close an existing trade — computes P&L and updates status.

    Returns the computed P&L dict.
    """
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM trades WHERE trade_id = ?", (trade_id,)
        ).fetchone()

        if not row:
            return {"error": f"Trade '{trade_id}' not found"}
        if row["status"] == "closed":
            return {"error": f"Trade '{trade_id}' is already closed"}

        entry_price = row["entry_price"]
        quantity = row["quantity"]
        side = row["side"]
        capital_usd = row["capital_usd"]

        # Calculate P&L
        if side == "buy":
            pnl_usd = (exit_price - entry_price) * quantity - fees_usd
        else:  # sell / short
            pnl_usd = (entry_price - exit_price) * quantity - fees_usd

        pnl_pct = (pnl_usd / capital_usd) * 100 if capital_usd > 0 else 0.0

        # Calculate holding duration
        try:
            created = datetime.fromisoformat(row["created_at"])
            now = datetime.now(timezone.utc)
            holding_seconds = int((now - created).total_seconds())
        except Exception:
            holding_seconds = None

        now_str = datetime.now(timezone.utc).isoformat()

        # Insert exit record
        conn.execute(
            """INSERT INTO trade_exits
               (trade_id, exit_price, exit_reason, pnl_usd, pnl_pct,
                holding_seconds, fees_usd, closed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (trade_id, exit_price, exit_reason, round(pnl_usd, 4),
             round(pnl_pct, 4), holding_seconds, fees_usd, now_str),
        )

        # Update trade status
        conn.execute(
            "UPDATE trades SET status = 'closed', updated_at = ? WHERE trade_id = ?",
            (now_str, trade_id),
        )

        # Update strategy snapshot
        _update_snapshot(conn, row["strategy"], row["broker"], row["symbol"],
                         pnl_usd, pnl_pct > 0)

        conn.commit()

        return {
            "trade_id": trade_id,
            "symbol": row["symbol"],
            "side": side,
            "strategy": row["strategy"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 2),
            "holding_seconds": holding_seconds,
            "status": "closed",
        }
    finally:
        conn.close()


def _update_snapshot(
    conn: sqlite3.Connection,
    strategy: str,
    broker: str,
    symbol: str,
    pnl_usd: float,
    is_winner: bool,
) -> None:
    """Update or create a strategy snapshot after closing a trade."""
    row = conn.execute(
        """SELECT * FROM strategy_snapshots
           WHERE strategy = ? AND broker = ? AND symbol = ?
           ORDER BY snapshot_at DESC LIMIT 1""",
        (strategy, broker, symbol),
    ).fetchone()

    now_str = datetime.now(timezone.utc).isoformat()

    if row:
        cum_pnl = row["cumulative_pnl"] + pnl_usd
        total = row["total_trades"] + 1
        wins = row["winning_trades"] + (1 if is_winner else 0)
        losses = row["losing_trades"] + (0 if is_winner else 1)
        wr = round(wins / total * 100, 1) if total > 0 else 0
    else:
        cum_pnl = pnl_usd
        total = 1
        wins = 1 if is_winner else 0
        losses = 0 if is_winner else 1
        wr = 100.0 if is_winner else 0.0

    conn.execute(
        """INSERT INTO strategy_snapshots
           (strategy, broker, symbol, cumulative_pnl, total_trades,
            winning_trades, losing_trades, win_rate_pct, snapshot_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (strategy, broker, symbol, round(cum_pnl, 2), total,
         wins, losses, wr, now_str),
    )


# ─── Query Functions ──────────────────────────────────────────────────────────

def get_trade_history(
    strategy: Optional[str] = None,
    symbol: Optional[str] = None,
    broker: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> list[dict]:
    """
    Query trade history with optional filters.
    Returns most recent trades first.
    """
    conn = _get_connection(db_path)
    try:
        query = """
            SELECT t.*,
                   te.exit_price, te.exit_reason, te.pnl_usd, te.pnl_pct,
                   te.holding_seconds, te.fees_usd, te.closed_at
            FROM trades t
            LEFT JOIN trade_exits te ON t.trade_id = te.trade_id
            WHERE 1=1
        """
        params: list = []

        if strategy:
            query += " AND t.strategy = ?"
            params.append(strategy.lower().strip())
        if symbol:
            query += " AND t.symbol = ?"
            params.append(symbol.upper().strip())
        if broker:
            query += " AND t.broker = ?"
            params.append(broker.lower().strip())
        if status:
            query += " AND t.status = ?"
            params.append(status.lower().strip())

        query += " ORDER BY t.created_at DESC LIMIT ?"
        params.append(min(limit, 500))

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_pnl_summary(
    strategy: Optional[str] = None,
    symbol: Optional[str] = None,
    broker: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict:
    """
    Aggregated P&L summary. Filters by strategy/symbol/broker if provided.
    Designed for dashboards and reports.
    """
    conn = _get_connection(db_path)
    try:
        where_parts = ["t.status = 'closed'"]
        params: list = []

        if strategy:
            where_parts.append("t.strategy = ?")
            params.append(strategy.lower().strip())
        if symbol:
            where_parts.append("t.symbol = ?")
            params.append(symbol.upper().strip())
        if broker:
            where_parts.append("t.broker = ?")
            params.append(broker.lower().strip())

        where_clause = " AND ".join(where_parts)

        row = conn.execute(f"""
            SELECT
                COUNT(*) as total_trades,
                COALESCE(SUM(te.pnl_usd), 0) as total_pnl_usd,
                COALESCE(AVG(te.pnl_pct), 0) as avg_pnl_pct,
                SUM(CASE WHEN te.pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN te.pnl_usd <= 0 THEN 1 ELSE 0 END) as losing_trades,
                MAX(te.pnl_usd) as best_trade_usd,
                MIN(te.pnl_usd) as worst_trade_usd,
                MAX(te.pnl_pct) as best_trade_pct,
                MIN(te.pnl_pct) as worst_trade_pct,
                COALESCE(SUM(t.capital_usd), 0) as total_capital_deployed,
                COALESCE(SUM(te.fees_usd), 0) as total_fees_usd
            FROM trades t
            JOIN trade_exits te ON t.trade_id = te.trade_id
            WHERE {where_clause}
        """, params).fetchone()

        total = row["total_trades"] or 0
        wins = row["winning_trades"] or 0

        # Strategy breakdown if no strategy filter
        strategies = []
        if not strategy:
            strat_rows = conn.execute(f"""
                SELECT t.strategy,
                       COUNT(*) as trades,
                       COALESCE(SUM(te.pnl_usd), 0) as pnl_usd,
                       COALESCE(AVG(te.pnl_pct), 0) as avg_pnl_pct
                FROM trades t
                JOIN trade_exits te ON t.trade_id = te.trade_id
                WHERE {where_clause}
                GROUP BY t.strategy
                ORDER BY pnl_usd DESC
            """, params).fetchall()
            strategies = [dict(r) for r in strat_rows]

        return {
            "total_trades": total,
            "total_pnl_usd": round(row["total_pnl_usd"], 2),
            "avg_pnl_pct": round(row["avg_pnl_pct"], 2),
            "win_rate_pct": round(wins / total * 100, 1) if total > 0 else 0,
            "winning_trades": wins,
            "losing_trades": row["losing_trades"] or 0,
            "best_trade_usd": round(row["best_trade_usd"], 2) if row["best_trade_usd"] else None,
            "worst_trade_usd": round(row["worst_trade_usd"], 2) if row["worst_trade_usd"] else None,
            "best_trade_pct": round(row["best_trade_pct"], 2) if row["best_trade_pct"] else None,
            "worst_trade_pct": round(row["worst_trade_pct"], 2) if row["worst_trade_pct"] else None,
            "total_capital_deployed": round(row["total_capital_deployed"], 2),
            "total_fees_usd": round(row["total_fees_usd"], 2),
            "strategy_breakdown": strategies,
            "filters": {
                "strategy": strategy,
                "symbol": symbol,
                "broker": broker,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


def get_equity_curve(
    strategy: Optional[str] = None,
    symbol: Optional[str] = None,
    broker: Optional[str] = None,
    db_path: Optional[str] = None,
) -> list[dict]:
    """
    Running cumulative P&L over time — ready for charting.
    Returns one data point per closed trade, ordered chronologically.
    """
    conn = _get_connection(db_path)
    try:
        where_parts = ["t.status = 'closed'"]
        params: list = []

        if strategy:
            where_parts.append("t.strategy = ?")
            params.append(strategy.lower().strip())
        if symbol:
            where_parts.append("t.symbol = ?")
            params.append(symbol.upper().strip())
        if broker:
            where_parts.append("t.broker = ?")
            params.append(broker.lower().strip())

        where_clause = " AND ".join(where_parts)

        rows = conn.execute(f"""
            SELECT te.closed_at, te.pnl_usd, te.pnl_pct,
                   t.symbol, t.strategy, t.side
            FROM trades t
            JOIN trade_exits te ON t.trade_id = te.trade_id
            WHERE {where_clause}
            ORDER BY te.closed_at ASC
        """, params).fetchall()

        curve = []
        cumulative_pnl = 0.0
        for r in rows:
            cumulative_pnl += r["pnl_usd"]
            curve.append({
                "date": r["closed_at"],
                "pnl_usd": round(r["pnl_usd"], 2),
                "cumulative_pnl_usd": round(cumulative_pnl, 2),
                "pnl_pct": round(r["pnl_pct"], 2),
                "symbol": r["symbol"],
                "strategy": r["strategy"],
                "side": r["side"],
            })

        return curve
    finally:
        conn.close()


# ─── Auto-init on import ─────────────────────────────────────────────────────

try:
    init_db()
except Exception:
    pass  # Will be created on first use
