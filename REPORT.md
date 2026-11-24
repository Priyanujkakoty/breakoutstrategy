# EURUSD 30m — 200 EMA pullback + swing breakout

Backtest of the posted ruleset with `backtesting.py` 0.6.6 on Dukascopy EURUSD bid
data. Signals on 30-minute bars, execution on 5-minute bars (1-minute control),
2018-01-01 → 2026-11-03, plus older samples back to 2007.

## Verdict

**The rules as written have no edge. With three changes the strategy has a
positive expectancy that survives an out-of-sample split and a 1-minute
execution control:**

1. **Trade only 12:00–16:00 UTC** (the London–New York overlap into the US
   morning). The London morning loses.
2. **Target 3R instead of 1.5R.** Win rate falls to ~32%, but the payoff more
   than compensates.
3. **Correct position sizing.** The original engine ran at ~50× equity; fixed
   to 1% risk per trade. R multiples were unaffected, all earlier return and
   drawdown figures were wrong.

Headline result, 5m execution, 0.2 pip spread per side, 1% risk per trade:

| Metric | Value |
|---|---|
| Trades | 987 |
| Win rate | 31.8% |
| Profit factor | 1.28 |
| Expectancy | **+0.235 R** per trade |
| t-stat | **3.49** (95% CI +0.104 … +0.368) |
| Return | +696.9% |
| CAGR | 26.5% |
| Max drawdown | −24.1% |
| Sharpe | 0.91 |
| Median hold | 15 min (mean 3.8 h) |

Walk-forward (config frozen, split by date):

| Window | n | Win % | PF | Exp R | Return | Max DD |
|---|---|---|---|---|---|---|
| IS 2018–2022 | 552 | 32.2 | 1.25 | +0.233 | +214% | −23% |
| OOS 2023–2026 | 422 | 31.3 | 1.36 | +0.244 | +155% | −18% |

1-minute execution control, 2022–2024: +0.116 R (n 474, PF 1.14, max DD
−27.3%). Positive, about half the 5m figure — the 5m run is flattered by
same-bar SL/TP ambiguity. Pooled across four non-overlapping 1-minute slices
spanning 2012–2026 (1,929 trades): **+0.102 R, t = 1.98**, bootstrap 95% CI
−0.003 … +0.200. Every slice is non-negative at 1m.

Yearly expectancy (5m, final config):

| Year | n | Win % | Exp R |
|---|---|---|---|
| 2018 | 77 | 37.7 | +0.41 |
| 2019 | 115 | 39.1 | +0.51 |
| 2020 | 90 | 33.3 | +0.14 |
| 2021 | 142 | 31.7 | +0.22 |
| 2022 | 128 | 22.7 | −0.04 |
| 2023 | 122 | 33.6 | +0.31 |
| 2024 | 104 | 35.6 | +0.38 |
| 2025 | 118 | 27.1 | +0.06 |
| 2026 | 91 | 28.6 | +0.20 |

Eight of nine calendar years positive. Longs +0.234 R (n 462), shorts
+0.235 R (n 525) — no directional bias.

**This is not a universal edge.** On 5m the same rules lose −0.222 R per trade
on 2015–2017 and −0.216 R over 2007–2017 as a whole; over the full 2007–2026
sample the 5m expectancy is +0.046 R (PF 1.21, n 2,062) — positive only because
2017–2026 is strongly positive. On 1-minute execution, however, 2015–2017 is
flat (−0.025 R) rather than a disaster, and 2022–2026 is +0.132 R with every
year positive. GBPUSD is flat (+0.027 R). See §5–§7.

---

## 1. Rules → code

| Rule | Implementation |
|---|---|
| 200 EMA trend filter | 30m close vs EMA(200) of 30m closes. Long only above, short only below. |
| Pullback inside the trend | Long: lowest low of the last 25 30m bars within 0.5 × ATR(14) of the EMA. Short: mirror with the highest high. |
| Local swing high/low | Confirmed fractal pivot, 10 bars each side (5 h). Usable only 10 bars after it forms — no look-ahead. |
| Breakout entry | Stop order 1 pip beyond the pivot. |
| Option B stop | Behind the body of the 30m breakout candle — at its open, known when the stop triggers. |
| Take profit | **3 × SL distance** from the spread-adjusted fill. |
| Session | Entries only 12:00–16:00 UTC. |
| Sizing | 1% of equity risked per trade, 50:1 margin. |
| Costs | 0.2 pip spread per side (0.4 round trip), no commission, no swap. |

