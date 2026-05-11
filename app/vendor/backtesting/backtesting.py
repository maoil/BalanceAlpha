"""
Core framework data structures.
Objects from this module can also be imported from the top-level
module directly, e.g.

    from backtesting import Backtest, Strategy
"""

from __future__ import annotations

import sys
import warnings
from abc import ABCMeta, abstractmethod
from copy import copy
from difflib import get_close_matches
from functools import lru_cache, partial
from itertools import chain, product, repeat
from math import copysign
from numbers import Number
from typing import Callable, List, Optional, Sequence, Tuple, Type, Union

import numpy as np
import pandas as pd
from numpy.random import default_rng

from ._stats import compute_stats, dummy_stats
from ._util import (
    SharedMemoryManager, _as_str, _Indicator, _Data, _batch, _indicator_warmup_nbars,
    _strategy_indicators, patch, try_, _tqdm,
)

__pdoc__ = {
    'Strategy.__init__': False,
    'Order.__init__': False,
    'Position.__init__': False,
    'Trade.__init__': False,
}


class Strategy(metaclass=ABCMeta):
    """
    A trading strategy base class. Extend this class and
    override methods `init` and `next` to define your own strategy.
    """
    def __init__(self, broker, data, params):
        self._indicators = []
        self._broker: _Broker = broker
        self._data: _Data = data
        self._params = self._check_params(params)

    def __repr__(self):
        return '<Strategy ' + str(self) + '>'

    def __str__(self):
        params = ','.join(f'{i[0]}={i[1]}' for i in zip(self._params.keys(),
                                                        map(_as_str, self._params.values())))
        if params:
            params = '(' + params + ')'
        return f'{self.__class__.__name__}{params}'

    def _check_params(self, params):
        for k, v in params.items():
            if not hasattr(self, k):
                suggestions = get_close_matches(k, (attr for attr in dir(self) if not attr.startswith('_')))
                hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
                raise AttributeError(
                    f"Strategy '{self.__class__.__name__}' is missing parameter '{k}'. "
                    "Strategy class should define parameters as class variables before they "
                    "can be optimized or run with." + hint)
            setattr(self, k, v)
        return params

    def I(self, func: Callable, *args,
          name=None, plot=True, overlay=None, color=None, scatter=False,
          **kwargs) -> np.ndarray:
        """Declare an indicator."""
        def _format_name(name: str) -> str:
            return name.format(*map(_as_str, args),
                               **dict(zip(kwargs.keys(), map(_as_str, kwargs.values()))))

        if name is None:
            params = ','.join(filter(None, map(_as_str, chain(args, kwargs.values()))))
            func_name = _as_str(func)
            name = (f'{func_name}({params})' if params else f'{func_name}')
        elif isinstance(name, str):
            name = _format_name(name)
        elif try_(lambda: all(isinstance(item, str) for item in name), False):
            name = [_format_name(item) for item in name]
        else:
            raise TypeError(f'Unexpected `name=` type {type(name)}; expected `str` or '
                            '`Sequence[str]`')

        try:
            value = func(*args, **kwargs)
        except Exception as e:
            raise RuntimeError(f'Indicator "{name}" error. See traceback above.') from e

        if isinstance(value, pd.DataFrame):
            value = value.values.T

        if value is not None:
            value = try_(lambda: np.asarray(value, order='C'), None)
        is_arraylike = bool(value is not None and value.shape)

        if is_arraylike and np.argmax(value.shape) == 0:
            value = value.T

        if isinstance(name, list) and (np.atleast_2d(value).shape[0] != len(name)):
            raise ValueError(
                f'Length of `name=` ({len(name)}) must agree with the number '
                f'of arrays the indicator returns ({value.shape[0]}).')

        if not is_arraylike or not 1 <= value.ndim <= 2 or value.shape[-1] != len(self._data.Close):
            raise ValueError(
                'Indicators must return (optionally a tuple of) numpy.arrays of same '
                f'length as `data` (data shape: {self._data.Close.shape}; indicator "{name}" '
                f'shape: {getattr(value, "shape", "")}, returned value: {value})')

        if overlay is None and np.issubdtype(value.dtype, np.number):
            x = value / self._data.Close
            with np.errstate(invalid='ignore'):
                overlay = ((x < 1.4) & (x > .6)).mean() > .6

        value = _Indicator(value, name=name, plot=plot, overlay=overlay,
                           color=color, scatter=scatter,
                           index=self.data.index)
        self._indicators.append(value)
        return value

    @abstractmethod
    def init(self):
        """Initialize the strategy. Override this method."""

    @abstractmethod
    def next(self):
        """Main strategy runtime method. Override this method."""

    class __FULL_EQUITY(float):
        def __repr__(self): return '.9999'
    _FULL_EQUITY = __FULL_EQUITY(1 - sys.float_info.epsilon)

    def buy(self, *,
            size: float = _FULL_EQUITY,
            limit: Optional[float] = None,
            stop: Optional[float] = None,
            sl: Optional[float] = None,
            tp: Optional[float] = None,
            tag: object = None) -> 'Order':
        """Place a new long order and return it."""
        assert 0 < size < 1 or round(size) == size >= 1, \
            "size must be a positive fraction of equity, or a positive whole number of units"
        return self._broker.new_order(size, limit, stop, sl, tp, tag)

    def sell(self, *,
             size: float = _FULL_EQUITY,
             limit: Optional[float] = None,
             stop: Optional[float] = None,
             sl: Optional[float] = None,
             tp: Optional[float] = None,
             tag: object = None) -> 'Order':
        """Place a new short order and return it."""
        assert 0 < size < 1 or round(size) == size >= 1, \
            "size must be a positive fraction of equity, or a positive whole number of units"
        return self._broker.new_order(-size, limit, stop, sl, tp, tag)

    @property
    def equity(self) -> float:
        """Current account equity (cash plus assets)."""
        return self._broker.equity

    @property
    def data(self) -> _Data:
        """Price data."""
        return self._data

    @property
    def position(self) -> 'Position':
        """Instance of Position."""
        return self._broker.position

    @property
    def orders(self) -> 'Tuple[Order, ...]':
        """List of orders waiting for execution."""
        return tuple(self._broker.orders)

    @property
    def trades(self) -> 'Tuple[Trade, ...]':
        """List of active trades."""
        return tuple(self._broker.trades)

    @property
    def closed_trades(self) -> 'Tuple[Trade, ...]':
        """List of settled trades."""
        return tuple(self._broker.closed_trades)


