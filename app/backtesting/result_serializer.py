"""
Backtest Result Serializer

Converts backtesting.py stats to a stable JSON structure for storage and API response.
"""

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


def _safe_float(value) -> Optional[float]:
    """Convert value to float, handling NaN and infinity."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    return None


def _safe_str(value) -> Optional[str]:
    """Convert value to string."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return str(value)
    return str(value)


def serialize_stats(stats: pd.Series) -> Dict[str, Any]:
    """
    Serialize backtesting.py stats to a dictionary.

    Args:
        stats: Stats Series returned by Backtest.run()

    Returns:
        Dictionary with summary statistics
    """
    return {
        "start": _safe_str(stats.get("Start")),
        "end": _safe_str(stats.get("End")),
        "duration": _safe_str(stats.get("Duration")),
        "exposure_time_pct": _safe_float(stats.get("Exposure Time [%]")),
        "equity_final": _safe_float(stats.get("Equity Final [$]")),
        "equity_peak": _safe_float(stats.get("Equity Peak [$]")),
        "return_pct": _safe_float(stats.get("Return [%]")),
        "buy_hold_return_pct": _safe_float(stats.get("Buy & Hold Return [%]")),
        "return_ann_pct": _safe_float(stats.get("Return (Ann.) [%]")),
        "volatility_ann_pct": _safe_float(stats.get("Volatility (Ann.) [%]")),
        "cagr_pct": _safe_float(stats.get("CAGR [%]")),
        "sharpe_ratio": _safe_float(stats.get("Sharpe Ratio")),
        "sortino_ratio": _safe_float(stats.get("Sortino Ratio")),
        "calmar_ratio": _safe_float(stats.get("Calmar Ratio")),
        "alpha_pct": _safe_float(stats.get("Alpha [%]")),
        "beta": _safe_float(stats.get("Beta")),
        "max_drawdown_pct": _safe_float(stats.get("Max. Drawdown [%]")),
        "avg_drawdown_pct": _safe_float(stats.get("Avg. Drawdown [%]")),
        "max_drawdown_duration": _safe_str(stats.get("Max. Drawdown Duration")),
        "avg_drawdown_duration": _safe_str(stats.get("Avg. Drawdown Duration")),
        "trade_count": int(stats.get("# Trades", 0)),
        "win_rate_pct": _safe_float(stats.get("Win Rate [%]")),
        "best_trade_pct": _safe_float(stats.get("Best Trade [%]")),
        "worst_trade_pct": _safe_float(stats.get("Worst Trade [%]")),
        "avg_trade_pct": _safe_float(stats.get("Avg. Trade [%]")),
        "max_trade_duration": _safe_str(stats.get("Max. Trade Duration")),
        "avg_trade_duration": _safe_str(stats.get("Avg. Trade Duration")),
        "profit_factor": _safe_float(stats.get("Profit Factor")),
        "expectancy_pct": _safe_float(stats.get("Expectancy [%]")),
        "sqn": _safe_float(stats.get("SQN")),
        "kelly_criterion": _safe_float(stats.get("Kelly Criterion")),
    }


def serialize_equity_curve(stats: pd.Series) -> list[Dict[str, Any]]:
    """
    Serialize equity curve to a list of data points.

    Args:
        stats: Stats Series returned by Backtest.run()

    Returns:
        List of equity curve data points
    """
    equity_curve = stats.get("_equity_curve")
    if equity_curve is None or equity_curve.empty:
        return []

    result = []
    for idx, row in equity_curve.iterrows():
        point = {
            "date": idx.isoformat() if isinstance(idx, pd.Timestamp) else str(idx),
            "equity": _safe_float(row.get("Equity")),
            "drawdown_pct": _safe_float(row.get("DrawdownPct")),
        }
        duration = row.get("DrawdownDuration")
        if duration is not None and pd.notna(duration):
            point["drawdown_duration"] = _safe_str(duration)
        result.append(point)

    return result


