"""Max favourable / adverse excursion per trade, in units of risk (R).

Uses the execution bars stored in the trade log (EntryBar/ExitBar are row
positions in the 5m execution frame).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ema200_breakout_exec5m import load_bars  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
PIP = 1e-4
KEYS = ["A_tight_level", "B_wide_body", "C_close_level"]


def load_trades(tag: str, key: str) -> pd.DataFrame:
    t = pd.read_csv(OUT / f"exec5m_trades_{tag}_{key}.csv", parse_dates=["EntryTime"])
    sign = np.where(t.Size > 0, 1, -1)
    t["sign"] = sign
    t["risk"] = (t.EntryPrice - t.SL).abs()
    t["outcome"] = np.where((t.ExitPrice - t.TP).abs() <= 0.2e-4, "TP",
                            np.where((t.ExitPrice - t.SL).abs() <= 0.2e-4, "SL", "gap"))
    return t


def excursions(t: pd.DataFrame, df: pd.DataFrame, horizon: int = 24) -> pd.DataFrame:
    """MFE/MAE over a fixed horizon from entry.

    Using the exit bar censors the distribution: a trade that exits at 1.5R can
    never show a 2R excursion, so choosing a target from exit-bounded MFE is
    circular.
    """
    hi = df.High.to_numpy()
    lo = df.Low.to_numpy()
    rows = []
    for r in t.itertuples():
        a = int(r.EntryBar)
        b = min(a + horizon, len(df) - 1)
        if r.sign > 0:
            mfe = (hi[a:b + 1].max() - r.EntryPrice) / r.risk
            mae = (r.EntryPrice - lo[a:b + 1].min()) / r.risk
        else:
            mfe = (r.EntryPrice - lo[a:b + 1].min()) / r.risk
            mae = (hi[a:b + 1].max() - r.EntryPrice) / r.risk
        rows.append((mfe, mae))
    out = pd.DataFrame(rows, columns=["mfe_R", "mae_R"], index=t.index)
    return out


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "nofresh"
    df = load_bars("5m", "2018-01-01")
    for key in KEYS:
        t = load_trades(tag, key)
        if t.empty:
            continue
        ex = excursions(t, df)
        t = pd.concat([t, ex], axis=1)
        q = t.mfe_R.quantile([0.25, 0.5, 0.75, 0.9]).round(2).to_dict()
        print(f"\n[{tag} {key}]  n={len(t)}")
        print("  MFE R quantiles 25/50/75/90:", q,
              " mean", round(t.mfe_R.mean(), 2))
        print("  MAE R quantiles 25/50/75/90:",
              t.mae_R.quantile([0.25, 0.5, 0.75, 0.9]).round(2).to_dict())
        print("  share reaching 1R / 1.5R / 2R / 3R:",
              round(float((t.mfe_R >= 1).mean()), 3),
              round(float((t.mfe_R >= 1.5).mean()), 3),
              round(float((t.mfe_R >= 2).mean()), 3),
              round(float((t.mfe_R >= 3).mean()), 3))
        for oc in ("TP", "SL", "gap"):
            s = t[t.outcome == oc]
            if len(s) > 20:
                print(f"  {oc:3s} n={len(s):4d} median MFE {s.mfe_R.median():.2f} "
                      f"median MAE {s.mae_R.median():.2f} "
                      f"share MFE>=2R {100 * (s.mfe_R >= 2).mean():.0f}%")
        t.to_csv(OUT / f"mfe_{tag}_{key}.csv", index=False)


if __name__ == "__main__":
    main()
