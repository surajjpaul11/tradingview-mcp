"""
Trade Execution Service — tradingview-mcp

Unified order execution via broker adapter pattern.
Supports Bitget (crypto via ccxt) and Alpaca (stocks via alpaca-trade-api).

Usage:
    from tradingview_mcp.core.services.execution_service import execute_order
    result = execute_order("BTC/USDT", "buy", 500.0, 64000, 72000, broker="bitget")
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from tradingview_mcp.core.services.trade_db import (
    init_db as _init_db,
    log_trade as _log_trade,
    close_trade as _close_trade,
    get_trade_history as _get_trade_history,
)


# ─── Broker Adapter Protocol ─────────────────────────────────────────────────

class BrokerAdapter(ABC):
    """Abstract interface for all broker integrations."""

    @abstractmethod
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        """Place a market order with optional SL/TP bracket."""
        ...

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """Get the current market price for position sizing."""
        ...

    @abstractmethod
    def get_account_balance(self) -> dict:
        """Get account balance info."""
        ...

    @property
    @abstractmethod
    def broker_name(self) -> str:
        ...


# ─── Bitget Adapter (Crypto via ccxt) ────────────────────────────────────────

class BitgetAdapter(BrokerAdapter):
    """Bitget exchange adapter using ccxt."""

    def __init__(self):
        try:
            import ccxt
        except ImportError:
            raise ImportError(
                "ccxt is required for Bitget trading. "
                "Install with: pip install 'ccxt>=4.3'"
            )

        api_key = os.environ.get("BITGET_API_KEY", "")
        api_secret = os.environ.get("BITGET_API_SECRET", "")
        passphrase = os.environ.get("BITGET_PASSPHRASE", "")
        sandbox = os.environ.get("BITGET_SANDBOX", "true").lower() == "true"

        if not api_key or api_key == "your_key":
            raise ValueError(
                "BITGET_API_KEY not configured. "
                "Set it in your .env file. See .env.example for details."
            )

        self._exchange = ccxt.bitget({
            "apiKey": api_key,
            "secret": api_secret,
            "password": passphrase,
            "sandbox": sandbox,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })

        self._sandbox = sandbox

    def market_status(self) -> dict:
        """{"is_open": bool, "next_open": str|None, "next_close": str|None}.

        Brokers that trade around the clock report is_open=True.
        """
        return {"is_open": True, "next_open": None, "next_close": None}

    def get_order(self, order_id: str) -> dict:
        """Current state of a previously placed order (status/filled price/qty)."""
        return {"order_id": order_id, "status": "unknown"}

    def close_position(self, symbol: str) -> dict:
        """Flatten the whole position in `symbol` at market, cancelling its open orders."""
        raise NotImplementedError(f"{self.broker_name} adapter cannot close positions yet")

    @property
    def broker_name(self) -> str:
        return "bitget"

    def get_current_price(self, symbol: str) -> float:
        ticker = self._exchange.fetch_ticker(symbol)
        return float(ticker["last"])

    def get_account_balance(self) -> dict:
        balance = self._exchange.fetch_balance()
        return {
            "total_usd": balance.get("total", {}).get("USDT", 0),
            "free_usd": balance.get("free", {}).get("USDT", 0),
            "broker": "bitget",
            "sandbox": self._sandbox,
        }

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        # The spot adapter has no linked OCO/bracket implementation. Reject
        # protected orders before submitting an entry that might be left bare.
        if stop_loss is not None or take_profit is not None:
            raise ValueError("Protected Bitget spot orders require a linked OCO implementation")

        # Place the main market order
        order = self._exchange.create_order(
            symbol=symbol,
            type="market",
            side=side,
            amount=quantity,
        )

        return {
            "order_id": order.get("id"),
            "status": order.get("status", "unknown"),
            "filled_price": order.get("average") or order.get("price"),
            "filled_quantity": order.get("filled", quantity),
            "sl_order": None,
            "tp_order": None,
            "raw": order,
        }


# ─── Alpaca Adapter (Stocks via alpaca-trade-api) ────────────────────────────

class AlpacaAdapter(BrokerAdapter):
    """Alpaca Markets adapter for stocks and ETFs."""

    def __init__(self):
        try:
            import alpaca_trade_api as tradeapi
        except ImportError:
            raise ImportError(
                "alpaca-trade-api is required for Alpaca trading. "
                "Install with: pip install 'alpaca-trade-api>=3.3'"
            )

        api_key = os.environ.get("ALPACA_API_KEY", "")
        api_secret = os.environ.get("ALPACA_API_SECRET", "")
        paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

        if not api_key or api_key == "your_key":
            raise ValueError(
                "ALPACA_API_KEY not configured. "
                "Set it in your .env file. See .env.example for details."
            )

        base_url = (
            "https://paper-api.alpaca.markets"
            if paper
            else "https://api.alpaca.markets"
        )

        self._api = tradeapi.REST(api_key, api_secret, base_url, api_version="v2")
        self._paper = paper

    @property
    def broker_name(self) -> str:
        return "alpaca"

    def get_current_price(self, symbol: str) -> float:
        # Get the latest trade price
        quote = self._api.get_latest_trade(symbol)
        return float(quote.price)

    def get_account_balance(self) -> dict:
        account = self._api.get_account()
        return {
            "total_usd": float(account.equity),
            "free_usd": float(account.buying_power),
            "broker": "alpaca",
            "paper": self._paper,
        }

    def market_status(self) -> dict:
        clock = self._api.get_clock()
        return {
            "is_open": bool(clock.is_open),
            "next_open": str(clock.next_open),
            "next_close": str(clock.next_close),
        }

    def get_order(self, order_id: str) -> dict:
        o = self._api.get_order(order_id)
        return {
            "order_id": o.id,
            "status": o.status,
            "filled_price": float(o.filled_avg_price) if o.filled_avg_price else None,
            "filled_quantity": float(o.filled_qty) if o.filled_qty else 0.0,
            "symbol": o.symbol,
            "side": o.side,
        }

    def _await_fill(self, order_id: str, timeout_s: float = 5.0, interval_s: float = 0.5) -> dict:
        """Poll briefly for a terminal state so the recorded price is the real fill."""
        deadline = time.monotonic() + timeout_s
        state = self.get_order(order_id)
        while time.monotonic() < deadline and state.get("status") not in (
                "filled", "canceled", "expired", "rejected"):
            time.sleep(interval_s)
            state = self.get_order(order_id)
        return state

    def get_position(self, symbol: str) -> Optional[dict]:
        try:
            p = self._api.get_position(symbol)
        except Exception:
            return None
        return {
            "symbol": p.symbol,
            "quantity": float(p.qty),
            "avg_entry_price": float(p.avg_entry_price),
            "market_value_usd": float(p.market_value),
            "unrealized_pl_usd": float(p.unrealized_pl),
            "unrealized_pl_pct": float(p.unrealized_plpc) * 100,
        }

    def close_position(self, symbol: str) -> dict:
        """Cancel the symbol's resting orders (stop/target legs), then flatten at market."""
        position = self.get_position(symbol)
        if position is None:
            return {"error": f"No open Alpaca position in {symbol}"}
        for o in self._api.list_orders(status="open", symbols=[symbol]):
            try:
                self._api.cancel_order(o.id)
            except Exception:
                pass
        order = self._api.close_position(symbol)
        state = self._await_fill(order.id)
        return {
            "order_id": order.id,
            "symbol": symbol,
            "quantity_closed": position["quantity"],
            "status": state.get("status", order.status),
            "exit_price": state.get("filled_price"),
            "broker": "alpaca",
        }

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        await_fill: bool = True,
    ) -> dict:
        order_params = {
            "symbol": symbol,
            "qty": quantity,
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }

        # Alpaca requires both legs for a bracket; a single leg uses OTO.
        if stop_loss is not None or take_profit is not None:
            order_params["order_class"] = (
                "bracket" if stop_loss is not None and take_profit is not None else "oto"
            )
            if stop_loss is not None:
                order_params["stop_loss"] = {"stop_price": str(round(stop_loss, 2))}
            if take_profit is not None:
                order_params["take_profit"] = {"limit_price": str(round(take_profit, 2))}

        order = self._api.submit_order(**order_params)
        state = self._await_fill(order.id) if await_fill else self.get_order(order.id)

        return {
            "order_id": order.id,
            "status": state.get("status", order.status),
            "filled_price": state.get("filled_price"),
            "filled_quantity": state.get("filled_quantity") or quantity,
            "sl_order": "included_in_bracket" if stop_loss else None,
            "tp_order": "included_in_bracket" if take_profit else None,
        }


