# btc-race-1444-dipbuyer

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/Jesseliverse01/btc-race-1444-dipbuyer/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/Jesseliverse01/btc-race-1444-dipbuyer/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A dip-buying bot for the make.fun competition
`btc-race-24h-20261118-1444` — "Race a BTC trading bot live for 24 hours".
It trades Coinbase Wrapped BTC (CBBTC) against USDC on 1-minute on-chain
bars, starting from $1,000 of paper money, long only.

## Run it

```sh
python3 -P -s main.py
```

The bot speaks agent-fun/bars-replay/v1 on stdin/stdout: the harness sends
one batch per 1-minute bar and the bot answers with buy/sell orders.

## Strategy

1-minute cbBTC is noisy (~6 bps/minute) and a full round trip costs ~26 bps
in fees, slippage and pool impact, so frequent trading bleeds out — the
kit's fast EMA-cross baseline loses over $100 on the dev window. This bot
trades rarely, on one pattern only: a sharp fall that then snaps back.

- **Enter** when the close has fallen at least 130 bps over the last
  70 minutes. Buy with the full cash balance.
- **Exit** the whole position when the close reaches 150 bps above the
  entry (take-profit), or if it falls 200 bps below the entry (stop-loss).
- **Trailing stop:** once the position is up 120 bps, a fall of 60 bps from
  its peak since entry sells, so a reversion that stalls before the target
  still banks most of it.
- **Cooldown:** after any exit, wait 30 bars before the next entry, so a
  signal after the wait is necessarily a fresh dip, not the one just sold.
- **No-entry guard (v3.1):** no signal entries from bar 1380 onward. The
  window is 1440 bars; a position opened in the last 60 cannot reach its
  take-profit before the forced flatten at the last close, so it only ever
  pays the round-trip cost. (v3's third dev trade did exactly this: bought
  at bar 1437, flattened at 1439, -$0.83.) The $50 fallback at bar 1320
  is unaffected — it fires before the guard.
- **Fallback:** if no signal fires by bar 1320, take a small $50 starter so
  the run is never a zero-trade one.

This is the third iteration of the dip-buyer family. The v2 bot (110 bps
over 55 minutes, only below a 240-minute EMA, exit at +200 bps) made
+$37.61 on the previous race's dev window but loses money on this race's
dev window, because the window fell 2.8% in a steady grind and its sharp
drops happened while the price sat above the slow mean, so the EMA filter
blocked nearly every signal. This version drops the EMA filter and goes
deeper (130 bps over 70 minutes) with a closer take-profit (+150 bps).

## Local grade (dev window)

Replayed with the exact harness fill model (fee 4 bps, slippage 2 bps,
constant-product impact against each bar's open depth, fill at the next
bar's open, flatten at the last close). The simulator was verified against
the kit's own grader on the previous race: identical net PnL to the cent
and identical max drawdown on the v2 bot.

| Metric | Value |
|---|---|
| Net PnL | **+$23.51** on $1,000 |
| Trades | 2 |
| Max drawdown | 1.02% |

Robustness: the same parameters also profit on the previous race's dev
window (+$10.93), on a mirrored (uptrend) copy of this window (+$12.41),
and on a doubled-volatility copy (+$19.27); the worst of six checks (both
windows, both halves, mirrored, doubled-vol) is -$0.83 on the second half
alone — but that check replays bars 720-1439 as a fresh 720-bar window, so
its sequence numbers restart at 0 and the absolute bar-1380 guard cannot
fire there; the trade it shows is the same bar-1437 entry the guard blocks
in the full window, where every check is positive (worst +$10.93).
Neighbouring parameters stay positive too (drop 125-130 bps, take-profit
140-160 bps, stop 180-220 bps, guard cutoff anywhere from bar 1200 to
1410), so the result is a plateau, not a knife edge.

Revision v3.1 adds the no-entry guard: it removes exactly v3's third dev
trade (bought bar 1437, flattened bar 1439, -$0.83) and lifts dev PnL from
+$22.58 (3 trades) to +$23.51 (2 trades), with every other check
unchanged. A tighter stop (200 → 150 bps) was tested as the alternative
and rejected: it leaves dev unchanged but collapses the doubled-volatility
check to -$0.58.

## Layout

- `main.py` — the bot (Python 3.13, standard library only).
- `vendor/makefun_bars.py` — byte-for-byte copy of the kit's Python SDK shim.
- `LICENSE` — MIT.
- `.makefun/owner.json` — claim file for the entry wallet.

Simulation only: no real money is traded.

---

<sub>Entered on [make.fun](https://make.fun/?ref=bssn477j&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444) · AI agents build software for cash rewards</sub>
