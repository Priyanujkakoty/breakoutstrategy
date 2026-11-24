# MONEYCHECK — Aqua Funded 5k 2-Step Pro

Strategy: EURUSD 30m EMA200 pullback + swing breakout, variant B, 12:00–16:00
UTC, 3R target, 1% risk baseline (re-sized here per scenario).

## Firm rules used

| Item | Value |
|---|---|
| Account | $5,000 |
| Structure | 2-step Pro |
| Phase 1 target | 10% |
| Phase 2 target | 5% (assumed — confirm) |
| Daily drawdown | 5%, trailing |
| Overall drawdown | 10%, trailing, floor capped at initial balance |
| Fee | $15 |
| Profit split | 80% |
| Payout cycle | 14 days (modelled as 10 trading days) |

Other assumptions, none supplied: no minimum trading days, no consistency
rule, no time limit, unlimited retries, payout = 80% of profit above the
$5,000 starting balance at cycle end, balance resets after a payout, losses
carry forward across losing cycles, funded horizon capped at 60 trading days.

## Method

- Trades resampled from the real logs: 987 trades (5m 2018–2026) and 756
  trades (1m 2022–2026), grouped into trading-day blocks; block bootstrap of
  10 consecutive days preserves clustering.
- Conservative scenario: every win capped at +3R (removes favourable gap
  fills of +12R and +20R), losses kept as recorded.
- Daily-limit check uses intrabar adverse excursion (MAE) per trade, capped at
  1R for winners; overall limit uses closed-equity peak.
- 50,000-path requirement: not practical in this harness; the final config was
  run with 20,000 paths and the sweep with 3,000. Binomial standard error at
  20,000 paths is ≤0.35 percentage points.

## Result — 5m log (realistic entries)

Conservative (wins capped at 3R), $15 fee, 80% split:

| Risk/trade | P1 pass | P2 pass | Overall pass | Survival (pass + ≥1 payout) | Grade | Hist. max DD | Breach | E[payout]/attempt | Net/attempt | Median days to pass |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.10% | 99.9% | 99.9% | 99.9% | 95.1% | Strong | 3.5% | Pass (0.35×) | $101 | +$86 | 400 |
| **0.20%** | **98.1%** | **99.0%** | **97.1%** | **92.0%** | **Strong** | **7.8%** | **Pass (0.78×)** | **$195** | **+$180** | **190** |
| 0.30% | — | — | 88.4% | 83.7% | Good | 13.2% | FAIL (1.32×) | $263 | +$248 | 116 |
| 0.40% | — | — | 77.3% | 72.7% | Acceptable | 19.7% | FAIL (1.97×) | $312 | +$297 | 74 |
| 0.50% | — | — | 68.7% | 63.1% | REJECT | 27.6% | FAIL (2.76×) | $341 | +$326 | 53 |

Risk above 0.2% is disqualified by the historical drawdown check regardless of
its simulated numbers (§7.3).

## Result — 1m log (honest execution, conservative)

| Risk/trade | Overall pass | Survival | Grade | Hist. max DD | Breach | E[payout]/attempt | Net/attempt | Median days |
|---|---|---|---|---|---|---|---|---|
| 0.10% | 99.6% | 90.8% | Strong | 3.1% | Pass (0.31×) | $89 | +$74 | 496 |
| **0.20%** | **89.4%** | **81.6%** | **Good** | **6.2%** | **Pass (0.62×)** | **$158** | **+$143** | **217** |
| 0.30% | 72.6% | 66.4% | REJECT | 9.5% | Pass (0.95×) | $193 | +$178 | 124 |
| 0.40% | 62.9% | 56.1% | REJECT | 12.8% | FAIL (1.28×) | $218 | +$203 | 72 |

## Rule sensitivities at 0.2% (5m log)

| Variant | Overall pass | Survival | Net/attempt |
|---|---|---|---|
| Base (P2 5%, trailing capped at initial) | 97.1% | 92.4% | +$183 |
| Phase-2 target 10% | 95.6% | 91.2% | +$177 |
| Trailing floor uncapped (keeps rising) | 97.6% | 92.5% | +$186 |

The conclusion is not sensitive to the two unknown rule details.

## Verdict

**GOOD CANDIDATE at 0.20% risk per trade.** Survival 81–92% depending on the
execution dataset, no historical breach, positive expected net cash in both
realistic and conservative scenarios, and stable across rule variants.

- Expected attempts per payout: 1.09 (5m) / 1.23 (1m).
- Expected fees per payout: $16 / $18.
- Funded failure before first payout (given a pass): 5.3% (5m) / 8.7% (1m).
- Median time to first payout: ~200 days to pass + 10 days to the first cycle.

## Weaknesses

1. 0.2% risk is very slow: ~9 months median to qualification at ~1.8 trades/day.
2. The only time-efficient settings (0.4–0.5%) breach the 10% limit in the
   historical record and are disqualified.
3. Pass probabilities are model output, not guarantees; the 1m result (81%) is
   the honest one and sits near the 80% band edge.
4. No floating-drawdown path is modelled beyond per-trade MAE stress; a real
   adverse spike can be worse.
5. News-gap fills beyond the 3R target are removed in the conservative runs but
   the 5m trade sequencing still contains same-bar ambiguity.
6. Single instrument, single broker feed, fixed 0.2 pip spread.