# ─── Adapter Factory ─────────────────────────────────────────────────────────

_SUPPORTED_BROKERS = {"bitget", "alpaca"}


def _get_adapter(broker: str) -> BrokerAdapter:
    """Factory: return the correct broker adapter."""
    broker = broker.lower().strip()
    if broker == "bitget":
        return BitgetAdapter()
    elif broker == "alpaca":
        return AlpacaAdapter()
    else:
        raise ValueError(f"Unsupported broker '{broker}'. Choose: {', '.join(_SUPPORTED_BROKERS)}")


# ─── Dry Run Simulator ───────────────────────────────────────────────────────

def _simulate_order(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    stop_loss: Optional[float],
    take_profit: Optional[float],
    broker: str,
) -> dict:
    """Simulate an order for dry_run mode — no exchange interaction."""
    return {
        "order_id": "DRY_RUN_SIM",
        "broker": broker,
        "mode": "dry_run",
        "symbol": symbol,
        "side": side,
        "quantity": round(quantity, 8),
        "entry_price": round(price, 4),
        "stop_loss": round(stop_loss, 4) if stop_loss else None,
        "take_profit": round(take_profit, 4) if take_profit else None,
        "notional_usd": round(quantity * price, 2),
        "status": "simulated",
        "message": "No real order placed. Set dry_run=False to execute live.",
    }


