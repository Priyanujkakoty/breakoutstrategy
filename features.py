"""Win rate / expectancy by entry feature bucket, for filter discovery."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(r"E:\FOREX INTEL\research_strats\fx30_breakout\out")
PIP = 1e-4
KEYS = ["A_tight_level", "B_wide_body"]


def load(tag: str, key: str) -> pd.DataFrame:
    t = pd.read_csv(OUT / f"exec5m_trades_{tag}_{key}.csv", parse_dates=["EntryTime"])
    sign = np.where(t.Size > 0, 1, -1)
    t["sign"] = sign
    t["risk_pips"] = (t.EntryPrice - t.SL).abs() / PIP
    t["pips"] = (t.ExitPrice - t.EntryPrice) * sign / PIP
    t["R"] = t.pips / t.risk_pips
    t["hour"] = t.EntryTime.dt.hour
    t["dow"] = t.EntryTime.dt.dayofweek
    atr = t.Entry_ATR14_30m.replace(0, np.nan)
    t["risk_atr"] = t.risk_pips * PIP / atr
    t["dist_ema_atr"] = (t.EntryPrice - t.Entry_EMA200_30m).abs() / atr
    t["gap_to_level_atr"] = np.where(
        t.sign > 0,
        (t.EntryPrice - t.Entry_SwingHigh30m),
        (t.Entry_SwingLow30m - t.EntryPrice),
    ) / atr
    t["level_age"] = np.where(t.sign > 0, t.Entry_SwingHighAge, t.Entry_SwingLowAge)
    return t


def table(t: pd.DataFrame, col: str, q: int = 5) -> None:
    x = t[col].replace([np.inf, -np.inf], np.nan)
    if x.notna().sum() < 50:
        return
    try:
        bins = pd.qcut(x, q, duplicates="drop")
    except ValueError:
        return
    g = t.groupby(bins, observed=True).agg(
        n=("R", "size"), win=("pips", lambda s: 100 * (s > 0).mean()),
        expR=("R", "mean"), sd=("R", "std"))
    g["t"] = g.expR / (g.sd / np.sqrt(g.n))
    g["expR"] = g.expR.round(3)
    g["win"] = g.win.round(1)
    g["t"] = g.t.round(2)
    print(f"\n  by {col}")
    print("  " + g[["n", "win", "expR", "t"]].to_string().replace("\n", "\n  "))


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "nofresh"
    for key in KEYS:
        t = load(tag, key)
        if t.empty:
            continue
        print(f"\n===== {tag} {key}  n={len(t)}  expR={t.R.mean():.3f}")
        for col in ("hour", "risk_atr", "dist_ema_atr", "gap_to_level_atr", "level_age"):
            table(t, col)
        # session buckets
        s = pd.cut(t.hour, [-1, 6, 11, 16, 21, 23],
                   labels=["00-06 Asia", "07-11 London", "12-16 NY", "17-21 late", "22-23"])
        g = t.groupby(s, observed=True).agg(
            n=("R", "size"), win=("pips", lambda x: 100 * (x > 0).mean()),
            expR=("R", "mean"), sd=("R", "std"))
        g["t"] = (g.expR / (g.sd / np.sqrt(g.n))).round(2)
        print("\n  by session")
        print("  " + g.assign(win=g.win.round(1), expR=g.expR.round(3))[["n", "win", "expR", "t"]]
              .to_string().replace("\n", "\n  "))


if __name__ == "__main__":
    main()
