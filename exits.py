"""Exit-reason breakdown for arbitrary tags."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(r"E:\FOREX INTEL\research_strats\fx30_breakout\out")
PIP = 1e-4
KEYS = ["A_tight_level", "B_wide_body", "C_close_level"]


def load(tag: str, key: str) -> pd.DataFrame:
    t = pd.read_csv(OUT / f"exec5m_trades_{tag}_{key}.csv", parse_dates=["EntryTime"])
    sign = np.where(t.Size > 0, 1, -1)
    t["pips"] = (t.ExitPrice - t.EntryPrice) * sign / PIP
    return t


def reason(t: pd.DataFrame) -> pd.Series:
    tol = 0.2e-4
    return np.where((t.ExitPrice - t.TP).abs() <= tol, "TP",
                    np.where((t.ExitPrice - t.SL).abs() <= tol, "SL", "gap/other"))


for tag in sys.argv[1:]:
    print(f"=== {tag}")
    for key in KEYS:
        t = load(tag, key)
        if t.empty:
            continue
        t["reason"] = reason(t)
        g = t.groupby("reason").agg(n=("pips", "size"), pips=("pips", "sum"))
        g["share_%"] = (100 * g.n / len(t)).round(1)
        print(key, f"n={len(t)}")
        print(g.round(1).to_string())
        print("  trades held <=1 exec bar:",
              round(100 * (t.ExitBar - t.EntryBar <= 1).mean(), 1), "%")
