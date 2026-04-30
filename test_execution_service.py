#!/usr/bin/env python3
"""
Test script for Trade Execution Service (dry_run mode only — no real orders)
"""

import sys
sys.path.insert(0, "src")

from tradingview_mcp.core.services.execution_service import (
    execute_order,
    _simulate_order,
    _SUPPORTED_BROKERS,
)


def test_execution_service():
    print("\n🧪 Testing Trade Execution Service (Dry-Run Only)\n")
    print("=" * 60)

    # ── Test 1: Dry run order simulation ──
    print("\n✅ Test 1: dry_run order for BTC/USDT on Bitget...")
    result = execute_order(
        symbol="BTC-USD",  # Will be fetched from Yahoo Finance in dry_run
        side="buy",
        capital_usd=500.0,
        stop_loss=64000.0,
        take_profit=72000.0,
        broker="bitget",
        dry_run=True,
    )

    if "error" in result:
        print(f"   ✗ Error: {result['error']}")
        return False

    required_keys = {"order_id", "broker", "mode", "symbol", "side",
                     "quantity", "entry_price", "status", "dry_run"}
    missing = required_keys - set(result.keys())
    if missing:
        print(f"   ✗ Missing keys: {missing}")
        return False

    print(f"   ✓ Order ID: {result['order_id']}")
    print(f"   ✓ Mode: {result['mode']}")
    print(f"   ✓ Symbol: {result['symbol']}")
    print(f"   ✓ Side: {result['side']}")
    print(f"   ✓ Quantity: {result['quantity']}")
    print(f"   ✓ Entry Price: ${result['entry_price']:,.2f}")
    print(f"   ✓ Notional: ${result.get('notional_usd', 0):,.2f}")
    print(f"   ✓ SL: {result.get('stop_loss')}  |  TP: {result.get('take_profit')}")
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Dry run: {result['dry_run']}")

    if result["status"] != "simulated":
        print("   ✗ Expected status 'simulated' for dry run")
        return False

    # ── Test 2: Dry run for Alpaca (stock) ──
    print("\n✅ Test 2: dry_run order for AAPL on Alpaca...")
    result = execute_order(
        symbol="AAPL",
        side="buy",
        capital_usd=1000.0,
        stop_loss=170.0,
        take_profit=210.0,
        broker="alpaca",
        dry_run=True,
    )

    if "error" in result:
        print(f"   ✗ Error: {result['error']}")
        return False

    print(f"   ✓ Order ID: {result['order_id']}")
    print(f"   ✓ Broker: {result['broker']}")
    print(f"   ✓ Symbol: {result['symbol']}")
    print(f"   ✓ Quantity: {result['quantity']} shares")
    print(f"   ✓ Entry Price: ${result['entry_price']:,.2f}")
    print(f"   ✓ Status: {result['status']}")

    # ── Test 3: Position sizing math ──
    print("\n✅ Test 3: Position sizing validation...")
    price = result["entry_price"]
    qty = result["quantity"]
    expected_qty = round(1000.0 / price, 2)
    if abs(qty - expected_qty) < 0.01:
        print(f"   ✓ Qty matches: {qty} ≈ $1000 / ${price:.2f} = {expected_qty}")
    else:
        print(f"   ✗ Qty mismatch: got {qty}, expected {expected_qty}")
        return False

    # ── Test 4: Invalid broker ──
    print("\n✅ Test 4: Invalid broker name...")
    result = execute_order(
        symbol="BTC-USD", side="buy", capital_usd=100.0,
        broker="nonexistent", dry_run=True,
    )
    if "error" in result:
        print(f"   ✓ Correctly returned error: {result['error'][:60]}...")
    else:
        print("   ✗ Should have returned an error for invalid broker")
        return False

    # ── Test 5: Invalid side ──
    print("\n✅ Test 5: Invalid side...")
    result = execute_order(
        symbol="BTC-USD", side="hold", capital_usd=100.0,
        broker="bitget", dry_run=True,
    )
    if "error" in result:
        print(f"   ✓ Correctly returned error: {result['error'][:60]}...")
    else:
        print("   ✗ Should have returned an error for invalid side")
        return False

    # ── Test 6: Zero capital ──
    print("\n✅ Test 6: Zero capital...")
    result = execute_order(
        symbol="BTC-USD", side="buy", capital_usd=0,
        broker="bitget", dry_run=True,
    )
    if "error" in result:
        print(f"   ✓ Correctly returned error: {result['error'][:60]}...")
    else:
        print("   ✗ Should have returned an error for zero capital")
        return False

    # ── Test 7: Supported brokers constant ──
    print("\n✅ Test 7: Supported brokers...")
    print(f"   ✓ Supported: {_SUPPORTED_BROKERS}")
    assert "bitget" in _SUPPORTED_BROKERS
    assert "alpaca" in _SUPPORTED_BROKERS
    print(f"   ✓ Both bitget and alpaca are supported")

    # ── Test 8: Simulate function directly ──
    print("\n✅ Test 8: Direct simulation function...")
    sim = _simulate_order("BTC/USDT", "buy", 0.005, 68000.0, 64000.0, 72000.0, "bitget")
    assert sim["order_id"] == "DRY_RUN_SIM"
    assert sim["status"] == "simulated"
    assert sim["mode"] == "dry_run"
    print(f"   ✓ Simulation output valid")

    print(f"\n{'=' * 60}")
    print("✅ All execution service tests passed!")
    print("=" * 60)

    print("\n📊 Summary:")
    print(f"   - Brokers tested: bitget (crypto), alpaca (stocks)")
    print(f"   - All tests used dry_run=True (no real orders)")
    print(f"   - Position sizing math verified")
    print(f"   - Error handling validated")

    return True


if __name__ == "__main__":
    try:
        success = test_execution_service()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
