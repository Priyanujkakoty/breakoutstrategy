"""Expectancy, t-stat and bootstrap CI per run/variant."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(r"E:\FOREX INTEL\research_strats\fx30_breakout\out")
PIP = 1e-4
KEYS = ["A_tight_level", "B_wide_body", "C_close_level"]
rng = np.random.default_rng(7)


def load(tag: str, key: str) -> pd.DataFrame:
    p = OUT / f"exec5m_trades_{tag}_{key}.csv"
    if not p.exists():
        return pd.DataFrame()
    t = pd.read_csv(p, parse_dates=["EntryTime"])
    if t.empty or len(t) < 5:
        return t.iloc[0:0]
    sign = np.where(t.Size > 0, 1, -1)
    t["risk_pips"] = (t.EntryPrice - t.SL).abs() / PIP
    t["pips"] = (t.ExitPrice - t.EntryPrice) * sign / PIP
    t["R"] = t.pips / t.risk_pips
    return t


def boot(x: np.ndarray, n: int = 10000) -> tuple[float, float]:
    idx = rng.integers(0, len(x), size=(n, len(x)))
    m = x[idx].mean(axis=1)
    return float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))


rows = []
for tag in sys.argv[1:]:
    for key in KEYS:
        t = load(tag, key)
        if t.empty:
            continue
        r = t.R.to_numpy()
        sd = r.std(ddof=1)
        tstat = r.mean() / (sd / np.sqrt(len(r)))
        lo, hi = boot(r)
        rows.append({
            "run": tag, "variant": key, "n": len(r),
            "win%": round(100 * (t.pips > 0).mean(), 1),
            "exp_R": round(r.mean(), 3),
            "sd_R": round(sd, 2),
            "t": round(tstat, 2),
            "ci_lo": round(lo, 3), "ci_hi": round(hi, 3),
            "exp_pips": round(t.pips.mean(), 3),
            "pips_total": round(t.pips.sum(), 0),
            "long%": round(100 * (t.Size > 0).mean(), 0),
            "hold_h": round(t.Duration.map(lambda d: pd.to_timedelta(d).total_seconds()).mean() / 3600, 2),
        })

df = pd.DataFrame(rows)
print(df.to_string(index=False))
df.to_csv(OUT / "significance.csv", index=False)
