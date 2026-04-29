from __future__ import annotations

from datetime import date, timedelta

from app.models.market_data import MarketData
from app.models.position import Position
from app.models.trade import Trade
from app.utils.constants import PositionStatus


def _price(row: MarketData) -> float | None:
    value = row.close if row.close is not None else row.nav
    if value is None or value <= 0:
        return None
    return float(value)


def _round_money(value: float | None) -> float:
    return round(float(value or 0), 2)


def _round_ratio(value: float | None) -> float:
    return round(float(value or 0), 4)


class DashboardMetricsService:
    """Portfolio-level metrics derived from positions, trades, and market data."""

    @staticmethod
    def get_asset_trend(days: int = 30) -> dict:
        positions = Position.query.filter_by(
            position_status=PositionStatus.OPEN.value
        ).all()
        if not positions:
            return {
                "series": [],
                "summary": {
                    "start_assets": 0.0,
                    "end_assets": 0.0,
                    "total_return": 0.0,
                },
            }

        instrument_ids = [position.instrument_id for position in positions]
        max_date = (
            MarketData.query.filter(MarketData.instrument_id.in_(instrument_ids))
            .with_entities(MarketData.trade_date)
            .order_by(MarketData.trade_date.desc())
            .first()
        )
        if max_date is None:
            return {
                "series": [],
                "summary": {
                    "start_assets": 0.0,
                    "end_assets": 0.0,
                    "total_return": 0.0,
                },
            }

        start_date = max_date[0] - timedelta(days=max(days - 1, 0))
        rows = (
            MarketData.query.filter(
                MarketData.instrument_id.in_(instrument_ids),
                MarketData.trade_date >= start_date,
            )
            .order_by(MarketData.trade_date.asc(), MarketData.instrument_id.asc())
            .all()
        )

        quantities = {
            position.instrument_id: float(position.quantity or 0) for position in positions
        }
        latest_prices: dict[int, float] = {}
        rows_by_date: dict[date, list[MarketData]] = {}
        for row in rows:
            rows_by_date.setdefault(row.trade_date, []).append(row)

        series = []
        start_assets = None
        previous_assets = None
        for trade_date, day_rows in rows_by_date.items():
            for row in day_rows:
                price = _price(row)
                if price is not None:
                    latest_prices[row.instrument_id] = price

            total_assets = sum(
                quantities[instrument_id] * latest_prices[instrument_id]
                for instrument_id in quantities
                if instrument_id in latest_prices
            )
            if total_assets <= 0:
                continue

            if start_assets is None:
                start_assets = total_assets

            daily_return = (
                total_assets / previous_assets - 1 if previous_assets else 0.0
            )
            cumulative_return = (
                total_assets / start_assets - 1 if start_assets else 0.0
            )
            series.append(
                {
                    "date": trade_date.isoformat(),
                    "total_assets": _round_money(total_assets),
                    "net_value": _round_ratio(total_assets / start_assets),
                    "daily_return": _round_ratio(daily_return),
                    "cumulative_return": _round_ratio(cumulative_return),
                }
            )
            previous_assets = total_assets

        start_value = series[0]["total_assets"] if series else 0.0
        end_value = series[-1]["total_assets"] if series else 0.0
        return {
            "series": series,
            "summary": {
                "start_assets": start_value,
                "end_assets": end_value,
                "total_return": _round_ratio(end_value / start_value - 1)
                if start_value > 0
                else 0.0,
            },
        }

    @staticmethod
    def get_performance_summary() -> dict:
        positions = Position.query.filter_by(
            position_status=PositionStatus.OPEN.value
        ).all()
        total_assets = sum(position.market_value or 0 for position in positions)
        total_cost = sum(
            (position.quantity or 0) * (position.avg_cost or 0)
            for position in positions
        )
        unrealized_pnl = total_assets - total_cost
        trend = DashboardMetricsService.get_asset_trend(days=30)["series"]
        latest_point = trend[-1] if trend else None
        previous_point = trend[-2] if len(trend) >= 2 else None

        if latest_point and previous_point:
            today_pnl = latest_point["total_assets"] - previous_point["total_assets"]
            previous_assets = previous_point["total_assets"]
            as_of_date = latest_point["date"]
        else:
            today_pnl = sum(position.today_pnl or 0 for position in positions)
            previous_assets = total_assets - today_pnl
            as_of_date = latest_point["date"] if latest_point else None

        earliest_trade_date = (
            Trade.query.with_entities(Trade.trade_date)
            .order_by(Trade.trade_date.asc())
            .first()
        )
        latest_date = date.fromisoformat(as_of_date) if as_of_date else date.today()
        if earliest_trade_date:
            holding_days = max((latest_date - earliest_trade_date[0]).days, 1)
        else:
            opened_dates = [position.opened_at for position in positions if position.opened_at]
            start_date = min(opened_dates) if opened_dates else latest_date
            holding_days = max((latest_date - start_date).days, 1)

        cumulative_return = unrealized_pnl / total_cost if total_cost > 0 else 0.0
        annualized_return = (
            (1 + cumulative_return) ** (365 / holding_days) - 1
            if cumulative_return > -1
            else -1.0
        )

        return {
            "total_assets": _round_money(total_assets),
            "total_cost": _round_money(total_cost),
            "unrealized_pnl": _round_money(unrealized_pnl),
            "today_pnl": _round_money(today_pnl),
            "change_vs_yesterday": _round_money(today_pnl),
            "change_pct_vs_yesterday": _round_ratio(
                today_pnl / previous_assets if previous_assets else 0.0
            ),
            "cumulative_return": _round_ratio(cumulative_return),
            "annualized_return": _round_ratio(annualized_return),
            "as_of_date": as_of_date,
        }
