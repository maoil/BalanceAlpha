"""
Backtesting strategies for BalanceAlpha.

Each strategy module should export:
- A Strategy subclass
- A prepare_data function (optional) for computing indicators
"""


from .cs_ai_momentum import CSAIMomentumStrategy, add_cs_ai_indicators

__all__ = [
    "CSAIMomentumStrategy",
    "add_cs_ai_indicators",
]
