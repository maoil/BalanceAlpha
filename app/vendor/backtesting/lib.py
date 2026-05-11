"""
Collection of common building blocks, helper auxiliary functions and
composable strategy classes for reuse.
"""

from __future__ import annotations

import warnings
from collections import OrderedDict
from inspect import currentframe
from itertools import chain, compress, count
from numbers import Number
from typing import Callable, Generator, Optional, Sequence, Union

import numpy as np
import pandas as pd

from ._stats import compute_stats as _compute_stats
from ._util import _Array, _as_str
from .backtesting import Backtest, Strategy

__pdoc__ = {}


OHLCV_AGG = OrderedDict((
    ('Open', 'first'),
    ('High', 'max'),
    ('Low', 'min'),
    ('Close', 'last'),
    ('Volume', 'sum'),
))
"""Dictionary of rules for aggregating resampled OHLCV data frames."""

TRADES_AGG = OrderedDict((
    ('Size', 'sum'),
    ('EntryBar', 'first'),
    ('ExitBar', 'last'),
    ('EntryPrice', 'mean'),
    ('ExitPrice', 'mean'),
    ('PnL', 'sum'),
    ('ReturnPct', 'mean'),
    ('EntryTime', 'first'),
    ('ExitTime', 'last'),
    ('Duration', 'sum'),
))
"""Dictionary of rules for aggregating resampled trades data."""

_EQUITY_AGG = {
    'Equity': 'last',
    'DrawdownPct': 'max',
    'DrawdownDuration': 'max',
}


def barssince(condition: Sequence[bool], default=np.inf) -> int:
    """
    Return the number of bars since `condition` sequence was last `True`,
    or if never, return `default`.
    """
    return next(compress(range(len(condition)), reversed(condition)), default)


def cross(series1: Sequence, series2: Sequence) -> bool:
    """
    Return `True` if `series1` and `series2` just crossed
    (above or below) each other.
    """
    return crossover(series1, series2) or crossover(series2, series1)


def crossover(series1: Sequence, series2: Sequence) -> bool:
    """
    Return `True` if `series1` just crossed over (above) `series2`.
    """
    series1 = (
        series1.values if isinstance(series1, pd.Series) else
        (series1, series1) if isinstance(series1, Number) else
        series1)
    series2 = (
        series2.values if isinstance(series2, pd.Series) else
        (series2, series2) if isinstance(series2, Number) else
        series2)
    try:
        return series1[-2] < series2[-2] and series1[-1] > series2[-1]
    except IndexError:
        return False


def quantile(series: Sequence, quantile: Union[None, float] = None):
    """
    If `quantile` is `None`, return the quantile _rank_ of the last
    value of `series` wrt former series values.
    """
    if quantile is None:
        try:
            last, series = series[-1], series[:-1]
            return np.mean(series < last)
        except IndexError:
            return np.nan
    assert 0 <= quantile <= 1, "quantile must be within [0, 1]"
    return np.nanpercentile(series, quantile * 100)


def compute_stats(
        *,
        stats: pd.Series,
        data: pd.DataFrame,
        trades: pd.DataFrame = None,
        risk_free_rate: float = 0.) -> pd.Series:
    """
    (Re-)compute strategy performance metrics.
    """
    equity = stats._equity_curve.Equity
    if trades is None:
        trades = stats._trades
    else:
        equity = equity.copy()
        equity[:] = stats._equity_curve.Equity.iloc[0]
        for t in trades.itertuples(index=False):
            equity.iloc[t.EntryBar:] += t.PnL
    return _compute_stats(trades=trades, equity=equity.values, ohlc_data=data,
                          risk_free_rate=risk_free_rate, strategy_instance=stats._strategy)


def resample_apply(rule: str,
                   func: Optional[Callable[..., Sequence]],
                   series: Union[pd.Series, pd.DataFrame, _Array],
                   *args,
                   agg: Optional[Union[str, dict]] = None,
                   **kwargs):
    """
    Apply `func` (such as an indicator) to `series`, resampled to
    a time frame specified by `rule`.
    """
    if func is None:
        def func(x, *_, **__):
            return x
    assert callable(func), 'resample_apply(func=) must be callable'

    if not isinstance(series, (pd.Series, pd.DataFrame)):
        assert isinstance(series, _Array), \
            'resample_apply(series=) must be `pd.Series`, `pd.DataFrame`, ' \
            'or a `Strategy.data.*` array'
        series = series.s

    if agg is None:
        agg = OHLCV_AGG.get(getattr(series, 'name', ''), 'last')
        if isinstance(series, pd.DataFrame):
            agg = {column: OHLCV_AGG.get(column, 'last')
                   for column in series.columns}

    resampled = series.resample(rule, label='right').agg(agg).dropna()
    resampled.name = _as_str(series) + '[' + rule + ']'

    frame, level = currentframe(), 0
    while frame and level <= 3:
        frame = frame.f_back
        level += 1
        if isinstance(frame.f_locals.get('self'), Strategy):
            strategy_I = frame.f_locals['self'].I
            break
    else:
        def strategy_I(func, *args, **kwargs):
            return func(*args, **kwargs)

    def wrap_func(resampled, *args, **kwargs):
        result = func(resampled, *args, **kwargs)
        if not isinstance(result, pd.DataFrame) and not isinstance(result, pd.Series):
            result = np.asarray(result)
            if result.ndim == 1:
                result = pd.Series(result, name=resampled.name)
            elif result.ndim == 2:
                result = pd.DataFrame(result.T)
        if not isinstance(result.index, pd.DatetimeIndex):
            result.index = resampled.index
        result = result.reindex(index=series.index.union(resampled.index),
                                method='ffill').reindex(series.index)
        return result

    wrap_func.__name__ = func.__name__

    array = strategy_I(wrap_func, resampled, *args, **kwargs)
    return array