def _alpaca_quantity(capital_usd: float, price: float, protected: bool) -> tuple[float, Optional[str]]:
    """
    Size an Alpaca order. Alpaca rejects fractional quantities on bracket/OTO orders,
    so an order carrying a stop or target is rounded DOWN to whole shares.
    Returns (quantity, error).
    """
    raw = capital_usd / price
    if protected:
        qty = float(int(raw))
        if qty < 1:
            return 0.0, (f"capital_usd ${capital_usd:,.2f} buys {raw:.2f} shares at ${price:,.2f}; "
                         f"Alpaca needs whole shares when a stop-loss or take-profit is attached. "
                         f"Raise capital_usd to at least ${price:,.2f}, or drop the stop/target "
                         f"to trade fractionally.")
        return qty, None
    return round(raw, 2), None


# ─── Public API ───────────────────────────────────────────────────────────────

def execute_order(
    symbol: str,
    side: str,
    capital_usd: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    broker: str = "bitget",
    dry_run: bool = True,
    strategy: str = "manual",
    allow_closed_market: bool = False,
) -> dict:
    """
    Execute a trade on the specified broker.

    Args:
        symbol:       Trading pair (e.g. "BTC/USDT" for Bitget, "AAPL" for Alpaca)
        side:         "buy" or "sell"
        capital_usd:  Dollar amount to deploy
        stop_loss:    Stop-loss price level
        take_profit:  Take-profit price level
        broker:       "bitget" or "alpaca"
        dry_run:      If True, simulate without placing a real order
        allow_closed_market: If True, queue the order while the market is closed
                      instead of refusing it (Alpaca only)

    Returns:
        Order confirmation dict with:
          order_id, broker, symbol, side, quantity, entry_price,
          stop_loss, take_profit, status, dry_run
    """
    broker = broker.lower().strip()
    side = side.lower().strip()

    if broker not in _SUPPORTED_BROKERS:
        return {"error": f"Unsupported broker '{broker}'. Choose: {', '.join(_SUPPORTED_BROKERS)}"}
    if side not in ("buy", "sell"):
        return {"error": f"Invalid side '{side}'. Choose: buy or sell"}
    if capital_usd <= 0:
        return {"error": "capital_usd must be positive"}
    if not dry_run and broker == "bitget" and (stop_loss is not None or take_profit is not None):
        return {"error": "Protected Bitget spot orders require a linked OCO implementation"}

    # ── Get current price for position sizing ──
    if dry_run:
        # In dry run, fetch price from Yahoo Finance to avoid needing broker creds
        try:
            from tradingview_mcp.core.services.backtest_service import _fetch_ohlcv
            # Convert symbol format: BTC/USDT → BTC-USD for Yahoo
            yf_symbol = symbol.replace("/USDT", "-USD").replace("/USD", "-USD")
            candles = _fetch_ohlcv(yf_symbol, "5d", "1d")
            price = candles[-1]["close"]
        except Exception as e:
            return {"error": f"Failed to fetch price for '{symbol}': {e}"}
    else:
        try:
            adapter = _get_adapter(broker)
        except Exception as e:
            return {"error": f"Failed to connect to {broker}: {e}"}

        # ── Market-hours gate: a closed market queues the order and the price is stale ──
        try:
            market = adapter.market_status()
        except Exception as e:
            return {"error": f"Failed to read {broker} market status: {e}"}
        market_open = market["is_open"]
        if not market_open and not allow_closed_market:
            return {
                "error": f"{broker} market is closed — no order placed.",
                "market": market,
                "hint": "Pass allow_closed_market=True to queue it for the next session.",
            }

        try:
            price = adapter.get_current_price(symbol)
        except Exception as e:
            return {"error": f"Failed to fetch {broker} price for '{symbol}': {e}"}

    # ── Calculate position size ──
    if broker == "alpaca":
        protected = stop_loss is not None or take_profit is not None
        quantity, size_error = _alpaca_quantity(capital_usd, price, protected)
        if size_error:
            return {"error": size_error}
    else:
        quantity = round(capital_usd / price, 8)  # Crypto: 8 decimal precision

    # ── Execute or simulate ──
    if dry_run:
        result = _simulate_order(symbol, side, quantity, price, stop_loss, take_profit, broker)
    else:
        try:
            adapter = _get_adapter(broker)
            try:
                result = adapter.place_market_order(symbol, side, quantity, stop_loss,
                                                    take_profit, await_fill=market_open)
            except TypeError:  # adapters without the await_fill parameter (Bitget)
                result = adapter.place_market_order(symbol, side, quantity, stop_loss, take_profit)
            result["broker"] = broker
            result["mode"] = "live"
            result["entry_price"] = result.get("filled_price") or price
            result["quantity"] = result.get("filled_quantity") or quantity
            result["quoted_price"] = price
            if result.get("filled_price") is None:
                if not market_open:
                    result["queued_for_next_open"] = market.get("next_open")
                    result["note"] = (
                        f"Market closed — order accepted and queued by {broker} for the next "
                        f"session (opens {market.get('next_open')}). entry_price is the pre-trade "
                        f"quote; run sync_broker_trades after the open to record the actual fill.")
                else:
                    result["note"] = ("Order not filled yet — entry_price is the pre-trade quote. "
                                      "Run sync_broker_trades to record the actual fill.")
        except Exception as e:
            return {"error": f"Order execution failed: {e}"}

    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    result["dry_run"] = dry_run

    # ── Auto-log to trade database ──
    try:
        trade_id = _log_trade(
            symbol=symbol,
            side=side,
            strategy=strategy,
            broker=broker,
            quantity=quantity,
            entry_price=result.get("entry_price", price),
            capital_usd=capital_usd,
            mode="dry_run" if dry_run else "live",
            stop_loss=stop_loss,
            take_profit=take_profit,
            order_id=result.get("order_id"),
        )
        result["trade_id"] = trade_id
    except Exception:
        result["trade_id"] = None  # DB logging failed but order succeeded

    return result


