"""BTC trading bot for make.fun btc-race-24h-20261118-1444.

Strategy (long only, one full-size position at a time, up to 8 round trips):
- Entry: buy 100% of cash when the close is at least 60 bps below the 120-bar simple
  moving average of closes (a dip against the 2-hour mean) for 2 CONSECUTIVE bars.
  The second bar is the confirmation: a single 1-minute print 60 bps under the mean
  is often just a wick, and buying the confirmed dislocation instead of the wick
  lifts both dev windows (see Backtest). A dip entry is selective: on the dev window
  only a few bars a day qualify, and each one is a real dislocation, not 1-minute noise.
- Exits (whichever fires first): take profit at +180 bps above the entry close, a hard
  stop at -100 bps, or a trailing stop at -90 bps below the highest close since entry.
  The trailing stop is the part that matters: on the dev window the second trade bought
  a dip that never recovered, and without the trail it would have ridden the final
  grind down to a -$15.50 loss; the trail cut it at about -$3.50 instead.
- No new entries after bar 1200: a trade entered in the last 2 hours has too little
  time to reach its take profit and mostly ends flattened at a loss, so late entries
  have negative expected value. (Backtest: removing them lifts the dev window from
  +$3.10 to +$10.84 and changes nothing on the previous race's dev window.)
- Fallback: if no trade has fired by bar 900, buy at the market when the close is at
  or above the 120-bar mean, or unconditionally after bar 1100, so the bot always takes
  at least one trade (the race window requires at least 1 trade to rank).
- Every order caps slippage at 200 bps so gap moves do not reject it.

Backtest (offline replay of the published dev windows, exact fill model: fills at the
next bar's open, 4 bps fee + 2 bps slippage + constant-product impact vs pool depth,
flatten at the last close):
- This race's dev window (17 Nov 14:44Z - 18 Nov 14:44Z, BTC -280 bps net):
  net PnL +$12.50, 4 trades, max drawdown 1.16% -> PASSES the dev gate (needs > $0).
  (Revision 1: was +$10.84 with a 1-bar dip trigger.)
- Previous race's dev window (flat, +49 bps net): net PnL +$22.00, 7 trades,
  max drawdown 1.47%.
  (Revision 1: was +$20.90 with a 1-bar dip trigger. The offline replay model says
  +$22.21 for this revision; the real entrypoint over stdio says +$22.00 — the
  $0.21 gap is one bar: the entrypoint's 15-bar cooldown ends one bar earlier
  than the replay model counts it, so the second dip buy fires at bar 382
  instead of 383. The smoke-test numbers above are the ground truth.)
- Revision 1 changes only the entry trigger (2 consecutive dip bars instead of 1);
  every other parameter is unchanged, and the improvement holds on both windows and
  on both windows' first halves (+$14.16 vs +$12.51 and +$17.63 vs +$16.64), so it is
  a confirmation filter, not a single-window fit. 3 bars was tested and rejected:
  it drops the previous window to +$7.18 (missed dips).
- The v1 bot from the previous race (single dip entry, no trail) LOSES -$20.46 on this
  race's dev window and would not have raced at all; the trailing stop plus the
  late-entry cutoff are what turn it around. The same parameter region (trail 70-100
  bps, take profit 150-180 bps) is positive on both windows, so this is a region,
  not a single fitted point.

Honest note: +$11-21 per 24 hours on the dev windows is far from the ~$106 net PnL
the 10th place needed in the previous race. This bot is a real ticket that passes the
gate and captures crash-dip recoveries; placing needs a big-move day, which no
backtest can promise. Every order is full size because a round trip costs about
37 bps on this pool (4 bps fee + 2 bps slippage + ~13 bps of price impact per leg at
the dev window's depth), and small trades would drown in it.

The entry reference is the close of the bar the buy was decided on, and a fill is
only armed when the harness reports it filled, so a rejected buy can fire again
instead of stranding the bot in cash. The highest close since entry is tracked for
the trailing stop.

All decisions use integer math on the bar closes (plus one float mean); no randomness,
no clock, no environment, no files, no network. Deterministic: the same bars give the
same orders on every run.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
SMA_BARS = 120
ENTRY_DIP_BPS = 60
DIP_CONFIRM_BARS = 2
TAKE_PROFIT_BPS = 180
STOP_LOSS_BPS = 100
TRAILING_STOP_BPS = 90
MAX_ENTRIES = 8
COOLDOWN_BARS = 15
NO_ENTRY_AFTER_BAR = 1200
FALLBACK_BAR = 900
FALLBACK_LAST_RESORT_BAR = 1100
MAX_SLIPPAGE_BPS = 200

closes = []
entry_close = None
entries_done = 0
last_sell_bar = -10**9
bought_once = False
pending_buy_close = None
high_since_entry = None
dip_streak = 0


def on_batch(state, batch):
    global entry_close, entries_done, last_sell_bar, bought_once
    global pending_buy_close, high_since_entry, dip_streak
    # Fold this batch's fills in first: a filled buy arms the entry reference and the
    # trailing-stop high; a rejected buy clears it so the signal can fire again.
    for fill in batch.get("fills", []):
        if fill.get("symbol") != SYMBOL:
            continue
        if fill.get("status") == "filled" and fill.get("side") == "buy":
            if pending_buy_close is not None:
                entry_close = pending_buy_close
            entries_done += 1
            bought_once = True
            pending_buy_close = None
            high_since_entry = state.close(SYMBOL)
        elif fill.get("status") == "rejected" and fill.get("side") == "buy":
            pending_buy_close = None
        elif fill.get("status") == "filled" and fill.get("side") == "sell":
            entry_close = None
            high_since_entry = None
            last_sell_bar = len(closes)
    # Track closes: only bars that actually carry CBBTC (a missing minute has no bar).
    for bar in batch.get("bars", []):
        if bar.get("symbol") == SYMBOL:
            closes.append(int(bar["c"]))
    if state.warming_up:
        return []
    close = state.close(SYMBOL)
    if close is None:
        return []
    held = state.positions.get(SYMBOL)
    if held is None:
        if entries_done >= MAX_ENTRIES:
            dip_streak = 0
            return []
        if len(closes) > NO_ENTRY_AFTER_BAR:
            dip_streak = 0
            return []
        if entries_done > 0 and len(closes) - last_sell_bar < COOLDOWN_BARS:
            dip_streak = 0
            return []
        if len(closes) >= SMA_BARS:
            mean = sum(closes[-SMA_BARS:]) / SMA_BARS
            if (mean - close) * 10000 // mean >= ENTRY_DIP_BPS:
                # Revision 1: require DIP_CONFIRM_BARS consecutive bars at or
                # below the dip threshold before buying. A single 1-minute
                # print 60 bps under the mean is often just a wick; waiting for
                # the second bar filters those out and buys the confirmed
                # dislocation instead. Offline replay: +$10.84 -> +$12.50 on
                # this race's dev window and +$20.90 -> +$22.21 on the previous
                # race's window, same trade counts. (3 bars overshoots: it
                # misses real dips and drops the previous window to +$7.18.)
                dip_streak += 1
                if dip_streak >= DIP_CONFIRM_BARS:
                    dip_streak = 0
                    pending_buy_close = close
                    return [{"side": "buy", "symbol": SYMBOL,
                             "notional_quote_units": state.cash,
                             "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            else:
                dip_streak = 0
        if not bought_once and len(closes) > FALLBACK_BAR:
            mean = sum(closes[-SMA_BARS:]) / SMA_BARS if len(closes) >= SMA_BARS else close
            if close >= mean or len(closes) > FALLBACK_LAST_RESORT_BAR:
                pending_buy_close = close
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": state.cash,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []
    # Holding a position: take profit, hard stop, trailing stop, else hold.
    if entry_close is None:
        entry_close = close
    if high_since_entry is None or close > high_since_entry:
        high_since_entry = close
    if (close - entry_close) * 10000 // entry_close >= TAKE_PROFIT_BPS:
        return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    if (entry_close - close) * 10000 // entry_close >= STOP_LOSS_BPS:
        return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    if (high_since_entry - close) * 10000 // high_since_entry >= TRAILING_STOP_BPS:
        return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


makefun_bars.run(on_batch)
