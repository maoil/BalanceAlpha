"""
Trading-day helpers for fund DCA.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from functools import lru_cache


class TradingCalendarService:
    """Centralized trading-calendar logic."""

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_trade_dates() -> tuple[date, ...]:
        try:
            import akshare as ak
        except ImportError:
            return tuple()

        try:
            calendar_df = ak.tool_trade_date_hist_sina()
        except Exception:
            return tuple()

        dates: list[date] = []
        for value in calendar_df.iloc[:, 0].tolist():
            if hasattr(value, "date"):
                dates.append(value.date())
            elif isinstance(value, date):
                dates.append(value)
        return tuple(sorted(set(dates)))

    @staticmethod
    def is_trading_day(current_date: date) -> bool:
        trade_dates = TradingCalendarService._load_trade_dates()
        if trade_dates:
            return current_date in set(trade_dates)
        return current_date.weekday() < 5

    @staticmethod
    def get_next_trading_day(current_date: date) -> date:
        trade_dates = TradingCalendarService._load_trade_dates()
        if trade_dates:
            for trade_date in trade_dates:
                if trade_date >= current_date:
                    return trade_date

        candidate = current_date
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate

    @staticmethod
    def add_trading_days(current_date: date, offset: int) -> date:
        if offset <= 0:
            return TradingCalendarService.get_next_trading_day(current_date)

        trade_dates = TradingCalendarService._load_trade_dates()
        if trade_dates:
            eligible = [trade_date for trade_date in trade_dates if trade_date > current_date]
            if len(eligible) >= offset:
                return eligible[offset - 1]

        candidate = current_date
        remaining = offset
        while remaining > 0:
            candidate += timedelta(days=1)
            if TradingCalendarService.is_trading_day(candidate):
                remaining -= 1
        return candidate

    @staticmethod
    def get_month_anchor(year: int, month: int, schedule_day: int) -> date:
        return date(year, month, min(schedule_day, monthrange(year, month)[1]))

    @staticmethod
    def get_next_monthly_run_date(schedule_day: int, from_date: date) -> date:
        year = from_date.year
        month = from_date.month + 1
        if month > 12:
            year += 1
            month = 1
        anchor = TradingCalendarService.get_month_anchor(year, month, schedule_day)
        return TradingCalendarService.get_next_trading_day(anchor)