def random_ohlc_data(example_data: pd.DataFrame, *,
                     frac=1., random_state: Optional[int] = None) -> Generator[pd.DataFrame, None, None]:
    """OHLC data generator."""
    def shuffle(x):
        return x.sample(frac=frac, replace=frac > 1, random_state=random_state)

    if len(example_data.columns.intersection({'Open', 'High', 'Low', 'Close'})) != 4:
        raise ValueError("`data` must be a pandas.DataFrame with columns "
                         "'Open', 'High', 'Low', 'Close'")
    while True:
        df = shuffle(example_data)
        df.index = example_data.index
        padding = df.Close - df.Open.shift(-1)
        gaps = shuffle(example_data.Open.shift(-1) - example_data.Close)
        deltas = (padding + gaps).shift(1).fillna(0).cumsum()
        for key in ('Open', 'High', 'Low', 'Close'):
            df[key] += deltas
        yield df


class SignalStrategy(Strategy):
    """A simple helper strategy that operates on position entry/exit signals."""
    __entry_signal = (0,)
    __exit_signal = (False,)

    def set_signal(self, entry_size: Sequence[float],
                   exit_portion: Optional[Sequence[float]] = None,
                   *,
                   plot: bool = True):
        """Set entry/exit signal vectors (arrays)."""
        self.__entry_signal = self.I(
            lambda: pd.Series(entry_size, dtype=float).replace(0, np.nan),
            name='entry size', plot=plot, overlay=False, scatter=True, color='black')

        if exit_portion is not None:
            self.__exit_signal = self.I(
                lambda: pd.Series(exit_portion, dtype=float).replace(0, np.nan),
                name='exit portion', plot=plot, overlay=False, scatter=True, color='black')

    def next(self):
        super().next()

        exit_portion = self.__exit_signal[-1]
        if exit_portion > 0:
            for trade in self.trades:
                if trade.is_long:
                    trade.close(exit_portion)
        elif exit_portion < 0:
            for trade in self.trades:
                if trade.is_short:
                    trade.close(-exit_portion)

        entry_size = self.__entry_signal[-1]
        if entry_size > 0:
            self.buy(size=entry_size)
        elif entry_size < 0:
            self.sell(size=-entry_size)


class TrailingStrategy(Strategy):
    """A strategy with automatic trailing stop-loss."""
    __n_atr = 6.
    __atr = None

    def init(self):
        super().init()
        self.set_atr_periods()

    def set_atr_periods(self, periods: int = 100):
        """Set the lookback period for computing ATR."""
        hi, lo, c_prev = self.data.High, self.data.Low, pd.Series(self.data.Close).shift(1)
        tr = np.max([hi - lo, (c_prev - hi).abs(), (c_prev - lo).abs()], axis=0)
        atr = pd.Series(tr).rolling(periods).mean().bfill().values
        self.__atr = atr

    def set_trailing_sl(self, n_atr: float = 6):
        """Set the future trailing stop-loss as some multiple of ATR."""
        self.__n_atr = n_atr

    def set_trailing_pct(self, pct: float = .05):
        """Set the future trailing stop-loss as some percent below the current price."""
        assert 0 < pct < 1, 'Need pct= as rate, i.e. 5% == 0.05'
        pct_in_atr = np.mean(self.data.Close * pct / self.__atr)
        self.set_trailing_sl(pct_in_atr)

    def next(self):
        super().next()
        index = len(self.data) - 1
        for trade in self.trades:
            if trade.is_long:
                trade.sl = max(trade.sl or -np.inf,
                               self.data.Close[index] - self.__atr[index] * self.__n_atr)
            else:
                trade.sl = min(trade.sl or np.inf,
                               self.data.Close[index] + self.__atr[index] * self.__n_atr)


for cls in list(globals().values()):
    if isinstance(cls, type) and issubclass(cls, Strategy):
        __pdoc__[f'{cls.__name__}.__init__'] = False


__all__ = [getattr(v, '__name__', k)
           for k, v in globals().items()
           if ((callable(v) and getattr(v, '__module__', None) == __name__ or
                k.isupper()) and
               not getattr(v, '__name__', k).startswith('_'))]
