"""Signal registry — ordered lists of active entry and exit signals.

To disable a signal: comment out its import and list entry.
To add a new signal: create the file in entries/ or exits/, import it here, add to the list.
Order matters: first matching entry signal wins.
"""

from .entries import (
    vix_extreme_fear,
    vix_fear_declining,
    ma_reclaim,
    rsi_oversold_bounce,
    # volume_capitulation,  # DISABLED: catches false bottoms in 2y backtest
    ema_momentum,
)
from .exits import (
    ma_breakdown,
    trailing_stop,
    end_of_data,
)

# Order matters: first match wins for entries
ENTRY_SIGNALS = [
    vix_extreme_fear,
    vix_fear_declining,
    ma_reclaim,
    rsi_oversold_bounce,
    # volume_capitulation,
    ema_momentum,
]

EXIT_SIGNALS = [
    ma_breakdown,
    trailing_stop,
    end_of_data,
]
