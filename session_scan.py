"""Exhaustive session-window scan on trade-level R, IS vs OOS.

Uses the all-hours trade log, so every window is a simple filter of the same
trades. No re-backtest needed: the session gate only decides whether a stop
order may be placed, so per-trade R is unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(r"E:\FOREX INTEL\research_strats\fx30_breakout\out")
PIP = 1e-4
KEYS = ["A_tight_level", "B_wide_body", "C_close_level"]


def load(tag: str, key: str) -> pd.DataFrame:
    p = OUT / f"exec5m_trades_{tag}_{key}.csv"
    t = pd.read_csv(p, parse_dates=["EntryTime", "ExitTime"])
    s = np.where(t.Size > 0, 1, -1)
    t["pips"] = (t.ExitPrice - t.EntryPrice) * s / PIP
    t["risk_pips"] = (t.EntryPrice - t.SL).abs() / PIP
    t["R"] = t.pips / t.risk_pips
    t["year"] = t.EntryTime.dt.year
    t["hour"] = t.EntryTime.dt.hour
    return t


def stats(r: np.ndarray) -> tuple[float, float, int]:
    if len(r) < 10:
        return np.nan, np.nan, len(r)
    sd = r.std(ddof=1)
    t = r.mean() / (sd / np.sqrt(len(r))) if sd > 0 else np.nan
    return r.mean(), t, len(r)


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "nofresh"
    key = sys.argv[2] if len(sys.argv) > 2 else "B_wide_body"
    t = load(tag, key)
    is_ = t[t.year <= 2022]
    oos = t[t.year >= 2023]
    print(f"{tag} {key}: n={len(t)}  IS n={len(is_)}  OOS n={len(oos)}")
    print(f"  full-sample expR={t.R.mean():+.3f}  IS={is_.R.mean():+.3f}  OOS={oos.R.mean():+.3f}")

    rows = []
    for a in range(7, 17):
        for b in range(a + 1, 19):
            w = lambda d: d[(d.hour >= a) & (d.hour < b)]
            mi, ti, ni = stats(w(is_).R.to_numpy())
            mo, to, no = stats(w(oos).R.to_numpy())
            mf = w(t).R.mean()
            rows.append(dict(start=a, end=b, n_full=len(w(t)),
                             exp_full=mf, n_is=ni, exp_is=mi, t_is=ti,
                             n_oos=no, exp_oos=mo, t_oos=to))
    d = pd.DataFrame(rows)
    d.to_csv(OUT / f"session_scan_{tag}_{key}.csv", index=False)

    ok = d[(d.n_is >= 100) & (d.n_oos >= 80)].copy()
    print(f"\nwindows with >=100 IS and >=80 OOS trades: {len(ok)}")
    print("\nBOTH IS>0 and OOS>0, sorted by min(IS,OOS) expectancy")
    both = ok[(ok.exp_is > 0) & (ok.exp_oos > 0)].copy()
    both["worst"] = both[["exp_is", "exp_oos"]].min(axis=1)
    print(both.sort_values("worst", ascending=False)
          .head(20)[["start", "end", "n_full", "exp_full", "n_is", "exp_is", "t_is",
                     "n_oos", "exp_oos", "t_oos"]].round(3).to_string(index=False))

    print(f"\nshare of all windows with IS>0: {(ok.exp_is > 0).mean():.0%}")
    print(f"share of all windows with OOS>0: {(ok.exp_oos > 0).mean():.0%}")
    print(f"share with both >0: {((ok.exp_is > 0) & (ok.exp_oos > 0)).mean():.0%}")
    print(f"correlation IS vs OOS expectancy: {ok.exp_is.corr(ok.exp_oos):.2f}")


if __name__ == "__main__":
    main()
