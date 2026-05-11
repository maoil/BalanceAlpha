"""
CS人工智能 Strategy

易方达人工智能ETF联接C 专用交易策略

买入条件（同时满足）：
- 价格突破近 10 日高点
- 10 日涨幅 >= 6%
- 价格站上 20 日均线

卖出条件（任一满足）：
- 价格跌破近 10 日低点
- 或跌破 20 日均线
"""

import pandas as pd

from app.vendor.backtesting import Strategy


def identity(values):
    """Return values as-is (used for indicator wrapping)."""
    return values


def sma(values, n: int):
    """Calculate Simple Moving Average."""
    return pd.Series(values).rolling(n).mean().to_numpy()


def highest(values, n: int):
    """Calculate Highest value in the past n periods."""
    return pd.Series(values).rolling(n).max().to_numpy()


def lowest(values, n: int):
    """Calculate Lowest value in the past n periods."""
    return pd.Series(values).rolling(n).min().to_numpy()


def roc(values, n: int):
    """Calculate Rate of Change over n periods."""
    s = pd.Series(values)
    return s.pct_change(n).to_numpy()


def add_cs_ai_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add CS人工智能 strategy indicators to the DataFrame.

    Indicators added:
    - HH10: 近10日最高价
    - LL10: 近10日最低价
    - SMA20: 20日均线
    - ROC10: 10日涨幅

    Args:
        df: DataFrame with OHLCV columns

    Returns:
        DataFrame with indicator columns added
    """
    data = df.copy()
    close = pd.Series(data["Close"], index=data.index)
    high = pd.Series(data["High"], index=data.index)
    low = pd.Series(data["Low"], index=data.index)

    data["HH10"] = highest(high, 10)
    data["LL10"] = lowest(low, 10)
    data["SMA20"] = sma(close, 20)
    data["ROC10"] = roc(close, 10)

    return data


class CSAIMomentumStrategy(Strategy):
    """
    CS人工智能 Momentum Strategy.

    专为易方达人工智能ETF联接C设计的趋势追踪策略。

    Entry conditions (ALL must be true):
    - 价格突破近10日高点 (Close > HH10 previous day)
    - 10日涨幅 >= min_momentum (default 6%)
    - 价格站上20日均线 (Close > SMA20)

    Exit conditions (ANY triggers exit):
    - 价格跌破近10日低点 (Close < LL10 previous day)
    - 或跌破20日均线 (Close < SMA20)

    Parameters:
        min_momentum: Minimum ROC10 value for entry (default: 0.06 = 6%)
    """

    min_momentum = 0.06

    def init(self):
        self.hh10 = self.I(identity, self.data.HH10, name="10日高点")
        self.ll10 = self.I(identity, self.data.LL10, name="10日低点")
        self.sma20 = self.I(identity, self.data.SMA20, name="20日均线")
        self.roc10 = self.I(identity, self.data.ROC10, name="10日涨幅", overlay=False)

    def next(self):
        price = self.data.Close[-1]

        if not self.position:
            if len(self.data) < 2:
                return
            
            prev_hh10 = self.hh10[-2] if len(self.hh10) >= 2 else self.hh10[-1]
            
            breakout = price > prev_hh10
            momentum_ok = self.roc10[-1] >= self.min_momentum
            above_ma = price > self.sma20[-1]

            if breakout and momentum_ok and above_ma:
                self.buy()
        else:
            if len(self.data) < 2:
                return
            
            prev_ll10 = self.ll10[-2] if len(self.ll10) >= 2 else self.ll10[-1]
            
            break_low = price < prev_ll10
            below_ma = price < self.sma20[-1]

            if break_low or below_ma:
                self.position.close()


__all__ = ["CSAIMomentumStrategy", "add_cs_ai_indicators"]