class Position:
    """Currently held asset position."""
    def __init__(self, broker: '_Broker'):
        self.__broker = broker

    def __bool__(self):
        return self.size != 0

    @property
    def size(self) -> float:
        """Position size in units of asset. Negative if position is short."""
        return sum(trade.size for trade in self.__broker.trades)

    @property
    def pl(self) -> float:
        """Profit (positive) or loss (negative) of the current position in cash units."""
        return sum(trade.pl for trade in self.__broker.trades)

    @property
    def pl_pct(self) -> float:
        """Profit (positive) or loss (negative) of the current position in percent."""
        total_invested = sum(trade.entry_price * abs(trade.size) for trade in self.__broker.trades)
        return (self.pl / total_invested) * 100 if total_invested else 0

    @property
    def is_long(self) -> bool:
        """True if the position is long (position size is positive)."""
        return self.size > 0

    @property
    def is_short(self) -> bool:
        """True if the position is short (position size is negative)."""
        return self.size < 0

    def close(self, portion: float = 1.):
        """Close portion of position by closing `portion` of each active trade."""
        for trade in self.__broker.trades:
            trade.close(portion)

    def __repr__(self):
        return f'<Position: {self.size} ({len(self.__broker.trades)} trades)>'


class _OutOfMoneyError(Exception):
    pass


