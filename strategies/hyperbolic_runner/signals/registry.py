"""Signal registry — ordered lists of active entry and exit signals for Hyperbolic Runner.

To disable a signal: comment out its import and list entry.
To add a new signal: create the file in entries/ or exits/, import it here, add to the list.
Order matters: first matching entry signal wins.
"""

from .entries import (
    ema_reclaim,
    rsi_recovery,
)
from .exits import (
    hard_breakdown,
    trailing_stop,
    end_of_data,
)

# Order matters: first match wins for entries
ENTRY_SIGNALS = [
    ema_reclaim,   # EMA reclaim outside consolidation (or in explosive cluster)
    rsi_recovery,  # RSI bounce from oversold outside consolidation
]

EXIT_SIGNALS = [
    hard_breakdown,  # Close < 20-period low for 2+ bars AND RSI < 40
    trailing_stop,   # 20x ATR from peak — catastrophic reversal protection
    end_of_data,     # Force-close at end of backtest
]
