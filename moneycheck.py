"""MONEYCHECK - Aqua Funded 5k 2-step Pro simulation.

Rules supplied by the user: 10% phase-1 target, 5% daily drawdown, 10% overall
drawdown, both trailing, $15 fee, 80% profit split, 14-day payout cycle.
Assumptions NOT supplied (flag them):
  * phase-2 target 5%
  * overall DD trails peak equity, floor capped at initial balance
  * daily DD measured from day-start equity, closed + intrabar MAE stress
  * 14-day cycle = 10 trading days, profit above start withdrawn, balance reset
  * no minimum trading days, no consistency rule, no time limit

Conservative mode caps every win at +3R (no favourable gap fills) while leaving
losses as recorded.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

INIT = 5_000.0
FEE = 15.0
SPLIT = 0.80
P1_TARGET = 0.10
P2_TARGET = float(__import__("os").environ.get("MC_P2", "0.05"))
DAILY_DD = 0.05
TOTAL_DD = 0.10
TRAIL_CAP = __import__("os").environ.get("MC_TRAIL_CAP", "1") == "1"
CYCLE_DAYS = 10
MAX_CYCLES = 6
MAX_DAYS = 60
SEED = 11


def load_trades(tag: str, cap: float = 0.0) -> pd.DataFrame:
    f = OUT / f"exec5m_trades_{tag}_B_wide_body.csv"
    t = pd.read_csv(f, parse_dates=["EntryTime"])
    sign = np.where(t.Size > 0, 1, -1)
    r = (t.ExitPrice - t.EntryPrice) * sign / 1e-4 / ((t.EntryPrice - t.SL).abs() / 1e-4)
    if cap > 0:
        r = np.minimum(r, cap)
    t["R"] = r
    t["day"] = t.EntryTime.dt.floor("D")
    m = OUT / f"mae_{tag}.csv"
    if m.exists():
        mae = pd.read_csv(m, parse_dates=["EntryTime"])["mae_R"].to_numpy()
        if len(mae) == len(t):
            t["mae_R"] = mae
        else:
            t["mae_R"] = 1.0
    else:
        t["mae_R"] = 1.0
    # intrabar adverse excursion used for the daily-limit check
    t["worst_R"] = np.where(t.R < 0, np.minimum(t.R, -1.0),
                            -np.minimum(t.mae_R, 1.0))
    return t[["day", "R", "worst_R"]].sort_values("day").reset_index(drop=True)


def day_blocks(t: pd.DataFrame) -> list[np.ndarray]:
    return [g[["R", "worst_R"]].to_numpy() for _, g in t.groupby("day", sort=True)]


def simulate_challenge(blocks, risk: float, rng):
    equity = INIT
    peak = INIT
    floor = INIT * (1 - TOTAL_DD)
    p1 = False
    days = 0
    max_dd = 0.0

    while days < 4000:
        blk = blocks[rng.integers(len(blocks))]
        day_start_eq = equity
        day_floor = day_start_eq - INIT * DAILY_DD
        for r, worst in blk:
            start_eq = equity
            floating = start_eq * (1 + worst * risk)
            if floating <= day_floor or floating <= floor:
                return dict(passed=False, days=days, max_dd=max_dd)
            equity += r * risk * start_eq
            dd = (equity - peak) / INIT
            if dd < max_dd:
                max_dd = dd
            if equity > peak:
                peak = equity
                floor = min(peak - INIT * TOTAL_DD, INIT) if TRAIL_CAP else peak - INIT * TOTAL_DD
            if equity <= day_floor or equity <= floor:
                return dict(passed=False, days=days, max_dd=max_dd)
            if not p1:
                if equity >= INIT * (1 + P1_TARGET):
                    p1 = True
                    equity, peak = INIT, INIT
                    floor = INIT * (1 - TOTAL_DD)
                    break
            else:
                if equity >= INIT * (1 + P2_TARGET):
                    return dict(passed=True, days=days, max_dd=max_dd)
        days += 1
    return dict(passed=False, days=days, max_dd=max_dd)


def simulate_funded(blocks, risk: float, rng):
    equity = INIT
    peak = INIT
    floor = INIT * (1 - TOTAL_DD)
    payouts = []
    day = 0
    cycle_start_day = 0
    max_dd = 0.0
    first_payout_day = None

    while day < MAX_DAYS and len(payouts) < MAX_CYCLES:
        blk = blocks[rng.integers(len(blocks))]
        day_start_eq = equity
        day_floor = day_start_eq - INIT * DAILY_DD
        for r, worst in blk:
            start_eq = equity
            floating = start_eq * (1 + worst * risk)
            if floating <= day_floor or floating <= floor:
                return dict(payouts=payouts, max_dd=max_dd)
            equity += r * risk * start_eq
            dd = (equity - peak) / INIT
            if dd < max_dd:
                max_dd = dd
            if equity > peak:
                peak = equity
                floor = min(peak - INIT * TOTAL_DD, INIT) if TRAIL_CAP else peak - INIT * TOTAL_DD
            if equity <= day_floor or equity <= floor:
                return dict(payouts=payouts, max_dd=max_dd)
        day += 1
        if day - cycle_start_day >= CYCLE_DAYS:
            profit = equity - INIT
            if profit > 0:
                payouts.append(SPLIT * profit)
                equity, peak = INIT, INIT
                floor = INIT * (1 - TOTAL_DD)
            # a losing cycle is NOT refunded: the balance carries forward
            cycle_start_day = day
    return dict(payouts=payouts, max_dd=max_dd)


def historical_breach(t: pd.DataFrame, risk: float) -> dict:
    equity = INIT
    peak = INIT
    worst_dd = 0.0
    worst_day = 0.0
    day_start = INIT
    day = None
    for row in t.itertuples():
        if day is not None and row.day != day:
            day_start = equity
        day = row.day
        floating = equity * (1 + row.worst_R * risk)
        worst_day = min(worst_day, (floating - day_start) / INIT)
        equity += row.R * risk * equity
        peak = max(peak, equity)
        worst_dd = min(worst_dd, (equity - peak) / INIT)
    return dict(max_dd=worst_dd, worst_day=worst_day,
                limit_multiple=abs(worst_dd) / TOTAL_DD)


def run(tag: str, cap: float, n_paths: int, risks) -> pd.DataFrame:
    t = load_trades(tag, cap)
    blocks = day_blocks(t)
    hist = historical_breach(t, 0.002)  # replaced per risk below
    rows = []
    rng = np.random.default_rng(SEED)
    for risk in risks:
        breach = historical_breach(t, risk)
        passed = surv = 0
        payouts = []
        npayouts = []
        days_to_pass = []
        for _ in range(n_paths):
            c = simulate_challenge(blocks, risk, rng)
            if c["passed"]:
                passed += 1
                days_to_pass.append(c["days"])
                f = simulate_funded(blocks, risk, rng)
                payouts.append(sum(f["payouts"]))
                npayouts.append(len(f["payouts"]))
                if f["payouts"]:
                    surv += 1
            else:
                payouts.append(0.0)
                npayouts.append(0)
        p_pass = passed / n_paths
        p_surv = surv / n_paths
        exp_payout = float(np.mean(payouts))
        rows.append(dict(tag=tag, cap=cap, risk=risk * 100,
                         p_pass=100 * p_pass, survival=100 * p_surv,
                         attempts=1 / p_surv if p_surv > 0 else np.nan,
                         hist_dd=100 * breach["max_dd"],
                         hist_dd_mult=breach["limit_multiple"],
                         hist_day=100 * breach["worst_day"],
                         exp_payout=exp_payout, net=exp_payout - FEE,
                         exp_npayouts=float(np.mean(npayouts)),
                         med_days=np.median(days_to_pass) if days_to_pass else np.nan,
                         n_pass=passed))
        print(f"  risk {risk*100:.2f}%  pass {100*p_pass:5.1f}%  "
              f"surv {100*p_surv:5.1f}%  histDD {100*breach['max_dd']:6.1f}% "
              f"(x{breach['limit_multiple']:.2f})  worstDay {100*breach['worst_day']:5.1f}%  "
              f"E[payout] ${exp_payout:7.2f}  net ${exp_payout - FEE:7.2f}  "
              f"med {np.median(days_to_pass) if days_to_pass else 0:.0f}d", flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "s1216rr3b"
    cap = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 5000
    label = "conservative" if cap > 0 else "realistic"
    print(f"{tag} ({label}, cap={cap}): {n} paths")
    risks = (0.001, 0.002, 0.003, 0.004, 0.005)
    one = __import__("os").environ.get("MC_RISK")
    if one:
        risks = (float(one),)
    d = run(tag, cap, n, risks)
    d.to_csv(OUT / f"moneycheck_{tag}_cap{cap}.csv", index=False)
    print()
    print(d.round(2).to_string(index=False))