# ─── Closing and reconciliation ───────────────────────────────────────────────

def close_position(symbol: str, broker: str = "alpaca", reason: str = "manual",
                   trade_id: Optional[str] = None, dry_run: bool = True) -> dict:
    """
    Flatten a real broker position AND record the exit in trades.db.

    `close_open_trade` only writes the database row; this places the closing order.
    With dry_run=True the position is reported but nothing is sold.
    """
    broker = broker.lower().strip()
    symbol = symbol.upper().strip()
    if broker not in _SUPPORTED_BROKERS:
        return {"error": f"Unsupported broker '{broker}'. Choose: {', '.join(_SUPPORTED_BROKERS)}"}

    try:
        adapter = _get_adapter(broker)
    except Exception as e:
        return {"error": f"Failed to connect to {broker}: {e}"}

    position = getattr(adapter, "get_position", lambda _s: None)(symbol)
    if position is None:
        return {"error": f"No open {broker} position in {symbol}", "dry_run": dry_run}

    if dry_run:
        return {"dry_run": True, "symbol": symbol, "broker": broker, "position": position,
                "message": "No order placed. Set dry_run=False to close this position."}

    try:
        market = adapter.market_status()
    except Exception as e:
        return {"error": f"Failed to read {broker} market status: {e}"}
    if not market["is_open"]:
        return {"error": f"{broker} market is closed — position not closed.", "market": market}

    result = adapter.close_position(symbol)
    if "error" in result:
        return result
    result["dry_run"] = False
    result["timestamp"] = datetime.now(timezone.utc).isoformat()

    exit_price = result.get("exit_price")
    target_id = trade_id or _find_open_trade_id(symbol, broker)
    if target_id and exit_price:
        result["trade_record"] = _close_trade(target_id, float(exit_price), reason)
        result["trade_id"] = target_id
    elif target_id:
        result["trade_record"] = {"warning": "Closing order placed but no fill price yet; "
                                             "run sync_broker_trades to record the exit."}
    return result