class Order:
    """Place new orders through `Strategy.buy()` and `Strategy.sell()`."""
    def __init__(self, broker: '_Broker',
                 size: float,
                 limit_price: Optional[float] = None,
                 stop_price: Optional[float] = None,
                 sl_price: Optional[float] = None,
                 tp_price: Optional[float] = None,
                 parent_trade: Optional['Trade'] = None,
                 tag: object = None):
        self.__broker = broker
        assert size != 0
        self.__size = size
        self.__limit_price = limit_price
        self.__stop_price = stop_price
        self.__sl_price = sl_price
        self.__tp_price = tp_price
        self.__parent_trade = parent_trade
        self.__tag = tag

    def _replace(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, f'_{self.__class__.__qualname__}__{k}', v)
        return self

    def __repr__(self):
        return '<Order {}>'.format(', '.join(f'{param}={try_(lambda: round(value, 5), value)!r}'
                                             for param, value in (
                                                 ('size', self.__size),
                                                 ('limit', self.__limit_price),
                                                 ('stop', self.__stop_price),
                                                 ('sl', self.__sl_price),
                                                 ('tp', self.__tp_price),
                                                 ('contingent', self.is_contingent),
                                                 ('tag', self.__tag),
                                             ) if value is not None))

    def cancel(self):
        """Cancel the order."""
        self.__broker.orders.remove(self)
        trade = self.__parent_trade
        if trade:
            if self is trade._sl_order:
                trade._replace(sl_order=None)
            elif self is trade._tp_order:
                trade._replace(tp_order=None)

    @property
    def size(self) -> float:
        """Order size (negative for short orders)."""
        return self.__size

    @property
    def limit(self) -> Optional[float]:
        """Order limit price for limit orders, or None for market orders."""
        return self.__limit_price

    @property
    def stop(self) -> Optional[float]:
        """Order stop price for stop-limit/stop-market order."""
        return self.__stop_price

    @property
    def sl(self) -> Optional[float]:
        """A stop-loss price."""
        return self.__sl_price

    @property
    def tp(self) -> Optional[float]:
        """A take-profit price."""
        return self.__tp_price

    @property
    def parent_trade(self):
        return self.__parent_trade

    @property
    def tag(self):
        """Arbitrary value for tracking this order and the associated Trade."""
        return self.__tag

    @property
    def is_long(self):
        """True if the order is long (order size is positive)."""
        return self.__size > 0

    @property
    def is_short(self):
        """True if the order is short (order size is negative)."""
        return self.__size < 0

    @property
    def is_contingent(self):
        """True for contingent orders (OCO stop-loss and take-profit bracket orders)."""
        return bool((parent := self.__parent_trade) and
                    (self is parent._sl_order or
                     self is parent._tp_order))


class Trade:
    """When an `Order` is filled, it results in an active `Trade`."""
    def __init__(self, broker: '_Broker', size: int, entry_price: float, entry_bar, tag):
        self.__broker = broker
        self.__size = size
        self.__entry_price = entry_price
        self.__exit_price: Optional[float] = None
        self.__entry_bar: int = entry_bar
        self.__exit_bar: Optional[int] = None
        self.__sl_order: Optional[Order] = None
        self.__tp_order: Optional[Order] = None
        self.__tag = tag
        self._commissions = 0

    def __repr__(self):
        return f'<Trade size={self.__size} time={self.__entry_bar}-{self.__exit_bar or ""} ' \
               f'price={self.__entry_price}-{self.__exit_price or ""} pl={self.pl:.0f}' \
               f'{" tag=" + str(self.__tag) if self.__tag is not None else ""}>'

    def _replace(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, f'_{self.__class__.__qualname__}__{k}', v)
        return self

    def _copy(self, **kwargs):
        return copy(self)._replace(**kwargs)

    def close(self, portion: float = 1.):
        """Place new `Order` to close `portion` of the trade at next market price."""
        assert 0 < portion <= 1, "portion must be a fraction between 0 and 1"
        size = copysign(max(1, int(round(abs(self.__size) * portion))), -self.__size)
        order = Order(self.__broker, size, parent_trade=self, tag=self.__tag)
        self.__broker.orders.insert(0, order)

    @property
    def size(self):
        """Trade size (volume; negative for short trades)."""
        return self.__size

    @property
    def entry_price(self) -> float:
        """Trade entry price."""
        return self.__entry_price

    @property
    def exit_price(self) -> Optional[float]:
        """Trade exit price (or None if the trade is still active)."""
        return self.__exit_price

    @property
    def entry_bar(self) -> int:
        """Candlestick bar index of when the trade was entered."""
        return self.__entry_bar

    @property
    def exit_bar(self) -> Optional[int]:
        """Candlestick bar index of when the trade was exited."""
        return self.__exit_bar

    @property
    def tag(self):
        """A tag value inherited from the `Order` that opened this trade."""
        return self.__tag

    @property
    def _sl_order(self):
        return self.__sl_order

    @property
    def _tp_order(self):
        return self.__tp_order

    @property
    def entry_time(self) -> Union[pd.Timestamp, int]:
        """Datetime of when the trade was entered."""
        return self.__broker._data.index[self.__entry_bar]

    @property
    def exit_time(self) -> Optional[Union[pd.Timestamp, int]]:
        """Datetime of when the trade was exited."""
        if self.__exit_bar is None:
            return None
        return self.__broker._data.index[self.__exit_bar]

    @property
    def is_long(self):
        """True if the trade is long (trade size is positive)."""
        return self.__size > 0

    @property
    def is_short(self):
        """True if the trade is short (trade size is negative)."""
        return not self.is_long

    @property
    def pl(self):
        """Trade profit (positive) or loss (negative) in cash units."""
        price = self.__exit_price or self.__broker.last_price
        return (self.__size * (price - self.__entry_price)) - self._commissions

    @property
    def pl_pct(self):
        """Trade profit (positive) or loss (negative) in percent relative to trade entry price."""
        price = self.__exit_price or self.__broker.last_price
        gross_pl_pct = copysign(1, self.__size) * (price / self.__entry_price - 1)
        commission_pct = self._commissions / (abs(self.__size) * self.__entry_price)
        return gross_pl_pct - commission_pct

    @property
    def value(self):
        """Trade total value in cash (volume × price)."""
        price = self.__exit_price or self.__broker.last_price
        return abs(self.__size) * price

    @property
    def sl(self):
        """Stop-loss price at which to close the trade."""
        return self.__sl_order and self.__sl_order.stop

    @sl.setter
    def sl(self, price: float):
        self.__set_contingent('sl', price)

    @property
    def tp(self):
        """Take-profit price at which to close the trade."""
        return self.__tp_order and self.__tp_order.limit

    @tp.setter
    def tp(self, price: float):
        self.__set_contingent('tp', price)

    def __set_contingent(self, type, price):
        assert type in ('sl', 'tp')
        assert price is None or 0 < price < np.inf, f'Make sure 0 < price < inf! price: {price}'
        attr = f'_{self.__class__.__qualname__}__{type}_order'
        order: Order = getattr(self, attr)
        if order:
            order.cancel()
        if price:
            kwargs = {'stop': price} if type == 'sl' else {'limit': price}
            order = self.__broker.new_order(-self.size, trade=self, tag=self.tag, **kwargs)
            setattr(self, attr, order)


