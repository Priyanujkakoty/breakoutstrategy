"""Focused filter grid: session hours, max distance from EMA, min stop distance."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ema200_breakout_exec5m import build_arrays, load_bars, run_one  # noqa: E402

OUT = HERE / "out"
VARIANTS = {
    "A": dict(sl_mode="level", entry_mode="stop"),
    "B": dict(sl_mode="body", entry_mode="stop"),
}

base = dict(ema_n=200, atr_n=14, pivot_n=10, pb_window=25, pb_atr=0.5,
            pb_recency=25, buf_pips=1.0, rr=1.5, risk_pct=0.01, max_hold=0,
            max_risk_atr=1.5, level_max_age=120, both_sides=True,
            require_fresh_pullback=True, require_fresh_level=True,
            session_start=-1, session_end=-1, max_dist_atr=0.0,
            min_stop_pips=1.0)

df = load_bars("5m", "2018-01-01")
arrays = build_arrays(df, base)

runs = []
for side in ("B", "A"):
    for sess in ((-1, -1), (7, 16), (11, 16)):
        for dist in (0.0, 2.5):
            minstop = 0.0 if side == "B" else 4.0
            runs.append((side, sess, dist, minstop))

# A with and without the stop floor at default session
for minstop in (1.0, 4.0):
    runs.append(("A", (-1, -1), 0.0, minstop))

rows = []
seen = set()
for side, sess, dist, minstop in runs:
    sig = (side, sess, dist, minstop)
    if sig in seen:
        continue
    seen.add(sig)
    tag = f"{side}_s{sess[0]}_{sess[1]}_d{dist}_m{minstop}"
    cfg = {**base, **VARIANTS[side], "session_start": sess[0],
           "session_end": sess[1], "max_dist_atr": dist,
           "min_stop_pips": minstop}
    res = run_one(df, arrays, cfg, 0.2)
    e, s = res["extra"], res["stats"]
    row = {"tag": tag, "variant": side, "session": str(sess), "dist_atr": dist,
           "min_stop": minstop, "trades": e["trades"],
           "win_%": e.get("win_rate_%"), "pf": s.get("Profit Factor"),
           "exp_R": e.get("expectancy_R"), "exp_pips": e.get("expectancy_pips"),
           "return_%": s.get("Return [%]"), "maxdd_%": s.get("Max. Drawdown [%]"),
           "risk_pips": e.get("avg_risk_pips")}
    rows.append(row)
    print(f"{tag:24s} n={row['trades']:5d} win={row['win_%']:.1f} "
          f"pf={row['pf']:.2f} expR={row['exp_R']:+.3f} ret={row['return_%']:.1f}% "
          f"dd={row['maxdd_%']:.0f}% risk={row['risk_pips']:.1f}", flush=True)

d = pd.DataFrame(rows).sort_values("exp_R", ascending=False)
d.to_csv(OUT / "grid_filters.csv", index=False)
print("\nTOP")
print(d.head(12).to_string(index=False))