def _find_open_trade_id(symbol: str, broker: str) -> Optional[str]:
    """Most recent open trade in trades.db for this symbol+broker."""
    _init_db()
    for t in _get_trade_history(symbol=symbol, broker=broker, status="open", limit=50):
        return t.get("trade_id")
    return None


def sync_broker_trades(broker: str = "alpaca", record_exits: bool = True) -> dict:
    """
    Reconcile open trades.db rows against the broker.

    Fixes two blind spots: entries still holding a pre-trade quote instead of the real
    fill, and positions closed outside this app (a stop/target that triggered, or a
    manual sale in the broker UI) that the database still shows as open.
    """
    broker = broker.lower().strip()
    if broker not in _SUPPORTED_BROKERS:
        return {"error": f"Unsupported broker '{broker}'. Choose: {', '.join(_SUPPORTED_BROKERS)}"}
    _init_db()
    try:
        adapter = _get_adapter(broker)
    except Exception as e:
        return {"error": f"Failed to connect to {broker}: {e}"}

    open_trades = [t for t in _get_trade_history(broker=broker, status="open", limit=500)
                   if t.get("mode") == "live"]
    checked, updated_fills, closed, unresolved = 0, [], [], []

    for t in open_trades:
        checked += 1
        symbol = (t.get("symbol") or "").upper()
        order_id = t.get("order_id")

        # 1. Fill price for the entry order
        if order_id and order_id not in ("AUTO_BACKTEST", "DRY_RUN_SIM"):
            try:
                state = adapter.get_order(order_id)
                if state.get("filled_price") and abs(float(state["filled_price"]) - float(t["entry_price"])) > 1e-9:
                    updated_fills.append({"trade_id": t["trade_id"], "symbol": symbol,
                                          "recorded_entry": t["entry_price"],
                                          "actual_fill": state["filled_price"]})
            except Exception as e:
                unresolved.append({"trade_id": t["trade_id"], "reason": f"order lookup failed: {e}"})

        # 2. Position gone at the broker → the trade is closed in reality
        position = getattr(adapter, "get_position", lambda _s: None)(symbol)
        if position is None:
            try:
                last = adapter.get_current_price(symbol)
            except Exception as e:
                unresolved.append({"trade_id": t["trade_id"], "reason": f"price lookup failed: {e}"})
                continue
            entry = {"trade_id": t["trade_id"], "symbol": symbol, "exit_price": last,
                     "exit_reason": "closed_at_broker"}
            if record_exits:
                entry["record"] = _close_trade(t["trade_id"], float(last), "closed_at_broker")
            closed.append(entry)

    return {
        "broker": broker,
        "open_trades_checked": checked,
        "closed_at_broker": closed,
        "entry_price_mismatches": updated_fills,
        "unresolved": unresolved,
        "record_exits": record_exits,
        "note": ("Exit prices for positions closed at the broker use the last trade price, "
                 "not the actual fill; treat them as approximate."),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
