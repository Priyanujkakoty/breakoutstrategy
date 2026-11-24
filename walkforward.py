"""Walk-forward split: fit window 2018-2022, test window 2023-2026."""

from __future__ import annotations

import argparse
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

p = argparse.ArgumentParser()
p.add_argument("--side", default="B")
p.add_argument("--session-start", type=int, default=-1)
p.add_argument("--session-end", type=int, default=-1)
p.add_argument("--max-dist-atr", type=float, default=0.0)
p.add_argument("--rr", type=float, default=1.5)
p.add_argument("--no-fresh", action="store_true")
p.add_argument("--spread-pips", type=float, default=0.2)
args = p.parse_args()

cfg = {**base, **V[args.side], "session_start": args.session_start,
       "session_end": args.session_end, "max_dist_atr": args.max_dist_atr,
       "rr": args.rr,
       "require_fresh_pullback": not args.no_fresh,
       "require_fresh_level": not args.no_fresh}

full = load_bars("5m", "2018-01-01")
splits = [("IS 2018-2022", "2018-01-01", "2022-12-31"),
          ("OOS 2023-2026", "2023-01-01", None)]
rows = []
for label, start, end in splits:
    sl = pd.Timestamp(start, tz="UTC")
    df = full.loc[sl:] if end is None else full.loc[sl:pd.Timestamp(end, tz="UTC")]
    ff = df
    arrays = build_arrays(ff, cfg)
    res = run_one(ff, arrays, cfg, args.spread_pips)
    e, s = res["extra"], res["stats"]
    row = {"window": label, "n": e["trades"], "win_%": e.get("win_rate_%"),
           "pf": s.get("Profit Factor"), "exp_R": e.get("expectancy_R"),
           "exp_pips": e.get("expectancy_pips"),
           "ret_%": s.get("Return [%]"), "dd_%": s.get("Max. Drawdown [%]")}
    rows.append(row)
    print(f"{label:14s} n={row['n']:5d} win={row['win_%']:.1f} pf={row['pf']:.2f} "
          f"expR={row['exp_R']:+.3f} ret={row['ret_%']:.0f}% dd={row['dd_%']:.0f}%",
          flush=True)

tag = (f"wf_{args.side}_s{args.session_start}_{args.session_end}"
       f"_d{args.max_dist_atr}_rr{args.rr}_f{int(not args.no_fresh)}")
pd.DataFrame(rows).to_csv(OUT / f"{tag}.csv", index=False)
print("saved", tag)
