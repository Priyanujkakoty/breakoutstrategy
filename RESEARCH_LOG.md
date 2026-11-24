# Research log — EURUSD 30m 200-EMA pullback breakout

Running notes, newest last. Every number here comes from the engine in this
folder; commands are at the bottom.

## 1. Baseline (rules as written)

5m execution, 2018-2026, 0.2 pip/side. All hours, no extra filters:

| Variant | n | win% | PF | exp R | t |
|---|---|---|---|---|---|
| A tight | 4,988 | 39.2 | 0.92 | −0.066 | −2.42 |
| B wide | 2,767 | 39.8 | 1.01 | −0.028 | −0.98 |
| C close | 1,577 | 34.3 | 0.83 | −0.144 | −4.49 |

Zero spread: A +0.030, B +0.021, C −0.107. The raw signal has at most a tiny
edge; costs remove it.

## 2. Payoff geometry

MFE measured to exit is censored (a trade that exits at 1.5R cannot show 2R).
Do not use it to choose the target. Direct backtests:

| RR | n | win% | PF | exp R |
|---|---|---|---|---|
| 1.5 | 1,057 | 44.3 | 1.21 | +0.093 |
| 2.0 | 1,022 | 38.9 | 1.21 | +0.142 |

Breakeven at 2R is 33.3%, and the setup delivers 38.9%. The 2R target is
better than 1.5R on the same entries.

## 3. Session filter (the main finding)

Losses concentrate in the London morning (07-11 UTC). The NY morning
(12-16 UTC) is positive. From the all-hours trade log (2,767 B trades):

| Window UTC | n | win% | PF | exp R |
|---|---|---|---|---|
| all | 2,767 | 39.8 | 1.01 | −0.028 |
| 07-11 | 665 | 36.4 | 0.86 | −0.130 |
| 11-16 | 1,208 | 43.5 | 1.15 | +0.066 |
| 12-16 | 1,057 | 44.3 | 1.21 | +0.093 |
| 09-12 | 521 | 37.2 | 0.85 | −0.134 |

Exhaustive scan of all 4-hour windows (59 windows with enough trades):
- positive in-sample: 34%, positive out-of-sample: 58%, both: 31%
- IS-vs-OOS expectancy correlation across windows: 0.71
- of the 8 non-overlapping 4-hour windows: 3 positive IS, 5 positive OOS,
  both positive only for 11-15 and 12-16; 07-11 and 08-12 are significantly
  negative in both halves.

So the stable fact is "London morning loses, NY morning does not". The exact
12-16 cell is the best of 8 overlapping candidates, so treat its point estimate
as upward-biased.

Walk-forward, B, no freshness filter, 0.2 pip/side:

| Window | IS 2018-2022 | OOS 2023-2026 |
|---|---|---|
| 11-16 | +0.034 R (n 674, t 0.7) | +0.107 R (n 534, t 1.9) |
| 12-16 | +0.057 R (n 590, t 0.9) | +0.139 R (n 467, t 2.0) |

## 4. Sizing bug (fixed)

`_size` divided by `equity / leverage`, but backtesting.py fills
`margin_available * leverage * size / price` units. Every trade therefore ran
at 99% of maximum notional — up to ~50× equity — not at 1% risk. R multiples
were unaffected, but all earlier return and drawdown figures were inflated and
risk per trade varied with stop width.

Corrected sizing verified: mean loss on stop-outs = 1.002% of equity.

Corrected results, B, 12-16, 5m, 2018-2026:

- return +132.6%, CAGR 10.0%, max DD −29.1%, Sharpe 0.49, PF 1.21
- 1,057 trades, win 44.3%, expectancy +0.093 R
- yearly: 2018 +16.2, 2019 +23.8, 2020 −8.0, 2021 +10.1, 2022 −11.8,
  2023 +42.8, 2024 +22.5, 2025 +1.2, 2026 +2.3

A tight on the same window and sizing: −54.5%, expectancy −0.023 R.

## 5. Filters that did not help

- EMA slope >= 0: +0.022 R (vs +0.066 baseline)
- ATR / 100-bar mean ATR <= 1.0: −0.006 R, cuts trades to 121
- 7-11 UTC: −0.130 R
- 09-12 UTC: −0.134 R

## 6. Transfer to other data

- GBPUSD, B, 12-16, 5m 2018-2026: −0.043 R, PF 0.98, −87.5% (old sizing)
- GBPUSD, B, 12-15: −0.008 R, PF 1.01
- GBPUSD, B, 12-16, RR 3.0: +0.027 R, PF 1.05, +5.9%, DD −45%
- EURUSD 1m 2022-2026, B, 12-15, no-fresh: +0.120 R, t 2.30, n 692,
  PF 1.33; yearly 2022 +0.10, 2023 +0.23, 2024 +0.18, 2025 +0.07, 2026 −0.01
- EURUSD 1m 2007-2017 (never used for selection): −0.209 R, PF 0.96, −97.7%
- 5m rebuilt from 1m for 2007-2017 reproduces it: −0.216 R, PF 1.02

The edge does not transfer to GBPUSD.

## 7. Era dependence

