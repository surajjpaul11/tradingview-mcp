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
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from tradingview_mcp.core.services.trade_db import log_trade as _log_trade


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
        # Place the main market order
        order = self._exchange.create_order(
            symbol=symbol,
            type="market",
            side=side,
            amount=quantity,
        )

        sl_order = None
        tp_order = None

        # Place stop-loss order
        if stop_loss is not None:
            try:
                sl_side = "sell" if side == "buy" else "buy"
                sl_order = self._exchange.create_order(
                    symbol=symbol,
                    type="stop",
                    side=sl_side,
                    amount=quantity,
                    price=stop_loss,
                    params={"stopPrice": stop_loss, "triggerPrice": stop_loss},
                )
            except Exception as e:
                sl_order = {"error": str(e)}

        # Place take-profit order
        if take_profit is not None:
            try:
                tp_side = "sell" if side == "buy" else "buy"
                tp_order = self._exchange.create_order(
                    symbol=symbol,
                    type="limit",
                    side=tp_side,
                    amount=quantity,
                    price=take_profit,
                )
            except Exception as e:
                tp_order = {"error": str(e)}

        return {
            "order_id": order.get("id"),
            "status": order.get("status", "unknown"),
            "filled_price": order.get("average") or order.get("price"),
            "filled_quantity": order.get("filled", quantity),
            "sl_order": sl_order,
            "tp_order": tp_order,
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

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        order_params = {
            "symbol": symbol,
            "qty": quantity,
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }

        # Alpaca supports bracket orders natively
        if stop_loss is not None or take_profit is not None:
            order_params["order_class"] = "bracket"
            if stop_loss is not None:
                order_params["stop_loss"] = {"stop_price": str(round(stop_loss, 2))}
            if take_profit is not None:
                order_params["take_profit"] = {"limit_price": str(round(take_profit, 2))}

        order = self._api.submit_order(**order_params)

        return {
            "order_id": order.id,
            "status": order.status,
            "filled_price": float(order.filled_avg_price) if order.filled_avg_price else None,
            "filled_quantity": float(order.filled_qty) if order.filled_qty else quantity,
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
            price = adapter.get_current_price(symbol)
        except Exception as e:
            return {"error": f"Failed to connect to {broker}: {e}"}

    # ── Calculate position size ──
    quantity = capital_usd / price

    # For stocks (Alpaca), round to whole shares unless fractional enabled
    if broker == "alpaca":
        quantity = round(quantity, 2)  # Alpaca supports fractional
    else:
        quantity = round(quantity, 8)  # Crypto: 8 decimal precision

    # ── Execute or simulate ──
    if dry_run:
        result = _simulate_order(symbol, side, quantity, price, stop_loss, take_profit, broker)
    else:
        try:
            adapter = _get_adapter(broker)
            result = adapter.place_market_order(symbol, side, quantity, stop_loss, take_profit)
            result["broker"] = broker
            result["mode"] = "live"
            result["entry_price"] = result.get("filled_price", price)
            result["quantity"] = result.get("filled_quantity", quantity)
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
            entry_price=price,
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
