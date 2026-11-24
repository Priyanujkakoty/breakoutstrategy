"""
EURUSD: 200 EMA trend + pullback + swing breakout, 30-minute signals.

Same rules as `ema200_pullback_breakout.py`, but here the *execution* runs on
5-minute bars while every signal (200 EMA, ATR, swing pivots, pullback) is
computed on 30-minute bars and mapped forward at bar close. That removes the
"SL and TP inside the entry bar" ambiguity that dominates a 30m-only run with
tight stops.

  1. Trend: close above/below the 30m 200 EMA.
  2. Setup: last 25 30m bars came within 0.5 ATR of the EMA.
  3. Entry: break of the most recent confirmed 30m swing high/low.
  4. Exit: TP = 1.5 x SL distance.
  5. SL variants:
       A tight   - stop entry at the level, SL 1 pip past the level
       B wide    - stop entry at the level, SL past the open of the 30m
                   breakout candle body ("behind the body")
       C confirm - entry at the 30m close of the breakout candle,
                   SL 1 pip past the level

Data: Dukascopy 5m CSVs (2018+), UTC.

Run: python ema200_breakout_exec5m.py
     python ema200_breakout_exec5m.py --sweep
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
DATA_DIR = ROOT / "market_data" / "EURUSD" / "5m" / "yearly"
OUT_DIR = Path(__file__).resolve().parent / "out"

PIP = 1e-4
TF = "30min"

VARIANTS = {
    "A_tight_level": dict(sl_mode="level", entry_mode="stop"),
    "B_wide_body": dict(sl_mode="body", entry_mode="stop"),
    "C_close_level": dict(sl_mode="level", entry_mode="close"),
}


# ---------------------------------------------------------------------------
# indicators (30m series)
# ---------------------------------------------------------------------------
def ema(arr, n: int) -> np.ndarray:
    return pd.Series(arr).ewm(span=n, adjust=False).mean().to_numpy()


def atr(high, low, close, n: int) -> np.ndarray:
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean().to_numpy()


def _pivot_mask(arr, n: int, kind: str) -> pd.Series:
    s = pd.Series(arr)
    win = 2 * n + 1
    if kind == "high":
        return s.where(s >= s.rolling(win, center=True).max())
    return s.where(s <= s.rolling(win, center=True).min())


def pivot_level(arr, n: int, kind: str) -> np.ndarray:
    """Most recent confirmed pivot, only known n bars after it formed."""
    return _pivot_mask(arr, n, kind).shift(n).ffill().to_numpy()


def pivot_age(arr, n: int, kind: str) -> np.ndarray:
    stamp = pd.Series(np.arange(len(arr), dtype=float)).where(
        _pivot_mask(arr, n, kind).notna()).shift(n).ffill()
    return np.arange(len(arr)) - stamp.to_numpy()


def pivot_time(arr, n: int, kind: str, index: pd.DatetimeIndex) -> np.ndarray:
    stamp = pd.Series(index.to_numpy()).where(
        _pivot_mask(arr, n, kind).notna()).shift(n).ffill()
    return stamp.to_numpy()


def pullback_touch(high, low, ema_arr, atr_arr, window: int, mult: float, side: str) -> np.ndarray:
    if side == "long":
        dist = pd.Series(low - ema_arr).rolling(window).min()
    else:
        dist = -(pd.Series(high - ema_arr).rolling(window).max())
    return (dist.to_numpy() <= mult * np.asarray(atr_arr)).astype(float)


def bars_since(cond: np.ndarray) -> np.ndarray:
    """Bars elapsed since the last True in `cond` (inf before the first True)."""
    idx = pd.Series(np.arange(len(cond), dtype=float)).where(np.asarray(cond) > 0)
    return (np.arange(len(cond)) - idx.ffill().to_numpy())


# ---------------------------------------------------------------------------
# strategy (runs on 5m bars, indicators precomputed on 30m)
# ---------------------------------------------------------------------------
class Breakout5m(Strategy):
    ema_n = 200
    atr_n = 14
    pivot_n = 10
    pb_window = 25
    pb_atr = 0.5
    pb_recency = 25
    level_max_age = 120
    level_min_age = 1
    buf_pips = 1.0
    rr = 1.5
    risk_pct = 0.01
    min_stop_pips = 1.0
    max_risk_atr = 1.5     # skip trades whose SL is further than this many ATR(30m)
    max_hold = 0
    sl_mode = "level"
    entry_mode = "stop"
    both_sides = True
    bar_minutes = 5
    spread_frac = 0.0
    require_fresh_pullback = True
    require_fresh_level = True
    session_start = -1          # UTC hour, inclusive; -1 disables
    session_end = -1            # UTC hour, exclusive
    max_dist_atr = 0.0          # skip entries further than this from the EMA (0 = off)
    min_slope_atr = -1.0        # require |EMA slope| >= this many ATR (-1 = off)
    max_atr_ratio = 0.0         # require ATR / mean(ATR,100) <= this (0 = off)
    max_atr_ratio_long = 0.0    # require ATR / mean(ATR,1000) <= this (0 = off)
    invert = False              # fade the breakout instead of following it
    be_at = 0.0                 # move SL to entry after price reaches this many R (0 = off)
    be_buffer_pips = 0.0        # leave this many pips beyond entry on the winning side
    arrays: dict | None = None

    def init(self):
        a = self.arrays
        self.ema = self.I(lambda: a["ema"], name="EMA200_30m")
        self.atr = self.I(lambda: a["atr"], name="ATR14_30m")
        self.lvl_hi = self.I(lambda: a["lvl_hi"], name="SwingHigh30m")
        self.lvl_lo = self.I(lambda: a["lvl_lo"], name="SwingLow30m")
        self.age_hi = self.I(lambda: a["age_hi"], name="SwingHighAge")
        self.age_lo = self.I(lambda: a["age_lo"], name="SwingLowAge")
        self.pb_long = self.I(lambda: a["pb_long"], name="PullbackLong")
        self.pb_short = self.I(lambda: a["pb_short"], name="PullbackShort")
        self.slope = self.I(lambda: a["ema_slope"], name="EMA200Slope")
        self.atr_ratio = self.I(lambda: a["atr_ratio"], name="ATRratio")
        self.atr_ratio_long = self.I(lambda: a["atr_ratio_long"], name="ATRratioLong")
        self.open30 = a["open30"]
        self.lvl_time_hi = a["lvl_time_hi"]
        self.lvl_time_lo = a["lvl_time_lo"]
        self.pb_time_long = a["pb_time_long"]
        self.pb_time_short = a["pb_time_short"]
        self.since_pb_long = a["since_pb_long"]
        self.since_pb_short = a["since_pb_short"]
        self.pending = None
        self.prev_close30 = None
        self.last_exit_time = None
        self.was_in_position = False
        self.be_risk = None
        self.be_side = 0
        self.be_done = False

    # -- helpers ------------------------------------------------------------
    def _cur(self, arr):
        """Value of a plain array at the current bar (plain arrays are not Indicators)."""
        return arr[len(self.data) - 1]

    def _fresh(self, lvl_time, pb_time) -> bool:
        if self.last_exit_time is None:
            return True
        if self.require_fresh_pullback and not (self._cur(pb_time) > self.last_exit_time):
            return False
        if self.require_fresh_level and not (self._cur(lvl_time) > self.last_exit_time):
            return False
        return True
    def _size(self, stop_dist: float, price: float) -> float:
        """Order fraction such that a stop-out loses risk_pct of equity.

        backtesting.py fills `size` as margin_available * leverage * size / price
        units, so the fraction must divide by equity * leverage, not by margin.
        """
        if stop_dist <= 0:
            return 0.0
        units = (self.risk_pct * self.equity) / stop_dist
        lev = self._broker._leverage
        if lev <= 0:
            return 0.0
        return float(min(0.99, units * price / (self.equity * lev)))

    def _long_setup(self, c: float) -> bool:
        e, at, lvl, age = self.ema[-1], self.atr[-1], self.lvl_hi[-1], self.age_hi[-1]
        if not np.isfinite([e, at, lvl, age]).all():
            return False
        return (c > e and lvl > e and self.pb_long[-1] >= 0.5
                and self._cur(self.since_pb_long) <= self.pb_recency
                and self.level_min_age <= age <= self.level_max_age
                and (self.max_dist_atr <= 0 or (c - e) <= self.max_dist_atr * at)
                and (self.min_slope_atr < 0 or self.slope[-1] >= self.min_slope_atr * at)
                and (self.max_atr_ratio <= 0 or self.atr_ratio[-1] <= self.max_atr_ratio)
                and (self.max_atr_ratio_long <= 0
                     or self.atr_ratio_long[-1] <= self.max_atr_ratio_long)
                and self._fresh(self.lvl_time_hi, self.pb_time_long))

    def _short_setup(self, c: float) -> bool:
        e, at, lvl, age = self.ema[-1], self.atr[-1], self.lvl_lo[-1], self.age_lo[-1]
        if not np.isfinite([e, at, lvl, age]).all():
            return False
        return (c < e and lvl < e and self.pb_short[-1] >= 0.5
                and self._cur(self.since_pb_short) <= self.pb_recency
                and self.level_min_age <= age <= self.level_max_age
                and (self.max_dist_atr <= 0 or (e - c) <= self.max_dist_atr * at)
                and (self.min_slope_atr < 0 or -self.slope[-1] >= self.min_slope_atr * at)
                and (self.max_atr_ratio <= 0 or self.atr_ratio[-1] <= self.max_atr_ratio)
                and (self.max_atr_ratio_long <= 0
                     or self.atr_ratio_long[-1] <= self.max_atr_ratio_long)
                and self._fresh(self.lvl_time_lo, self.pb_time_short))

    def _cancel_pending(self):
        if self.pending is not None:
            try:
                self.pending.cancel()
            except Exception:
                pass
            self.pending = None

    def _enter_long(self, c: float, o: float, lvl: float, buf: float, boundary: bool):
        cap = self.max_risk_atr * self.atr[-1] if self.max_risk_atr else np.inf
        if self.entry_mode == "stop":
            entry = lvl + buf
            if c >= entry:
                return
            if self.sl_mode == "level":
                sl = lvl - buf
            else:  # body of the 30m breakout candle: use its open (known at trigger)
                sl = min(self.open30[len(self.data) - 1], lvl) - buf
            fill = entry * (1 + self.spread_frac)   # buy at ask
            risk = fill - sl
            if risk < self.min_stop_pips * PIP or risk > cap:
                return
            size = self._size(risk, entry)
            if size > 0:
                self.pending = self.buy(size=size, stop=entry, sl=sl,
                                        tp=fill + self.rr * risk, tag="L")
        elif boundary:
            prev = self.prev_close30
            if prev is None or not (prev <= lvl < c):
                return
            o30 = self.open30[len(self.data) - 1]
            sl = lvl - buf if self.sl_mode == "level" else min(o30, c) - buf
            fill = c * (1 + self.spread_frac)
            risk = fill - sl
            if risk < self.min_stop_pips * PIP or risk > cap:
                return
            size = self._size(risk, c)
            if size > 0:
                self.buy(size=size, sl=sl, tp=fill + self.rr * risk, tag="L")

    def _enter_short(self, c: float, o: float, lvl: float, buf: float, boundary: bool):
        cap = self.max_risk_atr * self.atr[-1] if self.max_risk_atr else np.inf
        if self.entry_mode == "stop":
            entry = lvl - buf
            if c <= entry:
                return
            if self.sl_mode == "level":
                sl = lvl + buf
            else:
                sl = max(self.open30[len(self.data) - 1], lvl) + buf
            fill = entry * (1 - self.spread_frac)   # sell at bid
            risk = sl - fill
            if risk < self.min_stop_pips * PIP or risk > cap:
                return
            size = self._size(risk, entry)
            if size > 0:
                self.pending = self.sell(size=size, stop=entry, sl=sl,
                                         tp=fill - self.rr * risk, tag="S")
        elif boundary:
            prev = self.prev_close30
            if prev is None or not (prev >= lvl > c):
                return
            sl = lvl + buf if self.sl_mode == "level" else max(self.open30[len(self.data) - 1], c) + buf
            fill = c * (1 - self.spread_frac)
            risk = sl - fill
            if risk < self.min_stop_pips * PIP or risk > cap:
                return
            size = self._size(risk, c)
            if size > 0:
                self.sell(size=size, sl=sl, tp=fill - self.rr * risk, tag="S")

    # -- fade entries (invert mode) -----------------------------------------
    def _fade_long(self, c: float, o: float, lvl: float, buf: float):
        """Sell a limit at the upside breakout point; stop above the breakout body."""
        entry = lvl + buf
        if entry <= c:
            return
        body = max(self.open30[len(self.data) - 1], lvl)
        sl = body + 2 * buf
        fill = entry * (1 - self.spread_frac)
        risk = sl - fill
        cap = self.max_risk_atr * self.atr[-1] if self.max_risk_atr else np.inf
        if risk < self.min_stop_pips * PIP or risk > cap:
            return
        size = self._size(risk, entry)
        if size > 0:
            self.pending = self.sell(size=size, limit=entry, sl=sl,
                                     tp=fill - self.rr * risk, tag="FL")

    def _fade_short(self, c: float, o: float, lvl: float, buf: float):
        """Buy a limit at the downside breakout point; stop below the body."""
        entry = lvl - buf
        if entry >= c:
            return
        body = min(self.open30[len(self.data) - 1], lvl)
        sl = body - 2 * buf
        fill = entry * (1 + self.spread_frac)
        risk = fill - sl
        cap = self.max_risk_atr * self.atr[-1] if self.max_risk_atr else np.inf
        if risk < self.min_stop_pips * PIP or risk > cap:
            return
        size = self._size(risk, entry)
        if size > 0:
            self.pending = self.buy(size=size, limit=entry, sl=sl,
                                    tp=fill + self.rr * risk, tag="FS")

    def _manage_breakeven(self):
        """Move the stop to entry once price has run `be_at` R in favour.

        The trigger reads the previous completed bar, so the new stop is only
        active on later bars - no intrabar look-ahead.
        """
        if self.be_at <= 0 or not self.trades:
            return
        tr = self.trades[0]
        if not self.be_done:
            self.be_risk = abs(tr.entry_price - tr.sl)
            if not np.isfinite(self.be_risk) or self.be_risk <= 0:
                return
            self.be_side = 1 if tr.size > 0 else -1
            self.be_done = True
        i = len(self.data) - 2
        if i < tr.entry_bar:
            return
        moved = False
        if self.be_side > 0:
            if (self.data.High[i] - tr.entry_price) >= self.be_at * self.be_risk:
                new_sl = tr.entry_price + self.be_buffer_pips * PIP
                if new_sl > tr.sl:
                    tr.sl = new_sl
                    moved = True
        else:
            if (tr.entry_price - self.data.Low[i]) >= self.be_at * self.be_risk:
                new_sl = tr.entry_price - self.be_buffer_pips * PIP
                if new_sl < tr.sl:
                    tr.sl = new_sl
                    moved = True
        return moved

    # -- main loop ----------------------------------------------------------
    def next(self):
        ts = self.data.index[-1]
        boundary = (ts.minute + self.bar_minutes) % 30 == 0
        c, o = self.data.Close[-1], self.data.Open[-1]
        buf = self.buf_pips * PIP

        if self.position:
            self._cancel_pending()
            self.was_in_position = True
            self._manage_breakeven()
            if self.max_hold and (len(self.data) - 1 - self.trades[0].entry_bar) >= self.max_hold:
                self.position.close()
            if boundary:
                self.prev_close30 = c
            return

        if self.was_in_position:
            self.last_exit_time = ts
            self.was_in_position = False
            self.be_done = False
            self.be_risk = None

        if self.session_start >= 0 and not (self.session_start <= ts.hour < self.session_end):
            self._cancel_pending()
            if boundary:
                self.prev_close30 = c
            return

        self._cancel_pending()
        if not np.isfinite(self.ema[-1]):
            if boundary:
                self.prev_close30 = c
            return

        if self.invert:
            if self._long_setup(c):
                self._fade_long(c, o, self.lvl_hi[-1], buf)
            if self.both_sides and not self.orders and self._short_setup(c):
                self._fade_short(c, o, self.lvl_lo[-1], buf)
        else:
            if self._long_setup(c):
                self._enter_long(c, o, self.lvl_hi[-1], buf, boundary)
            if self.both_sides and not self.orders and self._short_setup(c):
                self._enter_short(c, o, self.lvl_lo[-1], buf, boundary)

        if boundary:
            self.prev_close30 = c


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def load_bars(tf: str, start: str | None = None, end: str | None = None,
              pair: str = "EURUSD") -> pd.DataFrame:
    data_dir = ROOT / "market_data" / pair / tf / "yearly"
    files = sorted(data_dir.glob(f"{pair.lower()}_{tf}_*.csv"))
    if not files:
        sys.exit(f"No {tf} CSVs in {data_dir}")
    if start:
        y0 = pd.Timestamp(start).year
        files = [f for f in files if int(f.stem.rsplit("_", 1)[-1]) >= y0]
    if end:
        y1 = pd.Timestamp(end).year
        files = [f for f in files if int(f.stem.rsplit("_", 1)[-1]) <= y1]
    parts = []
    for f in files:
        df = pd.read_csv(f, usecols=["timestamp", "open", "high", "low", "close", "volume"])
        df.index = pd.to_datetime(df.pop("timestamp"), unit="ms", utc=True)
        parts.append(df)
    out = pd.concat(parts)
    out = out[~out.index.duplicated(keep="first")].sort_index()
    out = out.rename(columns=str.title)
    if start:
        out = out.loc[pd.Timestamp(start, tz="UTC"):]
    if end:
        out = out.loc[:pd.Timestamp(end, tz="UTC")]
    return out[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def build_arrays(df5: pd.DataFrame, cfg: dict) -> dict:
    m = (df5.resample(TF)
            .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
            .dropna())
    hi, lo, cl = m["High"].to_numpy(), m["Low"].to_numpy(), m["Close"].to_numpy()
    e = ema(cl, cfg["ema_n"])
    at = atr(hi, lo, cl, cfg["atr_n"])
    n = cfg["pivot_n"]
    arr = {
        "ema": e, "atr": at,
        "ema_slope": e - pd.Series(e).shift(20).to_numpy(),
        "atr_ratio": at / pd.Series(at).rolling(100).mean().to_numpy(),
        "atr_ratio_long": at / pd.Series(at).rolling(1000).mean().to_numpy(),
        "lvl_hi": pivot_level(hi, n, "high"),
        "lvl_lo": pivot_level(lo, n, "low"),
        "age_hi": pivot_age(hi, n, "high"),
        "age_lo": pivot_age(lo, n, "low"),
        "pb_long": pullback_touch(hi, lo, e, at, cfg["pb_window"], cfg["pb_atr"], "long"),
        "pb_short": pullback_touch(hi, lo, e, at, cfg["pb_window"], cfg["pb_atr"], "short"),
        "lvl_time_hi": pivot_time(hi, n, "high", m.index),
        "lvl_time_lo": pivot_time(lo, n, "low", m.index),
    }
    touch_long = (lo - e) <= cfg["pb_atr"] * at
    touch_short = -(hi - e) <= cfg["pb_atr"] * at
    bt = pd.Series(m.index.to_numpy())
    arr["pb_time_long"] = bt.where(touch_long).ffill().to_numpy()
    arr["pb_time_short"] = bt.where(touch_short).ffill().to_numpy()
    arr["since_pb_long"] = bars_since(touch_long)
    arr["since_pb_short"] = bars_since(touch_short)
    avail = m.index + pd.Timedelta(TF)
    idx5 = df5.index
    out = {k: pd.Series(v, index=avail).reindex(idx5, method="ffill").to_numpy()
           for k, v in arr.items()}
    out["open30"] = pd.Series(m["Open"].to_numpy(), index=m.index).reindex(idx5, method="ffill").to_numpy()
    return out


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def trade_pips(trades: pd.DataFrame) -> pd.Series:
    sign = np.where(trades["Size"] > 0, 1, -1)
    return (trades["ExitPrice"] - trades["EntryPrice"]) * sign / PIP


def yearly_returns(eq: pd.Series) -> dict:
    e = eq.resample("YE").last()
    e = pd.concat([pd.Series([eq.iloc[0]], index=[eq.index[0]]), e])
    e = e[~e.index.duplicated(keep="last")]
    return {str(k.year): round(float(v), 2) for k, v in (e.pct_change().dropna() * 100).items()}


def run_one(df5: pd.DataFrame, arrays: dict, cfg: dict, spread_pips: float) -> dict:
    class S(Breakout5m):
        pass

    for k, v in cfg.items():
        setattr(S, k, v)
    spread_rel = (spread_pips * PIP) / float(df5["Close"].iloc[-1])
    S.arrays = arrays
    S.spread_frac = spread_rel
    S.bar_minutes = int(df5.index.to_series().diff().median().total_seconds() // 60)

    bt = Backtest(df5, S, cash=100_000, spread=spread_rel, commission=0.0,
                  margin=0.02, exclusive_orders=True, finalize_trades=True,
                  trade_on_close=(cfg["entry_mode"] == "close"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        stats = bt.run()
    ambig = sum(1 for w in caught
                if issubclass(w.category, UserWarning) and "contingent" in str(w.message))

    trades = stats["_trades"].copy()
    extra = {"trades": len(trades), "same_bar_sl_ambiguous": ambig}
    if len(trades):
        pips = trade_pips(trades)
        risk = (trades["EntryPrice"] - trades["SL"]).abs()
        r = pips * PIP / risk.replace(0, np.nan)
        extra.update({
            "win_rate_%": round(100 * (pips > 0).mean(), 2),
            "expectancy_pips": round(float(pips.mean()), 3),
            "expectancy_R": round(float(r.mean()), 3),
            "median_pips": round(float(pips.median()), 3),
            "avg_win_pips": round(float(pips[pips > 0].mean()), 2),
            "avg_loss_pips": round(float(pips[pips <= 0].mean()), 2),
            "avg_risk_pips": round(float((risk / PIP).mean()), 2),
            "long_share_%": round(100 * (trades["Size"] > 0).mean(), 1),
            "avg_hold_h": round(trades["Duration"].dt.total_seconds().div(3600).mean(), 1),
        })

    keep = ["Start", "End", "Duration", "Return [%]", "Buy & Hold return [%]",
            "Max. Drawdown [%]", "Sharpe Ratio", "Sortino Ratio", "Profit Factor",
            "Win Rate [%]", "# Trades", "Avg. Trade [%]", "Exposure Time [%]",
            "CAGR [%]", "Calmar Ratio"]
    summary = {}
    for k in keep:
        if k in stats.index:
            v = stats[k]
            summary[k] = float(v) if isinstance(v, (int, float, np.floating)) else str(v)
    return {"stats": summary, "extra": extra, "trades": trades,
            "equity": stats["_equity_curve"]["Equity"].copy()}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--spread-pips", type=float, default=0.2, help="per side")
    p.add_argument("--risk-pct", type=float, default=0.01)
    p.add_argument("--pivot-n", type=int, default=10)
    p.add_argument("--pb-window", type=int, default=25)
    p.add_argument("--pb-atr", type=float, default=0.5)
    p.add_argument("--pb-recency", type=int, default=25,
                   help="max 30m bars since the last pullback touch")
    p.add_argument("--buf-pips", type=float, default=1.0)
    p.add_argument("--rr", type=float, default=1.5)
    p.add_argument("--max-hold", type=int, default=0)
    p.add_argument("--max-risk-atr", type=float, default=1.5)
    p.add_argument("--exec-tf", default="5m", choices=["1m", "5m"])
    p.add_argument("--pair", default="EURUSD")
    p.add_argument("--session-start", type=int, default=-1,
                   help="UTC hour (inclusive) to allow entries; -1 disables")
    p.add_argument("--session-end", type=int, default=-1,
                   help="UTC hour (exclusive) to allow entries")
    p.add_argument("--max-dist-atr", type=float, default=0.0,
                   help="skip entries further than this many ATR from the EMA (0 = off)")
    p.add_argument("--min-slope-atr", type=float, default=-1.0,
                   help="require |EMA slope over 20 30m bars| >= this many ATR (-1 = off)")
    p.add_argument("--max-atr-ratio", type=float, default=0.0,
                   help="require ATR / 100-bar mean ATR <= this (0 = off)")
    p.add_argument("--max-atr-ratio-long", type=float, default=0.0,
                   help="require ATR / 1000-bar mean ATR <= this (0 = off)")
    p.add_argument("--no-fresh", action="store_true",
                   help="allow re-using the same swing level / pullback after a trade")
    p.add_argument("--invert", action="store_true",
                   help="fade the breakout with limit orders instead of following it")
    p.add_argument("--be-at", type=float, default=0.0,
                   help="move stop to entry after price reaches this many R (0 = off)")
    p.add_argument("--be-buffer-pips", type=float, default=0.0,
                   help="leave this many pips beyond entry when moving to breakeven")
    p.add_argument("--long-only", action="store_true")
    p.add_argument("--levels", default="A,B,C")
    p.add_argument("--tag", default="base")
    p.add_argument("--sweep", action="store_true")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"loading {args.exec_tf} data ...", flush=True)
    df5 = load_bars(args.exec_tf, args.start, args.end, args.pair)
    print(f"exec bars={len(df5):,}  {df5.index[0]} -> {df5.index[-1]}", flush=True)

    base = dict(ema_n=200, atr_n=14, pivot_n=args.pivot_n, pb_window=args.pb_window,
                pb_atr=args.pb_atr, pb_recency=args.pb_recency,
                buf_pips=args.buf_pips, rr=args.rr,
                risk_pct=args.risk_pct, max_hold=args.max_hold, max_risk_atr=args.max_risk_atr,
                level_max_age=120, both_sides=not args.long_only,
                require_fresh_pullback=not args.no_fresh,
                require_fresh_level=not args.no_fresh,
                session_start=args.session_start, session_end=args.session_end,
                max_dist_atr=args.max_dist_atr,
                min_slope_atr=args.min_slope_atr, max_atr_ratio=args.max_atr_ratio,
                max_atr_ratio_long=args.max_atr_ratio_long,
                invert=args.invert, be_at=args.be_at,
                be_buffer_pips=args.be_buffer_pips)
    arrays = build_arrays(df5, base)

    results = {}
    for name in [n.strip() for n in args.levels.split(",") if n.strip()]:
        key = next((k for k in VARIANTS if k.startswith(name)), None)
        if key is None:
            continue
        cfg = {**base, **VARIANTS[key]}
        res = run_one(df5, arrays, cfg, args.spread_pips)
        res["equity"].rename("Equity").to_csv(OUT_DIR / f"exec5m_equity_{args.tag}_{key}.csv")
        res["trades"].to_csv(OUT_DIR / f"exec5m_trades_{args.tag}_{key}.csv", index=False)
        results[key] = res
        s, e = res["stats"], res["extra"]
        print(f"\n[{key}]")
        print(f"  return {s.get('Return [%]', float('nan')):.2f}%   CAGR {s.get('CAGR [%]', float('nan')):.2f}%"
              f"   maxDD {s.get('Max. Drawdown [%]', float('nan')):.2f}%"
              f"   Sharpe {s.get('Sharpe Ratio', float('nan')):.2f}"
              f"   PF {s.get('Profit Factor', float('nan')):.2f}")
        print(f"  trades {e['trades']}  win {e.get('win_rate_%', float('nan')):.1f}%"
              f"  exp {e.get('expectancy_pips', float('nan')):.2f} pips"
              f" ({e.get('expectancy_R', float('nan')):.3f} R)"
              f"  avg risk {e.get('avg_risk_pips', float('nan')):.1f} pips"
              f"  hold {e.get('avg_hold_h', float('nan')):.1f} h"
              f"  long {e.get('long_share_%', float('nan')):.0f}%"
              f"  ambiguous {e['same_bar_sl_ambiguous']}")
        print(f"  yearly: {yearly_returns(res['equity'])}")

    if args.sweep:
        rows = []
        grid = [(piv, buf, pba, pbr, side)
                for piv in (8, 20)
                for buf in (1.0, 2.0)
                for pba, pbr in ((0.0, 6), (0.5, 25))
                for side in ("A", "B", "C")]
        print(f"\nsweep: {len(grid)} runs", flush=True)
        for piv, buf, pba, pbr, side in grid:
            key = next(k for k in VARIANTS if k.startswith(side))
            cfg = {**base, **VARIANTS[key], "pivot_n": piv, "buf_pips": buf,
                   "pb_atr": pba, "pb_recency": pbr}
            arr = arrays if (piv == base["pivot_n"] and pba == base["pb_atr"]
                             and pbr == base["pb_recency"]) else build_arrays(df5, cfg)
            try:
                res = run_one(df5, arr, cfg, args.spread_pips)
            except Exception as exc:  # noqa: BLE001
                print("skip", key, piv, buf, pba, pbr, exc)
                continue
            s, e = res["stats"], res["extra"]
            row = {"variant": key, "pivot_n": piv, "buf_pips": buf,
                   "pb_atr": pba, "pb_recency": pbr, "trades": e["trades"],
                   "return_%": s.get("Return [%]"), "cagr_%": s.get("CAGR [%]"),
                   "maxdd_%": s.get("Max. Drawdown [%]"), "sharpe": s.get("Sharpe Ratio"),
                   "pf": s.get("Profit Factor"), "win_%": e.get("win_rate_%"),
                   "exp_pips": e.get("expectancy_pips"), "exp_R": e.get("expectancy_R")}
            rows.append(row)
            print(f"  {key} piv={piv} buf={buf} pb=({pba},{pbr}) "
                  f"ret={row['return_%']:.1f}% pf={row['pf']:.2f} n={row['trades']}", flush=True)
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