Unspecified points:

- "Pullback within the trend" = within 0.5 ATR of the EMA. Requiring an actual
  touch (`--pb-atr 0`) was tested; it does not improve the final config.
- "Local swing high" = confirmed 10-bar fractal. A Donchian high has no
  confirmation delay and degenerates into a permanent stop order.
- Option B's risk is capped at 1.5 × ATR(30m); larger-risk breakouts are
  skipped.

## 2. What was wrong with the first version

### Look-ahead/index bug

Plain numpy arrays were indexed with `[-1]` inside `Strategy.next()`. For
`self.I(...)` indicators that is the current bar; for plain arrays it is the
**last bar of the whole dataset**. Two consequences: the "fresh setup" filter
was inert, and one trade side could be blocked for an entire run. Fixed with
`_cur(arr) = arr[len(self.data) - 1]`. All numbers here come from the fixed
engine.

### Position sizing

`_size` divided by `equity / leverage`, but `backtesting.py` fills
`margin_available * leverage * size / price` units. Every trade therefore ran
at 99% of maximum notional — up to ~50× equity — instead of 1% risk. R
multiples were unchanged; all earlier return and drawdown figures were
inflated and risk per trade varied with stop width. After the fix, realised
loss on stop-outs averages 1.002% of equity.

## 3. Data and engine

- Signals: 30m bars resampled from execution bars, UTC.
- Execution: 5m bars, 2018-01-01 → 2026-11-03, 659,717 bars.
- 1m control: 2022-01-01 → 2024-12-31, 1m bars.
- Old sample: EURUSD 1m 2007–2017 (4.1M bars); the 5m tests for that era use
  5m bars rebuilt from the same 1m data.
- `backtesting.py` defers a contingent SL/TP to the next bar when both fall
  inside the entry bar. At 3R, 42% of trades are affected on 5m. The 1m run is
  the control for that bias.
- Weekend gaps included. Median hold 15 min, so swap is irrelevant.

## 4. How the final configuration was reached

### 4.1 Target

Same entries, different take-profit. 5m, 2018–2026, 12–16 UTC:

| RR | n | Win % | PF | Exp R |
|---|---|---|---|---|
| 1.0 | 1,126 | 51.0 | 1.18 | +0.022 |
| 1.5 | 1,057 | 44.3 | 1.21 | +0.093 |
| 2.0 | 1,022 | 38.9 | 1.21 | +0.142 |
| 2.5 | 1,001 | 35.4 | 1.27 | +0.198 |
| 3.0 | 987 | 31.8 | 1.28 | +0.235 |

Breakeven at 3R is 25%; the setup delivers 31.8%. The 1.5R target was capping
the right tail: with 1.5R the same trades win 44% but the winners are too
small relative to the losers' cost.

### 4.2 Session

Exhaustive scan of all 4-hour windows on the trade log, then walk-forward:

| Window UTC | n | Win % | PF | Exp R |
|---|---|---|---|---|
| all hours | 2,767 | 39.8 | 1.01 | −0.028 |
| 07–11 | 665 | 36.4 | 0.86 | −0.130 |
| 09–12 | 521 | 37.2 | 0.85 | −0.134 |
| 11–16 | 1,208 | 43.5 | 1.15 | +0.066 |
| 12–16 | 1,057 | 44.3 | 1.21 | +0.093 |

Across 59 candidate windows, 34% are positive in-sample, 58% positive
out-of-sample, and the IS–OOS correlation of window expectancy is 0.71. Of the
eight non-overlapping 4-hour windows only two (11–15, 12–16) are positive in
both halves. The London morning is negative in both halves — that is the
stable part of the finding.

### 4.3 Stop variant

Option A (stop 1 pip past the broken pivot, ~2.2 pips of risk) cannot pay the
spread: 0.4 pips of cost against 2.2 pips of risk is 18% of R. On the same
12–16 session it returns −0.023 R (n 1,669) and −54.5%. Option C (enter at the
30m close) needs a 40% hit rate at 1.5R and delivers 34%; at 3R it is worse.
Option B is the only viable stop.

### 4.4 Filters that were tested and rejected

