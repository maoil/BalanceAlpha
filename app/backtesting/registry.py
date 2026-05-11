"""
Backtest Configuration Registry

This module contains the Python configuration registry for backtesting.
Each configuration entry binds a product to a data provider, strategy class,
and default parameters.
"""

from typing import Any, Callable, Dict, Optional, Type

from app.backtesting.providers import eastmoney_fund_nav, tencent_daily_ohlcv
from app.backtesting.strategies.cs_ai_momentum import (
    CSAIMomentumStrategy,
    add_cs_ai_indicators,
)
from app.vendor.backtesting import Strategy

import pandas as pd


class BacktestConfig:
    """Backtest configuration container."""

    def __init__(
        self,
        name: str,
        match: Dict[str, str],
        provider: Callable[..., pd.DataFrame],
        provider_symbol: str,
        strategy_class: Type[Strategy],
        prepare_data: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = None,
        default_params: Optional[Dict[str, Any]] = None,
        warmup_days: int = 120,
        backtest_config: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.match = match
        self.provider = provider
        self.provider_symbol = provider_symbol
        self.strategy_class = strategy_class
        self.prepare_data = prepare_data
        self.default_params = default_params or {}
        self.warmup_days = warmup_days
        self.backtest_config = backtest_config or {
            "commission": 0.0003,
            "exclusive_orders": True,
            "finalize_trades": True,
        }


BACKTEST_CONFIGS: Dict[str, BacktestConfig] = {
    "cs_ai_momentum": BacktestConfig(
        name="CS人工智能 - 易方达人工智能ETF联接C",
        match={"symbol": "012734"},
        provider=eastmoney_fund_nav,
        provider_symbol="012734",
        strategy_class=CSAIMomentumStrategy,
        prepare_data=add_cs_ai_indicators,
        default_params={"min_momentum": 0.06},
        warmup_days=30,
        backtest_config={
            "commission": 0.0,
            "exclusive_orders": True,
            "finalize_trades": True,
        },
    ),
}


def get_config_by_key(config_key: str) -> Optional[BacktestConfig]:
    """Get backtest configuration by key."""
    return BACKTEST_CONFIGS.get(config_key)


def get_config_by_match(symbol: str, market: Optional[str] = None) -> Optional[tuple[str, BacktestConfig]]:
    """
    Find a backtest configuration by matching symbol and market.

    Args:
        symbol: Product symbol
        market: Market code (optional)

    Returns:
        Tuple of (config_key, config) if found, None otherwise
    """
    for key, config in BACKTEST_CONFIGS.items():
        match = config.match
        if match.get("symbol") == symbol:
            if "market" not in match or market is None or match.get("market") == market:
                return key, config
    return None


def resolve_config(
    config_key: Optional[str],
    symbol: str,
    market: Optional[str] = None,
) -> tuple[str, BacktestConfig]:
    """
    Resolve backtest configuration from config key or symbol/market.

    Priority:
    1. If config_key is provided, use it to look up the config
    2. Otherwise, match by symbol and market

    Args:
        config_key: Explicit configuration key (e.g., "ai_etf_donchian")
        symbol: Product symbol
        market: Market code (optional)

    Returns:
        Tuple of (config_key, config)

    Raises:
        ValueError: If no matching configuration found
    """
    if config_key:
        config = get_config_by_key(config_key)
        if config is None:
            raise ValueError(f"Backtest configuration not found: {config_key}")
        return config_key, config

    result = get_config_by_match(symbol, market)
    if result is None:
        raise ValueError(
            f"No backtest configuration found for symbol={symbol}, market={market}. "
            "Please add a backtest_config_key to the instrument or register a new configuration."
        )
    return result


def list_configs() -> Dict[str, Dict[str, Any]]:
    """
    List all available backtest configurations.

    Returns:
        Dictionary of config_key -> config summary
    """
    return {
        key: {
            "name": config.name,
            "match": config.match,
            "provider": config.provider.__name__,
            "provider_symbol": config.provider_symbol,
            "strategy_class": config.strategy_class.__name__,
            "warmup_days": config.warmup_days,
        }
        for key, config in BACKTEST_CONFIGS.items()
    }


__all__ = [
    "BacktestConfig",
    "BACKTEST_CONFIGS",
    "get_config_by_key",
    "get_config_by_match",
    "resolve_config",
    "list_configs",
]
