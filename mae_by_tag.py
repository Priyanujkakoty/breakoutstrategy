"""Per-trade adverse excursion (exit-bounded) for a given tag."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ema200_breakout_exec5m import load_bars  # noqa: E402

OUT = HERE / "out"
SPECS = {
    "s1216rr3b": ("5m", "2018-01-01", None),
    "m1s1216rr3full": ("1m", "2022-01-01", None),
    "m1_2018_2020_rr3": ("1m", "2018-01-01", "2020-12-31"),
}


def run(tag: str) -> None:
    tf, start, end = SPECS[tag]
    t = pd.read_csv(OUT / f"exec5m_trades_{tag}_B_wide_body.csv",
                    parse_dates=["EntryTime"])
    df = load_bars(tf, start, end)
    hi, lo = df.High.to_numpy(), df.Low.to_numpy()
    sign = np.where(t.Size > 0, 1, -1)
    risk = (t.EntryPrice - t.SL).abs().to_numpy()
    entry = t.EntryPrice.to_numpy()
    mae = np.empty(len(t))
    for k in range(len(t)):
        a, b = int(t.EntryBar.iloc[k]), int(t.ExitBar.iloc[k])
        if sign[k] > 0:
            mae[k] = (entry[k] - lo[a:b + 1].min()) / risk[k]
        else:
            mae[k] = (hi[a:b + 1].max() - entry[k]) / risk[k]
    # alignment check against the entry time recorded by the engine
    df_times = df.index.to_numpy()
    bad = 0
    for k in range(len(t)):
        if df_times[int(t.EntryBar.iloc[k])] != t.EntryTime.iloc[k].to_datetime64():
            bad += 1
    out = t[["EntryTime"]].copy()
    out["mae_R"] = np.maximum(mae, 0.0)
    out.to_csv(OUT / f"mae_{tag}.csv", index=False)
    print(f"{tag}: n {len(t)}  alignment mismatches {bad}  "
          f"mae median {np.median(mae):.2f}  p95 {np.percentile(mae, 95):.2f}  "
          f"max {mae.max():.2f}")


if __name__ == "__main__":
    for tag in (sys.argv[1:] or list(SPECS)):
        run(tag)