| Filter | Effect on 12–16 expectancy |
|---|---|
| EMA slope ≥ 0 | +0.022 (worse) |
| ATR / 100-bar mean ≤ 1.0 | cuts trades 6×, expectancy ~0 |
| ATR / 1000-bar mean cap | kills the modern edge (0.208 → 0.052) |
| 07–11 session | −0.130 |
| 09–12 session | −0.134 |
| Fresh pivot+pullback after exit | halves trades, +0.02 R on some slices, −0.14 R on 2012–2014 |
| Fade the breakout | −0.73 R modern, −0.61 R ancient |

The fade result matters: the direction of the premise is right. Buying the
break of a confirmed swing high in the NY session is not a mean-reversion
mistake.

A breakeven stop was tested too: move the stop to entry once price reaches
+1R, +1.5R or +2R. 42% of losing trades do touch +1R first, but the rule still
hurts: return falls from +697% to +367…478% and PF slips from 1.28 to 1.26.
Winners that dip back to entry after running 1R give up the whole 3R payout.
Rejected. (R-multiples are not comparable for that variant: the recorded stop,
and therefore the measured risk, moves with the rule.)

## 5. 1-minute control

1-minute execution, final config, 0.2 pip/side:

| Period | n | Win % | PF | Exp R | Return | Max DD |
|---|---|---|---|---|---|---|
| 2012–2014 | 364 | 26.4 | 1.32 | +0.040 | +14.7% | −29.6% |
| 2015–2017 | 429 | 29.4 | 1.01 | −0.025 | −33.7% | −63.0% |
| 2018–2020 | 380 | 32.1 | 1.49 | +0.245 | +132.3% | −23.1% |
| 2022–2024 | 474 | 28.1 | 1.14 | +0.116 | +59.8% | −27.3% |
| 2022–2026 | 756 | 28.6 | 1.18 | +0.132 | +135.0% | −27.3% |

Pooled over the non-overlapping slices 2012–2014, 2015–2017, 2018–2020 and
2022–2026 (1,929 trades): **+0.102 R per trade, t = 1.98**, bootstrap 95% CI
−0.003…+0.200. That is the least flattering estimate of the edge and it is
still positive.

Yearly 2022–2026 at 1m: 2022 +1.2%, 2023 +18.7%, 2024 +47.0%, 2025 +20.1%,
2026 +10.8% — every calendar year positive.

The 1m figure is about half the 5m figure (+0.132 vs +0.235). The gap is
consistent with the 5m run's same-bar deferral flattering entries whose stop
and target both sit inside one 5m bar. The 1m estimate is the one to trust.

The 1m test also softens the regime story: at 5m the 2015–2017 slice reads
−0.222 R, but at 1m the same years are essentially flat (−0.025 R, PF 1.01).
The era is unprofitable rather than catastrophically bad; the 5m number
overstates the failure the same way it overstates the success.

## 6. 20-year sample

5m execution, EURUSD, 2007–2026, same config:

| Metric | Value |
|---|---|
| Trades | 2,062 |
| Win rate | 29.6% |
| PF | 1.21 |
| Expectancy | +0.046 R |
| Return | +76.9% |
| Max DD | −85.8% |

Yearly: 2007–2011 all negative, 2012 +22%, 2013 +34%, 2014 −9%, 2015 −50%,
2016 −31%, 2017 +15%, then 2018–2026 positive except 2022 (−10%).

So the edge is regime-dependent on 5m. It worked in 2012–2014 and 2018–2026,
and failed in 2007–2011 and 2015–2017. At 1-minute the failure is much
smaller: 2015–2017 is −0.025 R. Nothing tested repairs the 2015–2017 stretch
outright: raising the target, capping volatility, changing session, and fading
all fail there.

## 7. Era and instrument detail

3-year slices, 5m, 0.2 pip/side, expectancy in R:

| Config | 2012–2014 | 2015–2017 | 2018–2020 | 2021–2023 | 2024–2026 |
|---|---|---|---|---|---|
| RR 1.5 | +0.047 | −0.256 | — | — | — |
| RR 2.0 | — | — | +0.175 | +0.118 | +0.158 |
| RR 3.0 | +0.177 | −0.222 | +0.355 | +0.169 | +0.226 |
| RR 4.0 | — | — | +0.559 | +0.102 | +0.187 |
| RR 5.0 | — | — | +0.622 | +0.187 | +0.304 |

