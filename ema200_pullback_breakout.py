"""
EURUSD 30-minute: 200 EMA trend filter + pullback + swing breakout.

Rules under test (user spec):
  1. Trend filter: 200 EMA on the 30m chart. Long only above, short only below.
  2. Setup: wait for a pullback inside the trend structure.
  3. Entry: break of the local swing high (long) / swing low (short).
  4. Exit: fixed 1.5 : 1 reward-to-risk (TP = 1.5 x SL distance).
  5. SL variants:
       A  tight  - SL on the far side of the broken level (immediate entry)
       B  wide   - SL behind the entry candle body (immediate entry)
       C  confirm- entry at the close of the breakout candle, SL beyond the level

Implementation notes
  * Swing points = confirmed fractal pivots (n bars each side). A pivot is only
    used n bars after it forms, so nothing looks ahead.
  * Pullback = the low (long) / high (short) of the last `pb_window` bars came
    within `pb_atr` ATR of the 200 EMA, while price is on the trend side.
  * A uses a stop order resting at the level (intrabar fill). B and C enter at
    the close of the breakout bar (`trade_on_close=True`).
  * Position size: fixed 1% equity risk per trade, derived from the SL distance.
  * Costs: bid/ask spread, no commission (raw-spread broker).

Data: Dukascopy M1 CSVs, resampled to 30m, UTC.

Run:  python ema200_pullback_breakout.py
      python ema200_pullback_breakout.py --start 2018-01-01 --sweep
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "market_data" / "EURUSD" / "1m" / "yearly"
OUT_DIR = Path(__file__).resolve().parent / "out"

PIP = 1e-4

VARIANTS = {
    "A_tight_level": dict(sl_mode="level"),
    "B_wide_body": dict(sl_mode="body"),
    "C_close_level": dict(sl_mode="level", entry_mode="close"),
}


# ---------------------------------------------------------------------------
# indicators (plain arrays so backtesting.py can wrap them in self.I)
# ---------------------------------------------------------------------------
def ema(arr, n: int) -> np.ndarray:
    return pd.Series(arr).ewm(span=n, adjust=False).mean().to_numpy()


def atr(high, low, close, n: int) -> np.ndarray:
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean().to_numpy()


def pivot_level(arr, n: int, kind: str) -> np.ndarray:
    """Most recent confirmed pivot, available only n bars after it formed."""
    s = pd.Series(arr)
    win = 2 * n + 1
    if kind == "high":
        piv = s.where(s >= s.rolling(win, center=True).max())
    else:
        piv = s.where(s <= s.rolling(win, center=True).min())
    return piv.shift(n).ffill().to_numpy()


def pivot_age(arr, n: int, kind: str) -> np.ndarray:
    """Bars elapsed since the most recent confirmed pivot."""
    s = pd.Series(arr)
    win = 2 * n + 1
    if kind == "high":
        piv = s.where(s >= s.rolling(win, center=True).max())
    else:
        piv = s.where(s <= s.rolling(win, center=True).min())
    stamp = pd.Series(np.arange(len(s), dtype=float)).where(piv.notna()).shift(n).ffill()
    return (np.arange(len(s)) - stamp.to_numpy())


def pullback_touch(high, low, ema_arr, atr_arr, window: int, mult: float, side: str) -> np.ndarray:
    """1 where the recent excursion came within `mult` ATR of the EMA."""
    if side == "long":
        dist = pd.Series(low - ema_arr).rolling(window).min()
    else:
        dist = -(pd.Series(high - ema_arr).rolling(window).max())
    ok = (dist <= mult * pd.Series(atr_arr)).to_numpy()
    return ok.astype(float)


# ---------------------------------------------------------------------------
# strategy
# ---------------------------------------------------------------------------
class Ema200Breakout(Strategy):
    ema_n = 200
    atr_n = 14
    pivot_n = 10
    pb_window = 25          # bars scanned for the pullback (12.5 h on 30m)
    pb_atr = 0.5            # pullback must reach within 0.5 ATR of the EMA
    level_max_age = 120     # drop swing levels older than this many bars
    level_min_age = 1       # do not trade a pivot on its confirmation bar
    buf_pips = 1.0          # buffer past the level / candle body
    rr = 1.5
    risk_pct = 0.01
    min_stop_pips = 1.0
    max_hold = 0            # 0 = off
    sl_mode = "level"       # "level" | "body"
    entry_mode = "stop"     # "stop" | "close"
    both_sides = True

    def init(self):
        c, h, l = self.data.Close, self.data.High, self.data.Low
        self.ema = self.I(ema, c, self.ema_n, name=f"EMA{self.ema_n}")
        self.atr = self.I(atr, h, l, c, self.atr_n, name=f"ATR{self.atr_n}")
        self.lvl_hi = self.I(pivot_level, h, self.pivot_n, "high", name="SwingHigh")
        self.lvl_lo = self.I(pivot_level, l, self.pivot_n, "low", name="SwingLow")
        self.age_hi = self.I(pivot_age, h, self.pivot_n, "high", name="SwingHighAge")
        self.age_lo = self.I(pivot_age, l, self.pivot_n, "low", name="SwingLowAge")
        self.pb_long = self.I(pullback_touch, h, l, self.ema, self.atr, self.pb_window,
                              self.pb_atr, "long", name="PullbackLong")
        self.pb_short = self.I(pullback_touch, h, l, self.ema, self.atr, self.pb_window,
                               self.pb_atr, "short", name="PullbackShort")
        self.pending = None

    # -- helpers ------------------------------------------------------------
    def _size(self, stop_dist: float, price: float) -> float:
        if stop_dist <= 0:
            return 0.0
        risk_cash = self.risk_pct * self.equity
        units = risk_cash / stop_dist
        max_notional = self.equity / self._broker._leverage
        if max_notional <= 0:
            return 0.0
        return float(min(0.99, units * price / max_notional))

    def _long_setup(self) -> bool:
        e, a = self.ema[-1], self.atr[-1]
        lvl, age = self.lvl_hi[-1], self.age_hi[-1]
        if np.isnan(e) or np.isnan(a) or np.isnan(lvl) or np.isnan(age):
            return False
        if self.data.Close[-1] <= e:              # trend filter
            return False
        if self.pb_long[-1] < 0.5:                # no recent pullback to the EMA
            return False
        if lvl <= e:                              # structure must sit above the EMA
            return False
        if not (self.level_min_age <= age <= self.level_max_age):
            return False
        return True

    def _short_setup(self) -> bool:
        e, a = self.ema[-1], self.atr[-1]
        lvl, age = self.lvl_lo[-1], self.age_lo[-1]
        if np.isnan(e) or np.isnan(a) or np.isnan(lvl) or np.isnan(age):
            return False
        if self.data.Close[-1] >= e:
            return False
        if self.pb_short[-1] < 0.5:
            return False
        if lvl >= e:
            return False
        if not (self.level_min_age <= age <= self.level_max_age):
            return False
        return True

    def _cancel_pending(self):
        if self.pending is not None:
            try:
                self.pending.cancel()
            except Exception:  # already filled / removed
                pass
            self.pending = None

    # -- main loop ----------------------------------------------------------
    def next(self):
        c, o, h, l = self.data.Close[-1], self.data.Open[-1], self.data.High[-1], self.data.Low[-1]
        buf = self.buf_pips * PIP

        if self.position:
            self._cancel_pending()
            if self.max_hold and (len(self.data) - 1 - self.trades[0].entry_bar) >= self.max_hold:
                self.position.close()
            return

        self._cancel_pending()
        if np.isnan(self.ema[-1]) or np.isnan(self.atr[-1]):
            return

        # ---------------- long ----------------
        if self._long_setup():
            lvl = self.lvl_hi[-1]
            if self.entry_mode == "stop" and c < lvl - buf:
                entry_est = lvl + buf
                sl = lvl - buf if self.sl_mode == "level" else min(o, c) - buf
                risk = entry_est - sl
                if risk >= self.min_stop_pips * PIP:
                    size = self._size(risk, entry_est)
                    if size > 0:
                        self.pending = self.buy(size=size, stop=lvl + buf,
                                                sl=sl, tp=entry_est + self.rr * risk,
                                                tag="L")
            elif self.entry_mode == "close" and self.data.Close[-2] <= lvl < c:
                sl = lvl - buf if self.sl_mode == "level" else min(o, c) - buf
                risk = c - sl
                if risk >= self.min_stop_pips * PIP:
                    size = self._size(risk, c)
                    if size > 0:
                        self.buy(size=size, sl=sl, tp=c + self.rr * risk, tag="L")

        # ---------------- short ----------------
        if self.both_sides and self._short_setup():
            lvl = self.lvl_lo[-1]
            if self.entry_mode == "stop" and c > lvl + buf:
                entry_est = lvl - buf
                sl = lvl + buf if self.sl_mode == "level" else max(o, c) + buf
                risk = sl - entry_est
                if risk >= self.min_stop_pips * PIP:
                    size = self._size(risk, entry_est)
                    if size > 0:
                        self.pending = self.sell(size=size, stop=lvl - buf,
                                                 sl=sl, tp=entry_est - self.rr * risk,
                                                 tag="S")
            elif self.entry_mode == "close" and self.data.Close[-2] >= lvl > c:
                sl = lvl + buf if self.sl_mode == "level" else max(o, c) + buf
                risk = sl - c
                if risk >= self.min_stop_pips * PIP:
                    size = self._size(risk, c)
                    if size > 0:
                        self.sell(size=size, sl=sl, tp=c - self.rr * risk, tag="S")


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def load_30m(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    files = sorted(DATA_DIR.glob("eurusd_1m_*.csv"))
    if not files:
        sys.exit(f"No M1 CSVs in {DATA_DIR}")
    parts = []
    for f in files:
        df = pd.read_csv(f, usecols=["timestamp", "open", "high", "low", "close", "volume"])
        df.index = pd.to_datetime(df.pop("timestamp"), unit="ms", utc=True)
        r = (df.resample("30min")
               .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
               .dropna())
        parts.append(r)
    out = pd.concat(parts)
    out = out[~out.index.duplicated(keep="first")].sort_index()
    out = out.rename(columns=str.title)
    if start:
        out = out.loc[pd.Timestamp(start, tz="UTC"):]
    if end:
        out = out.loc[:pd.Timestamp(end, tz="UTC")]
    return out[["Open", "High", "Low", "Close", "Volume"]].astype(float)


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def trade_pips(trades: pd.DataFrame) -> pd.Series:
    sign = np.where(trades["Size"] > 0, 1, -1)
    return (trades["ExitPrice"] - trades["EntryPrice"]) * sign / PIP


def run_one(df: pd.DataFrame, cfg: dict, spread_pips: float, commission: float = 0.0) -> dict:
    class S(Ema200Breakout):
        pass

    for k, v in cfg.items():
        setattr(S, k, v)

    spread_rel = (spread_pips * PIP) / float(df["Close"].iloc[-1])
    bt = Backtest(df, S, cash=100_000, spread=spread_rel, commission=commission,
                  margin=0.02, exclusive_orders=True, finalize_trades=True,
                  trade_on_close=(cfg.get("entry_mode", "stop") == "close"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        stats = bt.run()
    ambig = sum(1 for w in caught
                if issubclass(w.category, UserWarning) and "contingent" in str(w.message))

    trades = stats["_trades"].copy()
    extra = {"trades": len(trades), "same_bar_sl_ambiguous": ambig}
    if len(trades):
        pips = trade_pips(trades)
        extra.update({
            "win_rate_%": round(100 * (pips > 0).mean(), 2),
            "expectancy_pips": round(float(pips.mean()), 3),
            "median_pips": round(float(pips.median()), 3),
            "avg_win_pips": round(float(pips[pips > 0].mean()), 2),
            "avg_loss_pips": round(float(pips[pips <= 0].mean()), 2),
            "long_share_%": round(100 * (trades["Size"] > 0).mean(), 1),
            "avg_hold_h": round(trades["Duration"].dt.total_seconds().div(3600).mean(), 1),
        })

    keep = ["Start", "End", "Duration", "Return [%]", "Buy & Hold Return [%]",
            "Max. Drawdown [%]", "Sharpe Ratio", "Sortino Ratio", "Profit Factor",
            "Win Rate [%]", "# Trades", "Avg. Trade [%]", "Exposure Time [%]",
            "CAGR [%]", "Calmar Ratio"]
    summary = {k: (float(stats[k]) if isinstance(stats[k], (int, float, np.floating)) else str(stats[k]))
               for k in keep if k in stats}
    return {"stats": summary, "extra": extra, "trades": trades,
            "equity": stats["_equity_curve"]["Equity"].copy()}


def yearly_return(eq: pd.Series) -> pd.Series:
    y = eq.resample("YE").last()
    y.iloc[0] = y.iloc[0] / eq.iloc[0]
    return (y.pct_change().fillna(y.iloc[0] - 1) * 100).round(2)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--spread-pips", type=float, default=0.2, help="per side")
    p.add_argument("--commission", type=float, default=0.0)
    p.add_argument("--risk-pct", type=float, default=0.01)
    p.add_argument("--pivot-n", type=int, default=10)
    p.add_argument("--pb-window", type=int, default=25)
    p.add_argument("--pb-atr", type=float, default=0.5)
    p.add_argument("--buf-pips", type=float, default=1.0)
    p.add_argument("--rr", type=float, default=1.5)
    p.add_argument("--max-hold", type=int, default=0)
    p.add_argument("--levels", default="A,B,C", help="variants to run")
    p.add_argument("--tag", default="base")
    p.add_argument("--sweep", action="store_true", help="pivot/buffer/params sensitivity grid")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("loading 1m -> 30m ...", flush=True)
    df = load_30m(args.start, args.end)
    print(f"bars={len(df):,}  {df.index[0]} -> {df.index[-1]}", flush=True)

    base_cfg = dict(risk_pct=args.risk_pct, pivot_n=args.pivot_n, pb_window=args.pb_window,
                    pb_atr=args.pb_atr, buf_pips=args.buf_pips, rr=args.rr,
                    max_hold=args.max_hold)

    results = {}
    for name in [n.strip() for n in args.levels.split(",") if n.strip()]:
        key = next((k for k in VARIANTS if k.startswith(name)), None)
        if key is None:
            print(f"unknown variant {name!r}", file=sys.stderr)
            continue
        cfg = {**base_cfg, **VARIANTS[key]}
        res = run_one(df, cfg, args.spread_pips, args.commission)
        res["equity"].rename("Equity").to_csv(OUT_DIR / f"equity_{args.tag}_{key}.csv")
        res["trades"].to_csv(OUT_DIR / f"trades_{args.tag}_{key}.csv", index=False)
        results[key] = res
        s = res["stats"]
        e = res["extra"]
        print(f"\n[{key}]  {json.dumps(cfg)}")
        print(f"  return {s.get('Return [%]'):.2f}%   CAGR {s.get('CAGR [%]', float('nan')):.2f}%"
              f"   maxDD {s.get('Max. Drawdown [%]'):.2f}%   Sharpe {s.get('Sharpe Ratio'):.2f}"
              f"   PF {s.get('Profit Factor'):.2f}")
        print(f"  trades {e['trades']}  win {e.get('win_rate_%', float('nan')):.1f}%"
              f"  expectancy {e.get('expectancy_pips', float('nan')):.2f} pips"
              f"  avg hold {e.get('avg_hold_h', float('nan')):.1f} h"
              f"  long {e.get('long_share_%', float('nan')):.0f}%"
              f"  ambiguous_same_bar {e['same_bar_sl_ambiguous']}")
        print(f"  yearly: {dict(yearly_return(res['equity']))}")

    if args.sweep:
        rows = []
        grid = [(piv, buf, pbw, pba, side)
                for piv in (5, 10, 20)
                for buf in (0.5, 1.0, 2.0)
                for pbw, pba in ((10, 0.5), (25, 0.5), (25, 1.0))
                for side in ("A", "B", "C")]
        print(f"\nsweep: {len(grid)} runs", flush=True)
        for piv, buf, pbw, pba, side in grid:
            key = next(k for k in VARIANTS if k.startswith(side))
            cfg = {**base_cfg, **VARIANTS[key], "pivot_n": piv, "buf_pips": buf,
                   "pb_window": pbw, "pb_atr": pba}
            try:
                res = run_one(df, cfg, args.spread_pips, args.commission)
            except Exception as exc:  # noqa: BLE001
                print("skip", piv, buf, pbw, pba, side, exc)
                continue
            s, e = res["stats"], res["extra"]
            rows.append({
                "variant": key, "pivot_n": piv, "buf_pips": buf, "pb_window": pbw,
                "pb_atr": pba, "trades": e["trades"],
                "return_%": s.get("Return [%]"), "cagr_%": s.get("CAGR [%]"),
                "maxdd_%": s.get("Max. Drawdown [%]"), "sharpe": s.get("Sharpe Ratio"),
                "pf": s.get("Profit Factor"), "win_%": e.get("win_rate_%"),
                "exp_pips": e.get("expectancy_pips"),
            })
            print(f"  {key} piv={piv} buf={buf} pb=({pbw},{pba}) "
                  f"ret={rows[-1]['return_%']:.1f}% pf={rows[-1]['pf']:.2f} "
                  f"n={rows[-1]['trades']}", flush=True)
        sweep = pd.DataFrame(rows).sort_values("pf", ascending=False)
        sweep.to_csv(OUT_DIR / f"sweep_{args.tag}.csv", index=False)
        print("\nTOP 15 BY PROFIT FACTOR")
        print(sweep.head(15).to_string(index=False))

    summary = {k: {**v["stats"], **v["extra"]} for k, v in results.items()}
    with open(OUT_DIR / f"summary_{args.tag}.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print(f"\nsaved -> {OUT_DIR}")


if __name__ == "__main__":
    main()
