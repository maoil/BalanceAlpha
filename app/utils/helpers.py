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
    """安全转换为浮点数"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


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
