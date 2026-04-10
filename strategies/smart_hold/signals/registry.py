"""Signal registry — ordered lists of active entry and exit signals.

To disable a signal: comment out its import and list entry.
To add a new signal: create the file in entries/ or exits/, import it here, add to the list.
Order matters: first matching entry signal wins.
"""

from .entries import (
    vix_extreme_fear,
    vix_fear_declining,
    fast_reentry,  # v2: added close > exit_sma guard + bars_since_exit >= 3 + vix_decline threshold 8.0
    vix_recovery_below_sma,  # v17: re-enter below SMA after VIX spike; complements fast_reentry (which requires above-SMA)
    # ma_breakdown_recovery,  # DISABLED v20 candidate: regressed GOOGL -14.26% (fires during genuine failed recoveries); see optimizer_log.md
    false_breakdown_reclaim,  # v20 candidate: 1-bar SMA reclaim (was 2-bar) to fire 1 bar earlier on QQQ false breakdowns
    # pyramid_momentum,  # DISABLED: too aggressive, causes -29% GOOGL regression (14 trades vs 11, multiple bad entries during recoveries)
    ma_reclaim,
    rsi_oversold_bounce,
    # volume_capitulation,  # DISABLED: catches false bottoms in 2y backtest
    macd_crossover,
    ema_momentum,
)
from .exits import (
    profit_lock,         # proactive exit when gain >= 50% and SMA slope just turns negative
    macd_reversal_exit,  # exit on MACD histogram bearish crossover with 18%+ gain, 40+ bars held
    # peak_gain_trail,   # DISABLED v18: peak-gain trail regressed GOOGL -5.39% (T1 premature exit); see optimizer_log.md
    # ema_sma_cross_exit,  # DISABLED v19: EMA/SMA death cross exit regressed SPY -2.92%, QQQ -7.82%; see optimizer_log.md
    ma_breakdown,
    trailing_stop,
    end_of_data,
)

# Order matters: first match wins for entries
ENTRY_SIGNALS = [
    vix_extreme_fear,
    vix_fear_declining,
    fast_reentry,  # v2: see import note above
    vix_recovery_below_sma,  # v17: see import note above
    # ma_breakdown_recovery,  # DISABLED: see import note above
    false_breakdown_reclaim,  # v20 candidate: see import note above
    # pyramid_momentum,  # DISABLED: see import note above
    ma_reclaim,
    rsi_oversold_bounce,
    # volume_capitulation,
    macd_crossover,
    ema_momentum,
]

EXIT_SIGNALS = [
    profit_lock,          # first: proactive exit on large gain + SMA slope turning negative
    macd_reversal_exit,   # MACD histogram crosses negative with 18%+ gain and 40+ bars held
    # peak_gain_trail,    # DISABLED: see import note above
    # ema_sma_cross_exit, # DISABLED: see import note above
    ma_breakdown,
    trailing_stop,
    end_of_data,
]
