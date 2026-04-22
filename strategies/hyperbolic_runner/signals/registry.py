"""Signal registry — ordered lists of active entry, pyramid, and exit signals for Hyperbolic Runner.

To disable a signal: comment out its import and list entry.
To add a new signal: create the file in entries/ or exits/, import it here, add to the list.
Order matters: first matching entry/exit signal wins.

PYRAMID_SIGNALS are evaluated separately when in_position — they scale into existing positions.
"""

from .entries import (
    ema_reclaim,
    rsi_recovery,
    volume_surge_pyramid,
)
from .exits import (
    hard_breakdown,
    volume_momentum_exit,
    trailing_stop,
    end_of_data,
)

# Order matters: first match wins for entries
ENTRY_SIGNALS = [
    ema_reclaim,   # EMA reclaim outside consolidation (or in explosive cluster)
    rsi_recovery,  # RSI bounce from oversold outside consolidation
]

# Pyramid signals: evaluated when in_position to scale into winning positions
PYRAMID_SIGNALS = [
    volume_surge_pyramid,  # Add 50% more on high-volume momentum surge (+5% gain, +3% bar, 2x vol)
]

EXIT_SIGNALS = [
    hard_breakdown,        # Close < 20-period low for 2+ bars AND RSI < 40
    volume_momentum_exit,  # Single-bar panic drop >= 3.5% with 2.5x volume (fires before trailing stop)
    trailing_stop,         # 20x ATR from peak — catastrophic reversal protection
    end_of_data,           # Force-close at end of backtest
]
