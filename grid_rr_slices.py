"""Final validation: RR sweep on 3-year slices, correct 1% risk sizing."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ema200_breakout_exec5m import build_arrays, load_bars, run_one  # noqa: E402

OUT = HERE / "out"
V = {"B": dict(sl_mode="body", entry_mode="stop")}
base = dict(ema_n=200, atr_n=14, pivot_n=10, pb_window=25, pb_atr=0.5,
            pb_recency=25, buf_pips=1.0, rr=3.0, risk_pct=0.01, max_hold=0,
            max_risk_atr=1.5, level_max_age=120, both_sides=True,
            require_fresh_pullback=False, require_fresh_level=False,
            session_start=12, session_end=16, max_dist_atr=0.0, min_stop_pips=1.0,
            min_slope_atr=-1.0, max_atr_ratio=0.0, max_atr_ratio_long=0.0,
            invert=False)

SLICES = [("2018-2020", "2018-01-01", "2020-12-31"),
          ("2021-2023", "2021-01-01", "2023-12-31"),
          ("2024-2026", "2024-01-01", "2026-11-03")]

rows = []
for label, start, end in SLICES:
    df = load_bars("5m", start, end)
    for rr in (2.0, 3.0, 4.0, 5.0):
        cfg = {**base, **V["B"], "rr": rr}
        arrays = build_arrays(df, cfg)
        res = run_one(df, arrays, cfg, 0.2)
        e, st = res["extra"], res["stats"]
        row = {"slice": label, "rr": rr, "n": e["trades"],
               "win_%": e.get("win_rate_%"), "pf": st.get("Profit Factor"),
               "exp_R": e.get("expectancy_R"),
               "ret_%": st.get("Return [%]"),
               "dd_%": st.get("Max. Drawdown [%]")}
        rows.append(row)
        print(f"{label} rr={rr:.1f} n={row['n']:4d} win={row['win_%']:.1f} "
              f"pf={row['pf']:.2f} expR={row['exp_R']:+.3f} "
              f"ret={row['ret_%']:.0f}% dd={row['dd_%']:.0f}%", flush=True)

d = pd.DataFrame(rows)
d.to_csv(OUT / "grid_rr_slices.csv", index=False)
print()
print(d.pivot(index="rr", columns="slice", values="exp_R").round(3).to_string())
print(d.pivot(index="rr", columns="slice", values="n").to_string())
