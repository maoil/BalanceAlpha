"""
Donchian Momentum Chaser Strategy

A trend-following strategy based on Donchian channels and momentum.
"""

import pandas as pd
import numpy as np

from app.vendor.backtesting import Strategy


def identity(values):
    """Return values as-is (used for indicator wrapping)."""
    return values


def sma(values, n: int):
    """Calculate Simple Moving Average."""
    return pd.Series(values).rolling(n).mean().to_numpy()


def highest(values, n: int):
    """Calculate Highest High over n periods."""
    return pd.Series(values).rolling(n).max().to_numpy()


def lowest(values, n: int):
    """Calculate Lowest Low over n periods."""
    return pd.Series(values).rolling(n).min().to_numpy()


def roc(values, n: int):
    """Calculate Rate of Change over n periods."""
    s = pd.Series(values)
    return s.pct_change(n).to_numpy()


def add_donchian_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add Donchian channel and momentum indicators to the DataFrame.

    Indicators added:
    - SMA20: 20-day simple moving average
    - HH20: 20-day highest high (Donchian upper)
    - LL20: 20-day lowest low (Donchian lower)
    - ROC20: 20-day rate of change (momentum)

    Args:
        df: DataFrame with OHLCV columns

    Returns:
        DataFrame with indicator columns added
    """
    data = df.copy()
    close = pd.Series(data["Close"], index=data.index)
    high = pd.Series(data["High"], index=data.index)
    low = pd.Series(data["Low"], index=data.index)

    data["SMA20"] = sma(close, 20)
    data["HH20"] = highest(high, 20)
    data["LL20"] = lowest(low, 20)
    data["ROC20"] = roc(close, 20)

    return data


class DonchianMomentumChaser(Strategy):
    """
    Donchian Momentum Chaser Strategy.

    Combines Donchian channel breakouts with momentum filtering.

    Entry conditions:
    - Price breaks above 20-day highest high
    - 20-day momentum (ROC) >= min_momentum threshold
    - Price above 20-day SMA

    Exit conditions:
    - Price breaks below 20-day lowest low
    - OR price breaks below 20-day SMA

    Parameters:
        min_momentum: Minimum ROC20 value for entry (default: 0.06 = 6%)
    """

    min_momentum = 0.06

    def init(self):
        self.sma20 = self.I(identity, self.data.SMA20, name="SMA 20")
        self.hh20 = self.I(identity, self.data.HH20, name="HH 20")
        self.ll20 = self.I(identity, self.data.LL20, name="LL 20")
        self.momentum = self.I(identity, self.data.ROC20, name="ROC20", overlay=False)

    def next(self):
        price = self.data.Close[-1]

        if not self.position:
            if len(self.data) < 2:
                return

            prev_hh = self.hh20[-2] if len(self.hh20) >= 2 else self.hh20[-1]

            breakout = price > prev_hh
            momentum_ok = self.momentum[-1] >= self.min_momentum
            above_ma = price > self.sma20[-1]

            if breakout and momentum_ok and above_ma:
                self.buy()
        else:
            if len(self.data) < 2:
                return

            prev_ll = self.ll20[-2] if len(self.ll20) >= 2 else self.ll20[-1]

            break_low = price < prev_ll
            below_ma = price < self.sma20[-1]

            if break_low or below_ma:
                self.position.close()


__all__ = ["DonchianMomentumChaser", "add_donchian_indicators"]
