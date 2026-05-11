"""
Backtesting.py engine vendored into BalanceAlpha.

Original source: https://github.com/kernc/backtesting.py
License: AGPL 3.0
"""

from .backtesting import Backtest, Strategy
from . import lib

__version__ = '0.3.3'
__all__ = ['Backtest', 'Strategy', 'lib']
