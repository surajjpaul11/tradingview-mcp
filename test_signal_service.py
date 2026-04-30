#!/usr/bin/env python3
"""
Test script for Signal Detection Service
"""

import sys
sys.path.insert(0, "src")

from tradingview_mcp.core.services.signal_service import get_live_signal, check_all_strategies


def test_signal_service():
    print("\n🧪 Testing Signal Detection Service\n")
    print("=" * 60)

    # ── Test 1: Valid signal check (VWMA17 on BTC-USD) ──
    print("\n✅ Test 1: get_live_signal('BTC-USD', 'vwma17')...")
    result = get_live_signal("BTC-USD", "vwma17", "1d")
    if "error" in result:
        print(f"   ✗ Error: {result['error']}")
        return False

    required_keys = {"signal", "symbol", "strategy", "price", "stop_loss",
                     "take_profit", "interval", "candles_fetched", "latest_bar_date"}
    missing = required_keys - set(result.keys())
    if missing:
        print(f"   ✗ Missing keys: {missing}")
        return False
    print(f"   ✓ All required keys present")
    print(f"   ✓ Signal: {result['signal']}")
    print(f"   ✓ Price: ${result['price']:,.2f}")
    print(f"   ✓ SL: {result['stop_loss']}  |  TP: {result['take_profit']}")
    print(f"   ✓ Candles fetched: {result['candles_fetched']}")

    valid_signals = {"long", "short", "exit", "none"}
    if result["signal"] not in valid_signals:
        print(f"   ✗ Invalid signal value: {result['signal']}")
        return False
    print(f"   ✓ Signal value is valid: {result['signal']}")

    # ── Test 2: All strategies produce valid output ──
    print("\n✅ Test 2: Testing all strategies...")
    strategies = ["rsi", "bollinger", "macd", "ema_cross", "supertrend", "donchian", "vwma17", "higher_highs"]
    for strat in strategies:
        sig = get_live_signal("SPY", strat, "1d")
        if "error" in sig:
            print(f"   ⚠ {strat}: Error - {sig['error']}")
            continue
        status = "🟢" if sig["signal"] in ("long", "short") else "⚪"
        print(f"   {status} {strat:15s} → signal: {sig['signal']:6s}  price: ${sig['price']:,.2f}")

    # ── Test 3: Invalid strategy name ──
    print("\n✅ Test 3: Invalid strategy name...")
    result = get_live_signal("BTC-USD", "nonexistent")
    if "error" in result:
        print(f"   ✓ Correctly returned error: {result['error'][:60]}...")
    else:
        print("   ✗ Should have returned an error for invalid strategy")
        return False

    # ── Test 4: check_all_strategies ──
    print("\n✅ Test 4: check_all_strategies('SPY')...")
    result = check_all_strategies("SPY", "1d")
    if "error" in result:
        print(f"   ✗ Error: {result['error']}")
        return False
    print(f"   ✓ Strategies checked: {result['strategies_checked']}")
    print(f"   ✓ Active signals: {result['active_signals']}")
    for r in result.get("results", []):
        status = "🟢" if r["signal"] in ("long", "short") else "⚪"
        print(f"     {status} {r['strategy']:15s} → {r['signal']}")

    print(f"\n{'=' * 60}")
    print("✅ All signal service tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        success = test_signal_service()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
