# EURUSD 30m EMA200 pullback + swing breakout

Long only above the 200 EMA, short only below. Wait for a pullback into the
EMA, then enter on the break of the last confirmed swing. Signals are generated
on 30-minute bars and executed intrabar on 5-minute (2018–2026) or 1-minute
(2006–2026) data, so stop and target fills are not assumed at bar boundaries.

## Headline result

Final configuration (`s1216rr3b`): 12:00–16:00 UTC session, variant B stop,
3R target, 0.2 pip per side.

| Metric | 5m 2018–2026 | 1m pooled 2012–2026 |
|---|---|---|
| Trades | 987 | 1,929 |
| Win rate | 31.8% | — |
| Profit factor | 1.28 | — |
| Expectancy | +0.235R | +0.102R (t 1.98) |
| Max drawdown | −24.1% | — |

Walk-forward: in-sample 2018–2022 +0.233R, out-of-sample 2023–2026 +0.244R.
Eight of nine calendar years are positive. The edge does not transfer to GBPUSD
(+0.027R), and 2015–2017 is the weak era on 1-minute data (−0.025R).

## Layout

```
REPORT.md                 full write-up: method, ablations, caveats
RESEARCH_LOG.md           chronological findings
MONEYCHECK.md             prop-firm qualification simulation
moneycheck.py             Aqua Funded 5k 2-step simulation
ema200_breakout_exec5m.py main engine (backtesting.py, intrabar 5m/1m)
ema200_pullback_breakout.py  signal-only prototype on 30m
mae_by_tag.py             per-trade adverse excursion extraction
significance.py           t-stat and block bootstrap CI
walkforward.py            in-sample / out-of-sample split
pool_1m.py                pooled 1-minute expectancy
session_scan.py           59-window session scan
grid_*.py                 parameter ablations
breakeven_study.py        break-even stop study
out/                      trade logs, summaries, equity charts
```

## Reproduce

Market data is not included. Place EURUSD bars as CSV under
`<root>/market_data/EURUSD/{1m,5m}/yearly/` with `DateTime,Open,High,Low,Close`
columns, then:

```bash
python ema200_breakout_exec5m.py --exec-tf 5m --start 2018-01-01 \
    --session-start 12 --session-end 16 --rr 3 --no-fresh --tag s1216rr3b

python moneycheck.py s1216rr3b 3 20000
```

`out/exec5m_trades_s1216rr3b_B_wide_body.csv` reproduces the headline table;
`moneycheck.py` reproduces the prop-firm numbers.

## Caveats

- Same-bar stop/target ambiguity flatters 5-minute results (42% of trades at 3R
  are affected); the 1-minute runs are the control and give +0.102R.
- Fixed 0.2 pip spread, no commission, no swap, single broker feed.
- Prop-firm phase-2 target of 5% is an assumption and is flagged in
  `MONEYCHECK.md`.
- Above 0.2% risk per trade the real historical path breaches a 10% trailing
  drawdown limit, so simulated pass rates at higher risk are not investable.
