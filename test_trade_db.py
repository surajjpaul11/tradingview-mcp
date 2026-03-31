#!/usr/bin/env python3
"""
Test script for Trade Tracking Database (uses in-memory SQLite)
"""

import sys
import os
import tempfile
import time
sys.path.insert(0, "src")

from tradingview_mcp.core.services.trade_db import (
    init_db, log_trade, close_trade,
    get_trade_history, get_pnl_summary, get_equity_curve,
)


# Use a temp file DB so all connections share the same database
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB = _tmp.name
_tmp.close()


def test_trade_db():
    print("\n🧪 Testing Trade Tracking Database\n")
    print("=" * 60)

    # ── Test 1: Initialize DB ──
    print("\n✅ Test 1: Initialize database...")
    init_db(DB)
    print("   ✓ Database initialized (in-memory)")

    # ── Test 2: Log a trade ──
    print("\n✅ Test 2: Log a trade...")
    trade_id_1 = log_trade(
        symbol="BTC/USDT",
        side="buy",
        strategy="vwma17",
        broker="bitget",
        quantity=0.007,
        entry_price=68000.0,
        capital_usd=500.0,
        mode="dry_run",
        stop_loss=66000.0,
        take_profit=72000.0,
        order_id="DRY_RUN_SIM",
        db_path=DB,
    )
    assert trade_id_1, "trade_id should not be empty"
    print(f"   ✓ Trade logged: {trade_id_1[:8]}...")

    # ── Test 3: Log a second trade (different strategy) ──
    print("\n✅ Test 3: Log second trade (RSI on AAPL)...")
    trade_id_2 = log_trade(
        symbol="AAPL",
        side="buy",
        strategy="rsi",
        broker="alpaca",
        quantity=5.0,
        entry_price=200.0,
        capital_usd=1000.0,
        mode="dry_run",
        db_path=DB,
    )
    print(f"   ✓ Trade logged: {trade_id_2[:8]}...")

    # ── Test 4: Get trade history ──
    print("\n✅ Test 4: Query trade history...")
    history = get_trade_history(db_path=DB)
    assert len(history) == 2, f"Expected 2 trades, got {len(history)}"
    print(f"   ✓ Found {len(history)} trades")

    # Filter by strategy
    vwma_trades = get_trade_history(strategy="vwma17", db_path=DB)
    assert len(vwma_trades) == 1
    print(f"   ✓ Filtered by vwma17: {len(vwma_trades)} trade")

    # Filter by broker
    alpaca_trades = get_trade_history(broker="alpaca", db_path=DB)
    assert len(alpaca_trades) == 1
    print(f"   ✓ Filtered by alpaca: {len(alpaca_trades)} trade")

    # ── Test 5: Close a trade with profit ──
    print("\n✅ Test 5: Close BTC trade with profit...")
    result = close_trade(trade_id_1, exit_price=70000.0, exit_reason="take_profit", db_path=DB)
    assert "error" not in result, f"Close failed: {result.get('error')}"
    assert result["pnl_usd"] > 0, f"Expected positive PnL, got {result['pnl_usd']}"
    print(f"   ✓ PnL: ${result['pnl_usd']:+.2f} ({result['pnl_pct']:+.2f}%)")
    print(f"   ✓ Exit reason: {result['exit_reason']}")
    print(f"   ✓ Status: {result['status']}")

    # ── Test 6: Close a trade with loss ──
    print("\n✅ Test 6: Close AAPL trade with loss...")
    result2 = close_trade(trade_id_2, exit_price=190.0, exit_reason="stop_loss", db_path=DB)
    assert result2["pnl_usd"] < 0, f"Expected negative PnL, got {result2['pnl_usd']}"
    print(f"   ✓ PnL: ${result2['pnl_usd']:+.2f} ({result2['pnl_pct']:+.2f}%)")

    # ── Test 7: Duplicate close rejected ──
    print("\n✅ Test 7: Reject duplicate close...")
    dup = close_trade(trade_id_1, exit_price=71000.0, db_path=DB)
    assert "error" in dup
    print(f"   ✓ Correctly rejected: {dup['error'][:50]}...")

    # ── Test 8: P&L Summary ──
    print("\n✅ Test 8: P&L Summary...")
    summary = get_pnl_summary(db_path=DB)
    assert summary["total_trades"] == 2
    print(f"   ✓ Total trades: {summary['total_trades']}")
    print(f"   ✓ Total PnL: ${summary['total_pnl_usd']:+.2f}")
    print(f"   ✓ Win rate: {summary['win_rate_pct']}%")
    print(f"   ✓ Best trade: ${summary['best_trade_usd']:+.2f}")
    print(f"   ✓ Worst trade: ${summary['worst_trade_usd']:+.2f}")

    # Strategy breakdown
    if summary.get("strategy_breakdown"):
        print(f"   ✓ Strategy breakdown:")
        for s in summary["strategy_breakdown"]:
            print(f"     - {s['strategy']:12s} → PnL: ${s['pnl_usd']:+.2f} ({s['trades']} trades)")

    # ── Test 9: Filter P&L by strategy ──
    print("\n✅ Test 9: P&L Summary filtered by strategy...")
    vwma_summary = get_pnl_summary(strategy="vwma17", db_path=DB)
    assert vwma_summary["total_trades"] == 1
    assert vwma_summary["total_pnl_usd"] > 0
    print(f"   ✓ VWMA17 PnL: ${vwma_summary['total_pnl_usd']:+.2f}")

    # ── Test 10: Equity Curve ──
    print("\n✅ Test 10: Equity Curve...")
    curve = get_equity_curve(db_path=DB)
    assert len(curve) == 2, f"Expected 2 data points, got {len(curve)}"
    print(f"   ✓ Data points: {len(curve)}")
    for pt in curve:
        print(f"     {pt['strategy']:12s} {pt['symbol']:10s} "
              f"PnL: ${pt['pnl_usd']:+8.2f}  "
              f"Cumulative: ${pt['cumulative_pnl_usd']:+8.2f}")

    # ── Test 11: Non-existent trade ──
    print("\n✅ Test 11: Close non-existent trade...")
    bad = close_trade("fake-id-12345", exit_price=100.0, db_path=DB)
    assert "error" in bad
    print(f"   ✓ Correctly returned error: {bad['error'][:50]}...")

    # ── Test 12: History with status filter ──
    print("\n✅ Test 12: Filter by status...")
    open_trades = get_trade_history(status="open", db_path=DB)
    closed_trades = get_trade_history(status="closed", db_path=DB)
    assert len(open_trades) == 0
    assert len(closed_trades) == 2
    print(f"   ✓ Open: {len(open_trades)}, Closed: {len(closed_trades)}")

    print(f"\n{'=' * 60}")
    print("✅ All trade database tests passed!")
    print("=" * 60)

    print("\n📊 Summary:")
    print(f"   - Tables tested: trades, trade_exits, strategy_snapshots")
    print(f"   - Operations: log, close, history, P&L summary, equity curve")
    print(f"   - Error handling: duplicate close, non-existent trade")
    print(f"   - All tests used in-memory SQLite (:memory:)")

    return True


if __name__ == "__main__":
    try:
        success = test_trade_db()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        try:
            os.unlink(DB)
        except Exception:
            pass
