"""
Fund Momentum Breakout Strategy

A momentum-based strategy designed for fund NAV data.
Uses shorter-term moving averages suitable for lower-volatility fund data.
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


def add_fund_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add fund-specific indicators to the DataFrame.

    Indicators added:
    - SMA3: 3-day simple moving average (entry MA)
    - SMA5: 5-day simple moving average (exit MA)
    - ROC20: 20-day rate of change (momentum)

    Args:
        df: DataFrame with OHLCV columns

    Returns:
        DataFrame with indicator columns added
    """
    data = df.copy()
    close = pd.Series(data["Close"], index=data.index)

    data["SMA3"] = sma(close, 3)
    data["SMA5"] = sma(close, 5)
    data["ROC20"] = close.pct_change(20)

    return data


class FundMomentumBreakout(Strategy):
    """
    Fund Momentum Breakout Strategy.

    Designed for fund NAV data which typically has lower volatility
    than individual stocks.

    Entry conditions:
    - 20-day momentum (ROC) >= min_momentum threshold
    - Price above 3-day SMA (short-term uptrend)

    Exit conditions:
    - Momentum turns negative
    - OR price breaks below 5-day SMA

    Parameters:
        min_momentum: Minimum ROC20 value for entry (default: 0.02 = 2%)
    """

    min_momentum = 0.02

    def init(self):
        self.entry_ma = self.I(identity, self.data.SMA3, name="SMA 3")
        self.exit_ma = self.I(identity, self.data.SMA5, name="SMA 5")
        self.momentum = self.I(identity, self.data.ROC20, name="ROC20", overlay=False)

    def next(self):
        price = self.data.Close[-1]

        if not self.position:
            if (
                self.momentum[-1] >= self.min_momentum
                and price > self.entry_ma[-1]
            ):
                self.buy()
        else:
            if self.momentum[-1] < 0 or price < self.exit_ma[-1]:
                self.position.close()


__all__ = ["FundMomentumBreakout", "add_fund_indicators"]
