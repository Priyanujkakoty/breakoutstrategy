"""Pool the non-overlapping 1-minute era runs into one expectancy estimate."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

TAGS = ["m1_2012_2014_rr3", "m1_2015_2017_rr3", "m1_2018_2020_rr3",
        "m1s1216rr3full"]

parts = []
for tag in TAGS:
    f = OUT / f"exec5m_trades_{tag}_B_wide_body.csv"
    if not f.exists():
        print(f"missing {f}")
        continue
    t = pd.read_csv(f, parse_dates=["EntryTime"])
    t["tag"] = tag
    parts.append(t)

t = pd.concat(parts, ignore_index=True)
sign = np.where(t.Size > 0, 1, -1)
pips = (t.ExitPrice - t.EntryPrice) * sign / 1e-4
risk = (t.EntryPrice - t.SL).abs() / 1e-4
r = (pips / risk).to_numpy()

n = len(r)
mean = r.mean()
sd = r.std(ddof=1)
se = sd / np.sqrt(n)
tstat = mean / se
# bootstrap CI
rng = np.random.default_rng(7)
boot = rng.choice(r, size=(20000, n), replace=True).mean(axis=1)
lo, hi = np.quantile(boot, [0.025, 0.975])

print(f"pooled 1m trades {n}")
print(f"  exp_R {mean:+.4f}  sd {sd:.3f}  t {tstat:.2f}")
print(f"  bootstrap 95% CI {lo:+.4f} .. {hi:+.4f}")
print()
print(t.assign(R=r).groupby("tag").agg(
    n=("R", "size"), win=("R", lambda x: round(100 * (x > 0).mean(), 1)),
    expR=("R", "mean")).round(4).to_string())

year = t.EntryTime.dt.year
g = pd.DataFrame({"year": year, "R": r}).groupby("year").agg(
    n=("R", "size"), expR=("R", "mean"))
g["t"] = (g.expR / (pd.DataFrame({"y": year, "R": r}).groupby("y").R.std()
                    / np.sqrt(g.n))).to_numpy()
print()
print(g.round(3).to_string())
