"""
衡策投资系统 - 通用辅助函数
"""
from datetime import datetime, date
from typing import Optional


def now() -> datetime:
    """获取当前时间"""
    return datetime.now()


def today() -> date:
    """获取当前日期"""
    return date.today()


def safe_float(value, default: float = 0.0) -> float:
    """安全转换为浮点数，失败时返回 default（永远不返回 None）"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def to_float(value: object) -> Optional[float]:
    """
    将各种来源的值转换为 float。

    处理百分号、逗号、中文占位符、pandas NaN 等边界情况。
    如果无法转换则返回 None（区别于 safe_float 的 default 行为）。

    统一替代 fund_data_fetcher._to_float / market_data_service._to_float。
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace("%", "").replace(",", "").strip()
        if not value or value in {"--", "None", "nan", "NaN"}:
            return None
    try:
        import math
        f = float(value)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def round_metric(value: object, digits: int = 4) -> Optional[float]:
    """
    转换为 float 并四舍五入到指定小数位。

    统一替代 fund_data_fetcher._round_metric / market_data_service._round。
    """
    numeric = to_float(value)
    if numeric is None:
        return None
    return round(numeric, digits)


def format_pct(value: Optional[float], decimals: int = 2) -> str:
    """格式化百分比显示"""
    if value is None:
        return "--"
    return f"{value * 100:.{decimals}f}%"


def format_currency(value: Optional[float], decimals: int = 2) -> str:
    """格式化货币显示"""
    if value is None:
        return "--"
    return f"¥{value:,.{decimals}f}"


def format_number(value: Optional[float], decimals: int = 2) -> str:
    """格式化数字显示"""
    if value is None:
        return "--"
    return f"{value:,.{decimals}f}"
