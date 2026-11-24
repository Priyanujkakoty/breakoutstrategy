"""Era comparison on short 3-year slices (cheap, per user instruction)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ema200_breakout_exec5m import build_arrays, load_bars, run_one  # noqa: E402

OUT = HERE / "out"
V = {"A": dict(sl_mode="level", entry_mode="stop"),
     "B": dict(sl_mode="body", entry_mode="stop")}
base = dict(ema_n=200, atr_n=14, pivot_n=10, pb_window=25, pb_atr=0.5,
            pb_recency=25, buf_pips=1.0, rr=1.5, risk_pct=0.01, max_hold=0,
            max_risk_atr=1.5, level_max_age=120, both_sides=True,
            require_fresh_pullback=False, require_fresh_level=False,
            session_start=-1, session_end=-1, max_dist_atr=0.0, min_stop_pips=1.0,
            min_slope_atr=-1.0, max_atr_ratio=0.0, invert=False)

SLICES = [("ancient 2012-2014", "2012-01-01", "2014-12-31"),
          ("ancient 2015-2017", "2015-01-01", "2017-12-31"),
          ("modern 2022-2024", "2022-01-01", "2024-12-31")]

CONFIGS = [
    ("B 12-16 rr1.5", dict(session_start=12, session_end=16, rr=1.5)),
    ("B 12-16 rr3.0", dict(session_start=12, session_end=16, rr=3.0)),
    ("B 07-11 rr1.5", dict(session_start=7, session_end=11, rr=1.5)),
    ("B 12-16 fade", dict(session_start=12, session_end=16, rr=1.5, invert=True)),
]

rows = []
cache = {}
for label, start, end in SLICES:
    if (start, end) not in cache:
        cache[(start, end)] = load_bars("5m", start, end)
    df = cache[(start, end)]
    for name, over in CONFIGS:
        cfg = {**base, **V["B"], **over}
        arrays = build_arrays(df, cfg)
        res = run_one(df, arrays, cfg, 0.2)
        e, st = res["extra"], res["stats"]
        row = {"slice": label, "config": name, "n": e["trades"],
               "win_%": e.get("win_rate_%"), "pf": st.get("Profit Factor"),
               "exp_R": e.get("expectancy_R"),
               "ret_%": st.get("Return [%]"),
               "dd_%": st.get("Max. Drawdown [%]")}
        rows.append(row)
        print(f"{label:19s} {name:13s} n={row['n']:4d} win={row['win_%']:.1f} "
              f"pf={row['pf']:.2f} expR={row['exp_R']:+.3f} "
              f"ret={row['ret_%']:.0f}% dd={row['dd_%']:.0f}%", flush=True)

d = pd.DataFrame(rows)
d.to_csv(OUT / "grid_eras.csv", index=False)
print()
print(d.pivot(index="config", columns="slice", values="exp_R").round(3).to_string())