class _Broker:
    def __init__(self, *, data, cash, spread, commission, margin,
                 trade_on_close, hedging, exclusive_orders, index):
        assert cash > 0, f"cash should be > 0, is {cash}"
        assert 0 < margin <= 1, f"margin should be between 0 and 1, is {margin}"
        self._data: _Data = data
        self._cash = cash

        if callable(commission):
            self._commission = commission
        else:
            try:
                self._commission_fixed, self._commission_relative = commission
            except TypeError:
                self._commission_fixed, self._commission_relative = 0, commission
            assert self._commission_fixed >= 0, 'Need fixed cash commission in $ >= 0'
            assert -.1 <= self._commission_relative < .1, \
                ("commission should be between -10% "
                 f"(e.g. market-maker's rebates) and 10% (fees), is {self._commission_relative}")
            self._commission = self._commission_func

        self._spread = spread
        self._leverage = 1 / margin
        self._trade_on_close = trade_on_close
        self._hedging = hedging
        self._exclusive_orders = exclusive_orders

        self._equity = np.tile(np.nan, len(index))
        self.orders: List[Order] = []
        self.trades: List[Trade] = []
        self.position = Position(self)
        self.closed_trades: List[Trade] = []

    def _commission_func(self, order_size, price):
        return self._commission_fixed + abs(order_size) * price * self._commission_relative

    def __repr__(self):
        return f'<Broker: {self._cash:.0f}{self.position.pl:+.1f} ({len(self.trades)} trades)>'

    def new_order(self,
                  size: float,
                  limit: Optional[float] = None,
                  stop: Optional[float] = None,
                  sl: Optional[float] = None,
                  tp: Optional[float] = None,
                  tag: object = None,
                  *,
                  trade: Optional[Trade] = None) -> Order:
        size = float(size)
        stop = stop and float(stop)
        limit = limit and float(limit)
        sl = sl and float(sl)
        tp = tp and float(tp)

        is_long = size > 0
        assert size != 0, size
        adjusted_price = self._adjusted_price(size)

        if is_long:
            if not (sl or -np.inf) < (limit or stop or adjusted_price) < (tp or np.inf):
                raise ValueError(
                    "Long orders require: "
                    f"SL ({sl}) < LIMIT ({limit or stop or adjusted_price}) < TP ({tp})")
        else:
            if not (tp or -np.inf) < (limit or stop or adjusted_price) < (sl or np.inf):
                raise ValueError(
                    "Short orders require: "
                    f"TP ({tp}) < LIMIT ({limit or stop or adjusted_price}) < SL ({sl})")

        order = Order(self, size, limit, stop, sl, tp, trade, tag)

        if not trade:
            if self._exclusive_orders:
                for o in self.orders:
                    if not o.is_contingent:
                        o.cancel()
                for t in self.trades:
                    t.close()

        self.orders.insert(0 if trade and stop else len(self.orders), order)

        return order

    @property
    def last_price(self) -> float:
        """Price at the last (current) close."""
        return self._data.Close[-1]

    def _adjusted_price(self, size=None, price=None) -> float:
        return (price or self.last_price) * (1 + copysign(self._spread, size))

    @property
    def equity(self) -> float:
        return self._cash + sum(trade.pl for trade in self.trades)

    @property
    def margin_available(self) -> float:
        margin_used = sum(trade.value / self._leverage for trade in self.trades)
        return max(0, self.equity - margin_used)

    def next(self):
        i = self._i = len(self._data) - 1
        self._process_orders()

        equity = self.equity
        self._equity[i] = equity

        if equity <= 0:
            assert self.margin_available <= 0
            for trade in self.trades:
                self._close_trade(trade, self._data.Close[-1], i)
            self._cash = 0
            self._equity[i:] = 0
            raise _OutOfMoneyError

    def _process_orders(self):
        data = self._data
        open, high, low = data.Open[-1], data.High[-1], data.Low[-1]
        reprocess_orders = False

        for order in list(self.orders):
            if order not in self.orders:
                continue

            stop_price = order.stop
            if stop_price:
                is_stop_hit = ((high >= stop_price) if order.is_long else (low <= stop_price))
                if not is_stop_hit:
                    continue
                order._replace(stop_price=None)

            if order.limit:
                is_limit_hit = low <= order.limit if order.is_long else high >= order.limit
                is_limit_hit_before_stop = (is_limit_hit and
                                            (order.limit <= (stop_price or -np.inf)
                                             if order.is_long
                                             else order.limit >= (stop_price or np.inf)))
                if not is_limit_hit or is_limit_hit_before_stop:
                    continue

                price = (min(stop_price or open, order.limit)
                         if order.is_long else
                         max(stop_price or open, order.limit))
            else:
                prev_close = data.Close[-2]
                price = prev_close if self._trade_on_close and not order.is_contingent else open
                if stop_price:
                    price = max(price, stop_price) if order.is_long else min(price, stop_price)

            is_market_order = not order.limit and not stop_price
            time_index = (
                (self._i - 1)
                if is_market_order and self._trade_on_close and not order.is_contingent else
                self._i)

            if order.parent_trade:
                trade = order.parent_trade
                _prev_size = trade.size
                size = copysign(min(abs(_prev_size), abs(order.size)), order.size)
                if trade in self.trades:
                    self._reduce_trade(trade, price, size, time_index)
                    assert order.size != -_prev_size or trade not in self.trades
                    if price == stop_price:
                        trade._sl_order._replace(stop_price=stop_price)
                if order in (trade._sl_order, trade._tp_order):
                    assert order.size == -trade.size
                    assert order not in self.orders
                else:
                    assert abs(_prev_size) >= abs(size) >= 1
                    self.orders.remove(order)
                continue

            adjusted_price = self._adjusted_price(order.size, price)
            adjusted_price_plus_commission = \
                adjusted_price + self._commission(order.size, price) / abs(order.size)

            size = order.size
            if -1 < size < 1:
                size = copysign(int((self.margin_available * self._leverage * abs(size))
                                    // adjusted_price_plus_commission), size)
                if not size:
                    warnings.warn(
                        f'time={self._i}: Broker canceled the relative-sized order due to insufficient margin '
                        f'(equity={self.equity:.2f}, margin_available={self.margin_available:.2f}).',
                        category=UserWarning)
                    self.orders.remove(order)
                    continue
            assert size == round(size)
            need_size = int(size)

            if not self._hedging:
                for trade in list(self.trades):
                    if trade.is_long == order.is_long:
                        continue
                    assert trade.size * order.size < 0

                    if abs(need_size) >= abs(trade.size):
                        self._close_trade(trade, price, time_index)
                        need_size += trade.size
                    else:
                        self._reduce_trade(trade, price, need_size, time_index)
                        need_size = 0

                    if not need_size:
                        break

            if abs(need_size) * adjusted_price_plus_commission > \
                    self.margin_available * self._leverage:
                warnings.warn(
                    f'time={self._i}: Broker canceled the order due to insufficient margin '
                    f'(equity={self.equity:.2f}, margin_available={self.margin_available:.2f}).',
                    category=UserWarning)
                self.orders.remove(order)
                continue

            if need_size:
                self._open_trade(adjusted_price,
                                 need_size,
                                 order.sl,
                                 order.tp,
                                 time_index,
                                 order.tag)

                if order.sl or order.tp:
                    if is_market_order:
                        reprocess_orders = True
                    elif stop_price and not order.limit and order.tp and (
                            (order.is_long and order.tp <= high and (order.sl or -np.inf) < low) or
                            (order.is_short and order.tp >= low and (order.sl or np.inf) > high)):
                        reprocess_orders = True
                    elif (low <= (order.sl or -np.inf) <= high or
                          low <= (order.tp or -np.inf) <= high):
                        warnings.warn(
                            f"({data.index[-1]}) A contingent SL/TP order would execute in the "
                            "same bar its parent stop/limit order was turned into a trade. "
                            "Since we can't assert the precise intra-candle "
                            "price movement, the affected SL/TP order will instead be executed on "
                            "the next (matching) price/bar, making the result (of this trade) "
                            "somewhat dubious. "
                            "See https://github.com/kernc/backtesting.py/issues/119",
                            UserWarning)

            self.orders.remove(order)

        if reprocess_orders:
            self._process_orders()

    def _reduce_trade(self, trade: Trade, price: float, size: float, time_index: int):
        assert trade.size * size < 0
        assert abs(trade.size) >= abs(size)

        size_left = trade.size + size
        assert size_left * trade.size >= 0
        if not size_left:
            close_trade = trade
        else:
            trade._replace(size=size_left)
            if trade._sl_order:
                trade._sl_order._replace(size=-trade.size)
            if trade._tp_order:
                trade._tp_order._replace(size=-trade.size)

            close_trade = trade._copy(size=-size, sl_order=None, tp_order=None)
            self.trades.append(close_trade)

        self._close_trade(close_trade, price, time_index)

    def _close_trade(self, trade: Trade, price: float, time_index: int):
        self.trades.remove(trade)
        if trade._sl_order:
            self.orders.remove(trade._sl_order)
        if trade._tp_order:
            self.orders.remove(trade._tp_order)

        closed_trade = trade._replace(exit_price=price, exit_bar=time_index)
        self.closed_trades.append(closed_trade)
        commission = self._commission(trade.size, price)
        self._cash += trade.pl - commission
        trade_open_commission = self._commission(closed_trade.size, closed_trade.entry_price)
        closed_trade._commissions = commission + trade_open_commission

    def _open_trade(self, price: float, size: int,
                    sl: Optional[float], tp: Optional[float], time_index: int, tag):
        trade = Trade(self, size, price, time_index, tag)
        self.trades.append(trade)
        self._cash -= self._commission(size, price)
        if tp:
            trade.tp = tp
        if sl:
            trade.sl = sl


class Backtest:
    """
    Backtest a particular (parameterized) strategy on particular data.
    """
    def __init__(self,
                 data: pd.DataFrame,
                 strategy: Type[Strategy],
                 *,
                 cash: float = 10_000,
                 spread: float = .0,
                 commission: Union[float, Tuple[float, float]] = .0,
                 margin: float = 1.,
                 trade_on_close=False,
                 hedging=False,
                 exclusive_orders=False,
                 finalize_trades=False,
                 ):
        if not (isinstance(strategy, type) and issubclass(strategy, Strategy)):
            raise TypeError('`strategy` must be a Strategy sub-type')
        if not isinstance(data, pd.DataFrame):
            raise TypeError("`data` must be a pandas.DataFrame with columns")
        if not isinstance(spread, Number):
            raise TypeError('`spread` must be a float value, percent of '
                            'entry order price')
        if not isinstance(commission, (Number, tuple)) and not callable(commission):
            raise TypeError('`commission` must be a float percent of order value, '
                            'a tuple of `(fixed, relative)` commission, '
                            'or a function that takes `(order_size, price)`'
                            'and returns commission dollar value')

        data = data.copy(deep=False)

        if (not isinstance(data.index, pd.DatetimeIndex) and
            not isinstance(data.index, pd.RangeIndex) and
            (data.index.is_numeric() and
             (data.index > pd.Timestamp('1975').timestamp()).mean() > .8)):
            try:
                data.index = pd.to_datetime(data.index, infer_datetime_format=True)
            except ValueError:
                pass

        if 'Volume' not in data:
            data['Volume'] = np.nan

        if len(data) == 0:
            raise ValueError('OHLC `data` is empty')
        if len(data.columns.intersection({'Open', 'High', 'Low', 'Close', 'Volume'})) != 5:
            raise ValueError("`data` must be a pandas.DataFrame with columns "
                             "'Open', 'High', 'Low', 'Close', and (optionally) 'Volume'")
        if data[['Open', 'High', 'Low', 'Close']].isnull().values.any():
            raise ValueError('Some OHLC values are missing (NaN). '
                             'Please strip those lines with `df.dropna()` or '
                             'fill them in with `df.interpolate()` or whatever.')
        if np.any(data['Close'] > cash):
            warnings.warn('Some prices are larger than initial cash value. Note that fractional '
                          'trading is not supported by this class. If you want to trade Bitcoin, '
                          'increase initial cash, or trade μBTC or satoshis instead (see e.g. class '
                          '`backtesting.lib.FractionalBacktest`.',
                          stacklevel=2)
        if not data.index.is_monotonic_increasing:
            warnings.warn('Data index is not sorted in ascending order. Sorting.',
                          stacklevel=2)
            data = data.sort_index()
        if not isinstance(data.index, pd.DatetimeIndex):
            warnings.warn('Data index is not datetime. Assuming simple periods, '
                          'but `pd.DateTimeIndex` is advised.',
                          stacklevel=2)

        self._data: pd.DataFrame = data
        self._broker = partial(
            _Broker, cash=cash, spread=spread, commission=commission, margin=margin,
            trade_on_close=trade_on_close, hedging=hedging,
            exclusive_orders=exclusive_orders, index=data.index,
        )
        self._strategy = strategy
        self._results: Optional[pd.Series] = None
        self._finalize_trades = bool(finalize_trades)

    def run(self, **kwargs) -> pd.Series:
        """Run the backtest. Returns `pd.Series` with results and statistics."""
        data = _Data(self._data.copy(deep=False))
        broker: _Broker = self._broker(data=data)
        strategy: Strategy = self._strategy(broker, data, kwargs)

        strategy.init()
        data._update()

        indicator_attrs = _strategy_indicators(strategy)
        start = 1 + _indicator_warmup_nbars(strategy)

        with np.errstate(invalid='ignore'):

            for i in _tqdm(range(start, len(self._data)), desc=self.run.__qualname__,
                           unit='bar', mininterval=2, miniters=100):
                data._set_length(i + 1)
                for attr, indicator in indicator_attrs:
                    setattr(strategy, attr, indicator[..., :i + 1])

                try:
                    broker.next()
                except _OutOfMoneyError:
                    break

                strategy.next()
            else:
                if self._finalize_trades is True:
                    for trade in reversed(broker.trades):
                        trade.close()

                    if start < len(self._data):
                        try_(broker.next, exception=_OutOfMoneyError)
                elif len(broker.trades):
                    warnings.warn(
                        'Some trades remain open at the end of backtest. Use '
                        '`Backtest(..., finalize_trades=True)` to close them and '
                        'include them in stats.', stacklevel=2)

            data._set_length(len(self._data))

            equity = pd.Series(broker._equity).bfill().fillna(broker._cash).values
            self._results = compute_stats(
                trades=broker.closed_trades,
                equity=equity,
                ohlc_data=self._data,
                risk_free_rate=0.0,
                strategy_instance=strategy,
            )

        return self._results


__all__ = [getattr(v, '__name__', k)
           for k, v in globals().items()
           if ((callable(v) and getattr(v, '__module__', None) == __name__ or
                k.isupper()) and
               not getattr(v, '__name__', k).startswith('_'))]
