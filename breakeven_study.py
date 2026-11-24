"""How far do losing trades ever run in favour, before the stop hits?

Exit-bounded MFE for SL trades is unbiased (the stop is at -1R, far below),
so this measures the headroom a breakeven rule could use.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ema200_breakout_exec5m import load_bars  # noqa: E402

OUT = HERE / "out"
TAG = sys.argv[1] if len(sys.argv) > 1 else "s1216rr3b"

t = pd.read_csv(OUT / f"exec5m_trades_{TAG}_B_wide_body.csv", parse_dates=["EntryTime"])
df = load_bars("5m", "2018-01-01", None)
hi, lo = df.High.to_numpy(), df.Low.to_numpy()

sign = np.where(t.Size > 0, 1, -1)
risk = (t.EntryPrice - t.SL).abs().to_numpy()
entry = t.EntryPrice.to_numpy()
outcome = np.where((t.ExitPrice - t.TP).abs() <= 0.2e-4, "TP",
                   np.where((t.ExitPrice - t.SL).abs() <= 0.2e-4, "SL", "gap"))

rows = []
for k in range(len(t)):
    a, b = int(t.EntryBar.iloc[k]), int(t.ExitBar.iloc[k])
    if sign[k] > 0:
        mfe = (hi[a:b + 1].max() - entry[k]) / risk[k]
        mae = (entry[k] - lo[a:b + 1].min()) / risk[k]
    else:
        mfe = (entry[k] - lo[a:b + 1].min()) / risk[k]
        mae = (hi[a:b + 1].max() - entry[k]) / risk[k]
    rows.append((outcome[k], mfe, mae))

m = pd.DataFrame(rows, columns=["outcome", "mfe_R", "mae_R"])
m.to_csv(OUT / f"excursion_exitbounded_{TAG}.csv", index=False)

sl = m[m.outcome == "SL"]
print(f"{TAG}: SL trades {len(sl)}")
for thr in (1.0, 1.5, 2.0, 2.5):
    share = (sl.mfe_R >= thr).mean() * 100
    print(f"  share of losers that touched +{thr:.1f}R before the stop: {share:5.1f}%")
print("  loser mfe_R quantiles:", sl.mfe_R.quantile([.5, .7, .8, .9]).round(2).to_dict())

tp = m[m.outcome == "TP"]
for thr in (0.5, 1.0):
    share = (tp.mae_R >= thr).mean() * 100
    print(f"  share of winners that first went -{thr:.1f}R: {share:5.1f}%")

# Breakeven economics: with BE at 1R, a loser that touched 1R becomes ~0R
# instead of -1R; but a winner that dips back to entry after touching 1R
# becomes 0R instead of +3R.
p_hit = (sl.mfe_R >= 1.0).mean()
print(f"\n  naive BE@1R gain on losers: {p_hit*100:.1f}% x 1R = +{p_hit:.3f}R per loser")
