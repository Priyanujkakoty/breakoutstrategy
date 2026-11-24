"""Does a long-window volatility cap rescue the bad era and keep the good ones?"""

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

SLICES = [("2012-2014", "2012-01-01", "2014-12-31"),
          ("2015-2017", "2015-01-01", "2017-12-31"),
          ("2022-2024", "2022-01-01", "2024-12-31")]

rows = []
cache = {}
for label, start, end in SLICES:
    df = cache.setdefault((start, end), load_bars("5m", start, end))
    for cap in (0.0, 1.0, 1.2, 1.5):
        cfg = {**base, **V["B"], "max_atr_ratio_long": cap}
        arrays = build_arrays(df, cfg)
        res = run_one(df, arrays, cfg, 0.2)
        e, st = res["extra"], res["stats"]
        row = {"slice": label, "cap": cap, "n": e["trades"],
               "win_%": e.get("win_rate_%"), "pf": st.get("Profit Factor"),
               "exp_R": e.get("expectancy_R"),
               "ret_%": st.get("Return [%]"),
               "dd_%": st.get("Max. Drawdown [%]")}
        rows.append(row)
        print(f"{label} cap={cap:3.1f} n={row['n']:4d} win={row['win_%']:.1f} "
              f"pf={row['pf']:.2f} expR={row['exp_R']:+.3f} "
              f"ret={row['ret_%']:.0f}% dd={row['dd_%']:.0f}%", flush=True)

d = pd.DataFrame(rows)
d.to_csv(OUT / "grid_atr_cap.csv", index=False)
print()
print(d.pivot(index="cap", columns="slice", values="exp_R").round(3).to_string())
print(d.pivot(index="cap", columns="slice", values="n").to_string())
