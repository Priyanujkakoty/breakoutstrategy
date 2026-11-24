"""Plot equity curves for the breakout test runs."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

OUT = Path(__file__).resolve().parent / "out"
KEYS = ["A_tight_level", "B_wide_body", "C_close_level"]


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "full"
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for k in KEYS:
        f = OUT / f"exec5m_equity_{tag}_{k}.csv"
        if not f.exists():
            continue
        eq = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
        ax.plot(eq.index, eq.values, lw=1.1, label=k)
    ax.set_yscale("log")
    ax.set_ylabel("Equity (log)")
    ax.set_title(f"EURUSD 30m 200EMA pullback breakout - {tag} (1% risk/trade, 0.2 pip/side)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = OUT / f"equity_{tag}.png"
    fig.savefig(p, dpi=130)
    print("saved", p)


if __name__ == "__main__":
    main()
