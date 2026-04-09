"""Signal registry — ordered lists of active entry and exit signals.

To disable a signal: comment out its import and list entry.
To add a new signal: create the file in entries/ or exits/, import it here, add to the list.
Order matters: first matching entry signal wins.
"""

from .entries import (
    vix_extreme_fear,
    vix_fear_declining,
    fast_reentry,  # v2: added close > exit_sma guard + bars_since_exit >= 3 + vix_decline threshold 8.0
    # false_breakdown_reclaim,  # DISABLED: 0 improve / 3 neutral (fires same bar as ma_reclaim with default reentry_ma_reclaim=2)
    # pyramid_momentum,  # DISABLED: too aggressive, causes -29% GOOGL regression (14 trades vs 11, multiple bad entries during recoveries)
    ma_reclaim,
    rsi_oversold_bounce,
    # volume_capitulation,  # DISABLED: catches false bottoms in 2y backtest
    macd_crossover,
    ema_momentum,
)
from .exits import (
    profit_lock,  # proactive exit when gain >= 50% and SMA slope just turns negative
    ma_breakdown,
    trailing_stop,
    end_of_data,
)

# Order matters: first match wins for entries
ENTRY_SIGNALS = [
    vix_extreme_fear,
    vix_fear_declining,
    fast_reentry,  # v2: see import note above
    # false_breakdown_reclaim,  # DISABLED: see import note above
    # pyramid_momentum,  # DISABLED: see import note above
    ma_reclaim,
    rsi_oversold_bounce,
    # volume_capitulation,
    macd_crossover,
    ema_momentum,
]

EXIT_SIGNALS = [
    profit_lock,  # first: proactive exit on large gain + SMA slope turning negative
    ma_breakdown,
    trailing_stop,
    end_of_data,
]
