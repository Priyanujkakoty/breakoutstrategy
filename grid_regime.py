"""Regime grid on the positive NY session: EMA slope vs ATR, ATR expansion."""

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
            min_slope_atr=-1.0, max_atr_ratio=0.0)

df = load_bars("5m", "2018-01-01")
arrays = build_arrays(df, base)

rows = []
for side in ("B", "A"):
    for sess in ((11, 16), (12, 16)):
        for slope in (-1.0, 0.0, 0.25, 0.5):
            for ratio in (0.0, 1.0, 1.3):
                if slope < 0 and ratio > 0:
                    continue  # baseline only once
                cfg = {**base, **V[side], "session_start": sess[0],
                       "session_end": sess[1], "min_slope_atr": slope,
                       "max_atr_ratio": ratio}
                res = run_one(df, arrays, cfg, 0.2)
                e, st = res["extra"], res["stats"]
                row = {"side": side, "session": f"{sess[0]}-{sess[1]}",
                       "slope": slope, "ratio": ratio, "n": e["trades"],
                       "win_%": e.get("win_rate_%"), "pf": st.get("Profit Factor"),
                       "exp_R": e.get("expectancy_R"),
                       "exp_pips": e.get("expectancy_pips"),
                       "ret_%": st.get("Return [%]"),
                       "dd_%": st.get("Max. Drawdown [%]")}
                rows.append(row)
                print(f"{side} {row['session']:5s} slope={slope:4.2f} ratio={ratio:3.1f} "
                      f"n={row['n']:5d} win={row['win_%']:.1f} pf={row['pf']:.2f} "
                      f"expR={row['exp_R']:+.3f} ret={row['ret_%']:.0f}%", flush=True)

d = pd.DataFrame(rows)
d.to_csv(OUT / "grid_regime.csv", index=False)
print("\nTOP by expR")
print(d.sort_values("exp_R", ascending=False).head(12).to_string(index=False))