3-year slices, B, 12-16, no-fresh, 0.2 pip/side, expectancy in R:

| Config | 2012-2014 | 2015-2017 | 2018-2020 | 2021-2023 | 2022-2024 | 2024-2026 |
|---|---|---|---|---|---|---|
| RR 1.5 | +0.047 | −0.256 | — | — | +0.128 | — |
| RR 2.0 | — | — | +0.175 | +0.118 | — | +0.158 |
| RR 3.0 | +0.177 | −0.222 | +0.355 | +0.169 | +0.192 | +0.226 |
| RR 4.0 | — | — | +0.559 | +0.102 | — | +0.187 |
| RR 5.0 | — | — | +0.622 | +0.187 | — | +0.304 |

Facts:
- raising the target improves every era tested (RR3 > RR1.5 in all three)
- 2015-2017 loses at every target
- 2012-2014 and 2018-2026 are positive at RR3
- 5m full 2007-2026 at RR3: +0.046 R, PF 1.21, n 2,062, +76.9% (old sizing)

Fade (invert) loses everywhere: −0.73 R modern, −1.11 R 2012-2014,
−1.22 R 2015-2017, −0.61 R on 1m ancient. The breakout direction is correct.

Filters rejected: EMA slope, ATR/100-bar mean, ATR/1000-bar mean (all reduce
expectancy), 07-11 UTC session (−0.02 to −0.14 R in every era).

## 8. 1-minute era record

Same config (B, 12-16 UTC, RR 3.0, no-fresh) on 1-minute execution, which
removes the 5m same-bar ambiguity:

| Period | n | win % | PF | exp R | return | max DD |
|---|---|---|---|---|---|---|
| 2012-2014 | 364 | 26.4 | 1.32 | +0.040 | +14.7% | −29.6% |
| 2015-2017 | 429 | 29.4 | 1.01 | −0.025 | −33.7% | −63.0% |
| 2018-2020 | 380 | 32.1 | 1.49 | +0.245 | +132.3% | −23.1% |
| 2022-2024 | 474 | 28.1 | 1.14 | +0.116 | +59.8% | −27.3% |
| 2022-2026 | 756 | 28.6 | 1.18 | +0.132 | +135.0% | −27.3% |

Every calendar year in the 1m 2022-2026 run is positive (2022 +1.2%,
2023 +18.7%, 2024 +47.0%, 2025 +20.1%, 2026 +10.8%).

The 5m failure numbers for 2015-2017 (−0.222 R) are much worse than the 1m
record (−0.025 R). The 5m run both flatters the good years and exaggerates the
bad ones. On 1m, the only era that is not positive is 2015-2017, and it is
essentially flat.

Pooled over the non-overlapping 1m slices (2012-2014, 2015-2017, 2018-2020,
2022-2026): n 1,929, exp R +0.102, sd 2.27, t 1.98, bootstrap 95% CI
−0.003 .. +0.200. This is the most conservative estimate of the edge.

## 9. Breakeven stop rejected

Move SL to entry after price reaches X R. 5m 2018-2026, RR 3.0:

| BE trigger | n | PF | return | max DD |
|---|---|---|---|---|
| off | 987 | 1.28 | +697% | −24% |
| +1.0 R | 1,096 | 1.26 | +367% | −30% |
| +1.5 R | 1,040 | 1.26 | +410% | −30% |
| +2.0 R | 1,011 | 1.26 | +478% | −30% |

42% of losers do touch +1R before stopping (28% touch +1.5R), but the rule
gives up too much: many winners retrace to entry after 1R and then run to 3R.
`expectancy_R` is not comparable for the BE rows because the recorded stop,
and therefore the measured risk, moves with the rule; compare PF/return/DD.

## 10. MONEYCHECK - Aqua Funded 5k 2-Step Pro

Rules: 10% P1, 5% P2 (assumed), 5% daily DD, 10% overall DD, both trailing
(capped at initial balance), $15 fee, 80% split, 14-day payout cycle modelled
as 10 trading days. Block bootstrap over trading-day blocks, conservative
wins capped at +3R, daily limit stressed with per-trade MAE.

| Risk | dataset | pass | survival | hist maxDD | E[payout] | net/attempt | med days |
|---|---|---|---|---|---|---|---|
| 0.20% | 5m 2018-2026 | 97.1% | 92.0% | -7.8% | $195 | +$180 | 190 |
| 0.20% | 1m 2022-2026 | 89.4% | 81.6% | -6.2% | $158 | +$143 | 217 |
| 0.30% | 5m | 88.4% | 83.7% | -13.2% | $263 | +$248 | 116 |
| 0.50% | 5m | 68.7% | 63.1% | -27.6% | $341 | +$326 | 53 |

Verdict: GOOD CANDIDATE at 0.20% risk. Above 0.2% the historical drawdown
exceeds the 10% limit (0.3% -> 1.32x, 0.5% -> 2.76x), so the simulated pass
rates at those levels are not investable. Rule sensitivity at 0.2%: P2 at 10%
gives 95.6% pass / 91.2% survival; uncapped trailing gives 97.6% / 92.5%.
Report: MONEYCHECK.md.
