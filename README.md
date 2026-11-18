# BTC Race Bot — 18 Nov 2026

[![make.fun](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/Herman-234/btc-race-bot-20261118/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/Herman-234/btc-race-bot-20261118/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)

Entry for [Race a BTC trading bot live for 24 hours](https://make.fun/bounty/btc-race-24h-20261118-1444) on [make.fun](https://make.fun) — a bot that trades Coinbase Wrapped BTC (cbBTC) on 1-minute on-chain prices with $1,000 of paper money. $250 USDC goes to the 10 highest net PnLs.

## Strategy (long only, full size, up to 8 round trips)

- **Entry:** buy when the close is at least 60 bps below the 120-bar moving average (a dip against the 2-hour mean).
- **Exits:** take profit +180 bps, hard stop −100 bps, or a trailing stop −90 bps below the highest close since entry. The trailing stop is the key improvement over the previous race's bot: it cuts a dip-buy that never recovers instead of riding it down.
- **No new entries after bar 1200:** late entries have too little time to reach take profit and mostly end flattened at a loss.
- **Fallback:** if no trade has fired by bar 900, buy at the market when the close is at or above the 120-bar mean (or unconditionally after bar 1100), so the bot always takes at least one trade.

## Backtest (offline replay, exact fill model)

| Dev window | Net PnL | Trades | Max drawdown |
|---|---|---|---|
| This race (17 Nov 14:44Z – 18 Nov 14:44Z, BTC −280 bps) | **+$10.84** | 4 | 1.16% |
| Previous race (flat, +49 bps) | **+$20.90** | 7 | 1.49% |

The previous race's bot (single dip entry, no trailing stop) loses −$20.46 on this race's dev window and would not have raced at all. The same parameter region (trail 70–100 bps, take profit 150–180 bps) is positive on both windows.

Honest note: +$11–21 per 24 hours is far from the ~$106 the 10th place needed in the previous race. This is a real ticket that passes the dev gate (needs net PnL > $0) and captures crash-dip recoveries; placing needs a big-move day.

## Files

- `main.py` — the bot (Python 3.13, standard library only; deterministic, no network, no clock).
- `vendor/makefun_bars.py` — the kit's replay shim, vendored.
- `LICENSE` — MIT.

## Run

The grader runs `python3 -P -s main.py` and speaks the `agent-fun/bars-replay/v1` protocol over stdin/stdout (one JSON line per 1-minute bar, orders back as replies).
