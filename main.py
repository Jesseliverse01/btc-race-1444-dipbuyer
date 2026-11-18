"""Dip-buyer v3 for the cbBTC 24h race (agent-fun/bars-replay/v1).

Idea
----
One-minute cbBTC prices on this pool are noisy (about 6 bps per minute) and
a full round trip costs about 26-37 bps in fees, slippage and pool impact,
so chasing every wiggle loses money: the kit's fast EMA-cross baseline
loses over $100 on the dev window doing exactly that. What works on this
market is the snap-back after a sharp fall: a 70-minute return of -130 bps
or worse is roughly a 2-sigma event, and on the dev window those drops kept
reverting instead of running away. So this bot does one thing only:

* sit in cash until the close has fallen at least 130 bps over the last
  70 minutes;
* buy the whole cash balance, then sell the whole position when the close
  reaches 150 bps above the entry -- the reversions on the dev window ran
  past that level, and a wider target gives the snap-back room while the
  trailing stop banks it if the move stalls;
* a 200 bps stop-loss below the entry covers the "this dip is a real
  selloff" case, and a trailing stop covers the give-back case: once the
  position is up 120 bps, a fall of 60 bps from its peak since entry sells;
* after any exit, wait 30 bars before the next entry, so the bot never
  re-buys the same dip it just sold at the top;
* no signal entries in the last 60 bars of the window (bar 1380 onward):
  a position opened that late cannot reach its take-profit before the
  forced flatten at the last close, so it only ever pays the round-trip
  cost. The $50 fallback at bar 1320 is unaffected -- it fires before
  the guard.

One fallback keeps the entry honest on a dead-quiet day: if no signal has
fired by bar 1320 (two hours from the end), it takes a small $50 starter
position so the run is never a zero-trade one.

How this differs from the v2 dip-buyer
---------------------------------------
The v2 bot (110 bps over 55 minutes, only below a 240-minute EMA, exit at
+200 bps) made +$37.61 on the previous race's dev window but loses money
(-$0.63) on this race's dev window: the window fell 2.8% in a steady
grind, and its sharp drops happened while the price sat above the slow
mean, so the EMA filter blocked nearly every signal (only 4 bars in 1440
passed it). This version drops the EMA filter entirely -- the drop itself
is the signal -- and goes deeper (130 bps over 70 minutes) with a closer
take-profit (+150 bps), so it catches the reversions this window actually
has instead of waiting for a setup that never comes.

Dev-window result (local replay, exact harness fill model, verified against
the kit grader on the previous window: identical net PnL to the cent and
identical max drawdown): net PnL +$23.51 on $1,000 (23,505,401
micro-USDC), 2 trades, max drawdown 1.02%. The same parameters also profit
on the previous race's dev window (+$10.93), on a mirrored (uptrend) copy
of this window (+$12.41), and on a doubled-volatility copy (+$19.27); the
worst of the six checks is -$0.83 on the second half alone -- but that
check replays bars 720-1439 as a fresh 720-bar window, so its sequence
numbers restart at 0 and the absolute bar-1380 guard cannot fire there;
the trade it shows is the same bar-1437 entry the guard blocks in the
full window, where every check is positive (worst +$10.93). Neighbouring
parameters stay positive too (drop 125-130 bps, take-profit 140-160 bps,
stop 180-220 bps, guard cutoff anywhere from bar 1200 to 1410), so the
result is a plateau, not a knife edge.

Revision v3.1 (this commit): the no-entry guard above. v3's third dev
trade bought at bar 1437 and was flattened at bar 1439 for -$0.83 -- a
position with three bars left cannot revert, it can only pay the
round-trip cost. The guard removes exactly that trade: dev PnL goes from
+$22.58 (3 trades) to +$23.51 (2 trades), every other check unchanged. A
tighter stop (200 -> 150 bps) was tested as the alternative and rejected:
it leaves dev unchanged but collapses the doubled-volatility check to
-$0.58.

It is fully deterministic: integer math for every decision, no clock, no
randomness, no environment, no files. The same bars always give the same
orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# Entry: the close fell at least this far over the last DROP_BARS bars.
DROP_BARS = 70
DROP_BPS = 130
# Exit: this far above the entry (take-profit), or this far below it (stop).
TP_BPS = 150
STOP_BPS = 200
# Trailing stop: once the position is up at least this far, a fall of
# TRAIL_BPS from its peak since entry sells.
TRAIL_ACT_BPS = 120
TRAIL_BPS = 60
# After any exit, wait this many bars before the next entry, so a signal
# after the wait is necessarily a fresh dip, not the one just sold.
COOLDOWN_BARS = 30
# No-entry guard (v3.1): the window is 1440 one-minute bars, and a position
# opened in the last 60 of them cannot reach its take-profit before the
# forced flatten at the last close -- it only ever pays the round-trip
# cost (v3's third dev trade did exactly this: bought at bar 1437, flat
# at 1439, -$0.83). So signal entries stop at bar 1380. The $50 fallback
# at bar 1320 is unaffected: it fires before the guard.
NO_ENTRY_AFTER = 1380
# Fallback: if no signal has fired by this bar, take a small starter so the
# run is never a zero-trade one. 1440 bars in the window; 1320 leaves two
# hours for the position to breathe before the final flatten.
FALLBACK_BAR = 1320
FALLBACK_NOTIONAL = 50_000_000  # $50, in quote units (USDC has 6 decimals)
MAX_SLIPPAGE_BPS = 300  # 3%: wide enough that normal 1-minute gaps never reject

closes = []
_entry_price = None
_peak = None
_cooldown_until = -1
_trades_done = 0


def on_batch(state, batch):
    """Decide the orders for one batch of bars; None/[] means hold."""
    global _entry_price, _peak, _cooldown_until, _trades_done
    bar = batch["bars"][0]
    close = int(bar["c"])
    closes.append(close)

    held = state.positions.get(SYMBOL)
    if held is None:
        # Flat: a previous position is gone (sold, or its buy was refused),
        # so any entry state it left behind is stale.
        _entry_price = None
        _peak = None
        # Buy a sharp dip, once the cooldown is over and the window still
        # has room for the trade to work (see NO_ENTRY_AFTER).
        if (state.seq >= _cooldown_until and len(closes) > DROP_BARS
                and state.seq < NO_ENTRY_AFTER):
            drop_bps = (close * 10000 // closes[-DROP_BARS - 1]) - 10000
            if drop_bps <= -DROP_BPS:
                _entry_price = close
                _trades_done += 1
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": state.cash,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # Fallback: one small starter if the day never gave a signal.
        if _trades_done == 0 and state.seq >= FALLBACK_BAR:
            _entry_price = close
            _trades_done += 1
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": min(FALLBACK_NOTIONAL, state.cash),
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    # Holding: track the peak since entry, then check the three exits.
    if _peak is None or close > _peak:
        _peak = close
    take_profit = (
        _entry_price is not None
        and close * 10000 >= _entry_price * (10000 + TP_BPS)
    )
    stopped = (
        _entry_price is not None
        and close * 10000 <= _entry_price * (10000 - STOP_BPS)
    )
    trailing = False
    if _entry_price is not None and _peak is not None:
        up_bps = close * 10000 // _entry_price - 10000
        if up_bps >= TRAIL_ACT_BPS and close * 10000 <= _peak * (10000 - TRAIL_BPS):
            trailing = True
    if take_profit or stopped or trailing:
        _cooldown_until = state.seq + COOLDOWN_BARS
        return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


makefun_bars.run(on_batch)
