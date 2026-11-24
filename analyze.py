"""Summarise trade logs produced by ema200_breakout_exec5m.py."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "out"
PIP = 1e-4


def load(tag: str, key: str) -> pd.DataFrame:
    f = OUT / f"exec5m_trades_{tag}_{key}.csv"
    if not f.exists():
        return pd.DataFrame()
    t = pd.read_csv(f)
    if t.empty:
        return t
    sign = np.where(t["Size"] > 0, 1, -1)
    t["sign"] = sign
    t["risk_pips"] = (t["EntryPrice"] - t["SL"]) * sign / PIP
    t["pips"] = (t["ExitPrice"] - t["EntryPrice"]) * sign / PIP
    t["R"] = t["pips"] / t["risk_pips"]
    t["EntryTime"] = pd.to_datetime(t["EntryTime"], utc=True)
    t["ExitTime"] = pd.to_datetime(t["ExitTime"], utc=True)
    t["Duration"] = pd.to_timedelta(t["Duration"])
    t["hour"] = t["EntryTime"].dt.hour
    t["year"] = t["EntryTime"].dt.year
    return t


def describe(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"trades": 0}
    wins, losses = t[t["pips"] > 0], t[t["pips"] <= 0]
    return {
        "trades": len(t),
        "win%": round(100 * (t["pips"] > 0).mean(), 1),
        "pf": round(t["pips"][t["pips"] > 0].sum() / -t["pips"][t["pips"] <= 0].sum(), 2),
        "exp_pips": round(t["pips"].mean(), 3),
        "exp_R": round(t["R"].mean(), 3),
        "avg_risk_pips": round(t["risk_pips"].mean(), 1),
        "avg_win_R": round(wins["R"].mean(), 2) if len(wins) else np.nan,
        "avg_loss_R": round(losses["R"].mean(), 2) if len(losses) else np.nan,
        "pips_sum": round(t["pips"].sum(), 0),
        "hold_h": round(t["Duration"].dt.total_seconds().div(3600).mean(), 2),
        "long%": round(100 * (t["Size"] > 0).mean(), 0),
    }


def exit_reason(t: pd.DataFrame) -> pd.Series:
    tol = 0.2e-4
    near_tp = (t["ExitPrice"] - t["TP"]).abs() <= tol
    near_sl = (t["ExitPrice"] - t["SL"]).abs() <= tol
    return np.where(near_tp, "TP", np.where(near_sl, "SL", "gap/other"))


def main() -> None:
    tags = sys.argv[1:] or ["full", "gross", "m1check", "m1gross"]
    rows = []
    for tag in tags:
        for key in ("A_tight_level", "B_wide_body", "C_close_level"):
            t = load(tag, key)
            if t.empty:
                continue
            d = describe(t)
            d.update({"run": tag, "variant": key})
            rows.append(d)
    df = pd.DataFrame(rows)[["run", "variant", "trades", "win%", "pf", "exp_pips",
                             "exp_R", "avg_risk_pips", "avg_win_R", "avg_loss_R",
                             "pips_sum", "hold_h", "long%"]]
    print(df.to_string(index=False))
    df.to_csv(OUT / "analysis_summary.csv", index=False)

    # year-by-year expectancy in R for the main run
    for tag in tags:
        print(f"\n--- {tag}: yearly expectancy (R) / trades")
        for key in ("A_tight_level", "B_wide_body", "C_close_level"):
            t = load(tag, key)
            if t.empty:
                continue
            g = t.groupby("year").agg(n=("R", "size"), expR=("R", "mean"), pips=("pips", "sum"))
            g["expR"] = g["expR"].round(3)
            g["pips"] = g["pips"].round(0)
            print(key)
            print(g.T.to_string())

    # hour-of-day for the main run
    print("\n--- full: expectancy (pips) by UTC hour")
    for key in ("A_tight_level", "B_wide_body", "C_close_level"):
        t = load("full", key)
        if t.empty:
            continue
        g = t.groupby("hour")["pips"].agg(["size", "mean"]).round(3)
        print(key, dict(g["mean"]))

    # exit reasons
    print("\n--- full: exit reason share and PnL")
    for key in ("A_tight_level", "B_wide_body", "C_close_level"):
        t = load("full", key)
        if t.empty:
            continue
        t["reason"] = exit_reason(t)
        g = t.groupby("reason").agg(n=("pips", "size"), pips=("pips", "sum"))
        g["share_%"] = (100 * g["n"] / len(t)).round(1)
        print(key)
        print(g.round(1).to_string())
        print("  hold 0-1 bars:", round(100 * (t["ExitBar"] - t["EntryBar"] <= 1).mean(), 1), "%")


if __name__ == "__main__":
    main()
