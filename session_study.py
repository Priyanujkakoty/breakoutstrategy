"""Session-hour study on the widest samples."""

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
            require_fresh_pullback=True, require_fresh_level=True,
            session_start=-1, session_end=-1, max_dist_atr=0.0, min_stop_pips=1.0)

df = load_bars("5m", "2018-01-01")
arrays = build_arrays(df, base)

sessions = [(-1, -1), (7, 11), (11, 13), (13, 16), (11, 16), (7, 16), (12, 16), (12, 17)]
rows = []
for side, fresh in (("B", False), ("A", False), ("B", True)):
    for s in sessions:
        cfg = {**base, **V[side], "session_start": s[0], "session_end": s[1],
               "require_fresh_pullback": fresh, "require_fresh_level": fresh}
        res = run_one(df, arrays, cfg, 0.2)
        e, st = res["extra"], res["stats"]
        row = {"side": side, "fresh": fresh, "session": f"{s[0]}-{s[1]}",
               "n": e["trades"], "win_%": e.get("win_rate_%"),
               "pf": st.get("Profit Factor"), "exp_R": e.get("expectancy_R"),
               "exp_pips": e.get("expectancy_pips"),
               "ret_%": st.get("Return [%]"), "dd_%": st.get("Max. Drawdown [%]")}
        rows.append(row)
        print(f"{side} fresh={int(fresh)} {row['session']:>5s} n={row['n']:5d} "
              f"win={row['win_%']:.1f} pf={row['pf']:.2f} expR={row['exp_R']:+.3f} "
              f"ret={row['ret_%']:.0f}%", flush=True)

d = pd.DataFrame(rows)
d.to_csv(OUT / "session_study.csv", index=False)
print(d.sort_values(["side", "fresh", "exp_R"], ascending=[True, True, False]).to_string(index=False))
