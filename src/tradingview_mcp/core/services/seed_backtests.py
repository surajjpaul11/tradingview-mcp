import json
import uuid
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from tradingview_mcp.core.services.trade_db import _get_connection, _get_db_path, init_db

def _format_iso_datetime(date_str: str, default_time: str = "09:30:00") -> str:
    """Format any date string to standard ISO-8601 with timezone."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    s = str(date_str).strip()
    if " " in s and "T" in s:
        s = s.split("T")[0].replace(" ", "T")
        if s.count(":") == 1:
            s += ":00"
        return f"{s}+00:00"
    if "T" in s:
        if "+" in s or s.endswith("Z"):
            return s
        return f"{s}+00:00"
    if " " in s:
        parts = s.split()
        date_part = parts[0]
        time_part = parts[1]
        if time_part.count(":") == 1:
            time_part = f"{time_part}:00"
        return f"{date_part}T{time_part}+00:00"
    return f"{s}T{default_time}+00:00"

def seed_backtest_data(db_path: str = None) -> int:
    """Import historical trades from all backtest JSON files into trades.db."""
    init_db(db_path)
    conn = _get_connection(db_path)
    
    # Locate project root and backtest JSON files
    current = Path(__file__).resolve()
    base_dir = current.parents[4]  # tradingview-mcp
    strategies_dir = base_dir / "strategies"
    
    json_files = list(strategies_dir.rglob("*backtest*.json"))
    if not json_files:
        print("No backtest JSON files found.")
        conn.close()
        return 0

    print(f"Found {len(json_files)} backtest JSON files in {strategies_dir}")
    
    # Clear previous backtest imports to remain idempotent
    conn.execute("DELETE FROM trade_exits WHERE trade_id IN (SELECT trade_id FROM trades WHERE mode = 'backtest')")
    conn.execute("DELETE FROM trades WHERE mode = 'backtest'")
    conn.commit()
    
    inserted_trades = 0
    
    for jf in json_files:
        try:
            data = json.loads(jf.read_text())
            symbol = data.get("symbol")
            strategy = data.get("strategy")
            trade_log = data.get("trade_log", [])
            interval = data.get("interval", "1d")
            
            if not symbol or not strategy or not trade_log:
                continue
                
            for t in trade_log:
                trade_id = str(uuid.uuid4())
                side_raw = (t.get("side") or "long").lower()
                side = "buy" if side_raw in ("long", "buy") else "sell"
                
                entry_price = float(t.get("entry_price", 0))
                exit_price = float(t.get("exit_price", entry_price))
                exit_reason = str(t.get("exit_reason", "signal_exit"))
                
                # Format ISO dates
                entry_date_str = str(t.get("entry_date", ""))
                exit_date_str = str(t.get("exit_date", entry_date_str))
                
                created_at = _format_iso_datetime(entry_date_str, "09:30:00")
                closed_at = _format_iso_datetime(exit_date_str, "16:00:00")
                
                # Capital & quantity
                capital_usd = 1000.0
                quantity = round(capital_usd / entry_price, 4) if entry_price > 0 else 1.0
                
                # PnL
                return_pct = float(t.get("return_pct", 0.0))
                if side == "buy":
                    pnl_usd = round((exit_price - entry_price) * quantity, 2)
                else:
                    pnl_usd = round((entry_price - exit_price) * quantity, 2)
                
                # Insert trade record
                conn.execute(
                    """INSERT INTO trades
                       (trade_id, symbol, side, strategy, broker, quantity, entry_price,
                        capital_usd, mode, order_id, status, interval, notes,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'backtest', ?, ?, ?, 'backtest', 'BACKTEST_IMPORT',
                               'closed', ?, ?, ?, ?)""",
                    (trade_id, symbol.upper(), side, strategy.lower(), quantity, entry_price,
                     capital_usd, interval, f"Backtest from {jf.name}", created_at, closed_at)
                )
                
                # Calculate holding duration
                try:
                    d1 = datetime.fromisoformat(created_at)
                    d2 = datetime.fromisoformat(closed_at)
                    holding_seconds = int((d2 - d1).total_seconds())
                except Exception:
                    holding_seconds = 86400
                    
                # Insert exit record
                conn.execute(
                    """INSERT INTO trade_exits
                       (trade_id, exit_price, exit_reason, pnl_usd, pnl_pct,
                        holding_seconds, fees_usd, closed_at)
                       VALUES (?, ?, ?, ?, ?, ?, 3.0, ?)""",
                    (trade_id, exit_price, exit_reason, pnl_usd, return_pct, holding_seconds, closed_at)
                )
                inserted_trades += 1
                
        except Exception as e:
            print(f"Error processing {jf.name}: {e}")
            
    conn.commit()
    conn.close()
    print(f"Successfully seeded {inserted_trades} closed historical trades into trades.db!")
    return inserted_trades

if __name__ == "__main__":
    seed_backtest_data()