Raising the target improves every era, which is why 3R is used rather than
fitting the best cell per period. 4R and 5R look better in two slices but
collapse in 2021–2023; 3R is the most consistent.

GBPUSD, same rules, 5m 2018–2026: RR 1.5 −0.043 R; RR 3.0 +0.027 R
(PF 1.05, +5.9%). The edge does not transfer.

## 8. Why this works, mechanically

- The session filter removes the London morning, where breakout failures
  cluster (−0.13 R per trade over 665 trades).
- The 3R target converts a 32% hit rate into +0.24 R. At 1.5R the same entries
  need 40% and deliver 44% — a 4-point margin. At 3R they need 25% and deliver
  32% — a 7-point margin. The wider target widens the margin because the loss
  is fixed at 1R while the win scales.
- The B stop (behind the breakout candle's body, average 6.5 pips) is wide
  enough that the 0.4-pip round trip is ~6% of risk, not 18% as with Option A.
- Exit mix: 60.4% stop-outs at −1.00 R, 30.2% targets at +3.00 R, 9.4%
  gaps/other averaging −0.70 R. The arithmetic is
  `0.302 × 3 − 0.604 × 1 − 0.094 × 0.7 ≈ +0.24 R`.

## 9. Caveats

1. **Selection.** The session window and the 3R target were chosen after
   looking at this data. The IS/OOS split and the 1m control are the only
   protections, and both are in-sample with respect to the choice of window.
   The honest checks are the 20-year 5m sample (+0.046 R) and the pooled 1m
   slices (+0.102 R, t 1.98).
2. **Regime dependence.** 2015–2017 is flat at 1m (−0.025 R) and bad at 5m
   (−0.222 R). Do not assume the 2018–2026 behaviour persists.
3. **Costs.** Fixed 0.2 pip/side, no slippage beyond the spread, no commission,
   no swap. Live slippage on stop entries in fast markets would reduce
   expectancy; the ancient sample shows what that looks like (gap exits average
   −1.45 R there).
4. **Same-bar ambiguity.** 42% of 5m trades have SL and TP inside the entry
   bar. The 1m control roughly halves the measured expectancy, so treat
   +0.10 R as the realistic figure.
5. **Single pair.** GBPUSD is flat. No cross-pair validation.
6. **Sample size.** 987 trades in the headline run; the standard error of
   expectancy is 0.067 R. The 95% interval is +0.10 … +0.37 R.

## 10. Files

- `ema200_breakout_exec5m.py` — engine: 30m signals, 5m/1m execution, variants,
  session/slope/ATR/invert filters, sweep, correct 1% sizing.
- `walkforward.py` — IS/OOS split runner.
- `session_scan.py` — exhaustive session-window scan on trade-level R.
- `grid_rr_slices.py`, `grid_eras.py`, `grid_fresh_rr3.py`,
  `grid_atr_era.py`, `grid_sensitivity.py`, `grid_regime.py`, `grid_filters.py`
  — ablations.
- `mfe.py` — excursion measurement (fixed-horizon; exit-bounded MFE is
  censored and must not be used to choose a target).
- `breakeven_study.py`, `grid_breakeven.py` — breakeven-stop analysis (rejected).
- `pool_1m.py` — pooled 1-minute era expectancy, t-stat, bootstrap CI.
- `significance.py`, `analyze.py`, `exits.py`, `plot_equity.py`.
- `RESEARCH_LOG.md` — chronological notes.
- `out/` — trade CSVs, equity CSVs, stats JSON, sweep CSVs, charts, logs.

Reproduce the headline result:

```
python ema200_breakout_exec5m.py --start 2018-01-01 --levels B \
    --session-start 12 --session-end 16 --no-fresh --rr 3.0 --tag s1216rr3b
python walkforward.py --side B --session-start 12 --session-end 16 \
    --no-fresh --rr 3.0
python ema200_breakout_exec5m.py --exec-tf 1m --start 2022-01-01 \
    --levels B --session-start 12 --session-end 16 --no-fresh --rr 3.0 \
    --tag m1s1216rr3full
python significance.py s1216rr3b m1s1216rr3full
python plot_equity.py s1216rr3b
```

Old-era data: `market_data/EURUSD/5m/yearly/eurusd_5m_2007..2017.csv` were
rebuilt from the 1m files in the same repository (same source, resampled).
