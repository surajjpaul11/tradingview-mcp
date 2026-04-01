import sys
import os
from pathlib import Path

# Add src to the path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from tradingview_mcp.core.services.execution_service import execute_order

strategies = ["straight_line", "enhanced_lines", "buy_and_protect", "volatility_harvester"]
symbol = "AAPL"
interval = "1d"
side = "buy"
capital_usd = 1000.0

for strategy in strategies:
    print(f"Testing {strategy}...")
    try:
        res = execute_order(
            symbol=symbol,
            side=side,
            capital_usd=capital_usd,
            broker="alpaca",
            dry_run=True,
            strategy=strategy
        )
        print(f"Success for {strategy}: {res}")
    except Exception as e:
        print(f"Failed for {strategy}: {e}")