def serialize_trades(stats: pd.Series) -> list[Dict[str, Any]]:
    """
    Serialize trades to a list of trade records.

    Args:
        stats: Stats Series returned by Backtest.run()

    Returns:
        List of trade records
    """
    trades_df = stats.get("_trades")
    if trades_df is None or trades_df.empty:
        return []

    result = []
    for _, row in trades_df.iterrows():
        trade = {
            "size": _safe_float(row.get("Size")),
            "entry_bar": int(row.get("EntryBar", 0)),
            "exit_bar": int(row.get("ExitBar", 0)),
            "entry_price": _safe_float(row.get("EntryPrice")),
            "exit_price": _safe_float(row.get("ExitPrice")),
            "pnl": _safe_float(row.get("PnL")),
            "return_pct": _safe_float(row.get("ReturnPct")),
            "entry_time": _safe_str(row.get("EntryTime")),
            "exit_time": _safe_str(row.get("ExitTime")),
            "duration": _safe_str(row.get("Duration")),
        }

        sl = row.get("SL")
        if sl is not None and pd.notna(sl):
            trade["sl"] = _safe_float(sl)

        tp = row.get("TP")
        if tp is not None and pd.notna(tp):
            trade["tp"] = _safe_float(tp)

        tag = row.get("Tag")
        if tag is not None:
            trade["tag"] = str(tag)

        result.append(trade)

    return result


def serialize_backtest_result(
    stats: pd.Series,
    scope: Dict[str, Any],
    include_equity_curve: bool = True,
    include_trades: bool = True,
    html_path: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Serialize complete backtest result to JSON-compatible dictionary.

    Args:
        stats: Stats Series returned by Backtest.run()
        scope: Scope information (instrument, config, etc.)
        include_equity_curve: Whether to include full equity curve
        include_trades: Whether to include trade details
        html_path: Optional path to generated HTML chart
        error: Optional error message

    Returns:
        Complete result dictionary matching the spec
    """
    summary_stats = serialize_stats(stats)

    summary = {
        "start": summary_stats.get("start"),
        "end": summary_stats.get("end"),
        "equity_final": summary_stats.get("equity_final"),
        "return_pct": summary_stats.get("return_pct"),
        "buy_hold_return_pct": summary_stats.get("buy_hold_return_pct"),
        "max_drawdown_pct": summary_stats.get("max_drawdown_pct"),
        "sharpe_ratio": summary_stats.get("sharpe_ratio"),
        "trade_count": summary_stats.get("trade_count"),
        "win_rate_pct": summary_stats.get("win_rate_pct"),
    }

    result = {
        "scope": scope,
        "summary": summary,
        "equity_curve": serialize_equity_curve(stats) if include_equity_curve else [],
        "trades": serialize_trades(stats) if include_trades else [],
        "stats": summary_stats,
        "chart": {"html_path": html_path},
        "error": error,
    }

    return result


def create_scope(
    instrument_id: int,
    symbol: str,
    market: Optional[str],
    name: str,
    backtest_config_key: str,
    config_name: str,
    provider: str,
    provider_symbol: str,
    strategy_class: str,
) -> Dict[str, Any]:
    """
    Create scope dictionary for backtest result.

    Args:
        instrument_id: Instrument database ID
        symbol: Product symbol
        market: Market code
        name: Product name
        backtest_config_key: Configuration key
        config_name: Configuration display name
        provider: Data provider function name
        provider_symbol: Symbol passed to provider
        strategy_class: Strategy class name

    Returns:
        Scope dictionary
    """
    return {
        "instrument_id": instrument_id,
        "symbol": symbol,
        "market": market,
        "name": name,
        "backtest_config_key": backtest_config_key,
        "config_name": config_name,
        "provider": provider,
        "provider_symbol": provider_symbol,
        "strategy_class": strategy_class,
    }


__all__ = [
    "serialize_stats",
    "serialize_equity_curve",
    "serialize_trades",
    "serialize_backtest_result",
    "create_scope",
]
