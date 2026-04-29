from __future__ import annotations

from datetime import timedelta

from app.models.market_data import MarketData
from app.models.strategy_assignment import StrategyAssignment
from app.models.strategy_template import StrategyTemplate


def _price(row: MarketData) -> float | None:
    value = row.close if row.close is not None else row.nav
    if value is None or value <= 0:
        return None
    return float(value)


def _round_ratio(value: float | None) -> float:
    return round(float(value or 0), 4)


class StrategyPerformanceService:
    """Strategy-level performance from assigned instrument market history."""

    @staticmethod
    def get_performance(days: int = 7) -> list[dict]:
        templates = StrategyTemplate.query.order_by(
            StrategyTemplate.account_type.asc(),
            StrategyTemplate.template_code.asc(),
        ).all()
        results = []
        for template in templates:
            assignments = StrategyAssignment.query.filter_by(
                template_id=template.id,
                status="active",
            ).all()
            if not assignments:
                continue

            series = StrategyPerformanceService._build_strategy_series(
                [assignment.instrument_id for assignment in assignments],
                days=days,
            )
            values = [point["value"] for point in series]
            returns = [
                current / previous - 1
                for previous, current in zip(values, values[1:])
                if previous > 0
            ]
            peak = None
            max_drawdown = 0.0
            for value in values:
                peak = value if peak is None else max(peak, value)
                if peak and peak > 0:
                    max_drawdown = min(max_drawdown, value / peak - 1)

            return_7d = values[-1] / values[0] - 1 if len(values) >= 2 else 0.0
            win_rate = (
                sum(1 for value in returns if value > 0) / len(returns)
                if returns
                else 0.0
            )
            results.append(
                {
                    "strategy_id": template.id,
                    "strategy_code": template.template_code,
                    "strategy_name": template.template_name,
                    "account_type": template.account_type,
                    "return_7d": _round_ratio(return_7d),
                    "win_rate": _round_ratio(win_rate),
                    "max_drawdown": _round_ratio(max_drawdown),
                    "status": template.status,
                    "instrument_count": len({assignment.instrument_id for assignment in assignments}),
                    "series": series,
                }
            )
        return results

    @staticmethod
    def _build_strategy_series(instrument_ids: list[int], days: int) -> list[dict]:
        max_date = (
            MarketData.query.filter(MarketData.instrument_id.in_(instrument_ids))
            .with_entities(MarketData.trade_date)
            .order_by(MarketData.trade_date.desc())
            .first()
        )
        if max_date is None:
            return []

        start_date = max_date[0] - timedelta(days=max(days, 0))
        rows = (
            MarketData.query.filter(
                MarketData.instrument_id.in_(instrument_ids),
                MarketData.trade_date >= start_date,
            )
            .order_by(MarketData.trade_date.asc(), MarketData.instrument_id.asc())
            .all()
        )

        base_prices: dict[int, float] = {}
        latest_prices: dict[int, float] = {}
        rows_by_date = {}
        for row in rows:
            rows_by_date.setdefault(row.trade_date, []).append(row)

        series = []
        for trade_date, day_rows in rows_by_date.items():
            for row in day_rows:
                price = _price(row)
                if price is None:
                    continue
                base_prices.setdefault(row.instrument_id, price)
                latest_prices[row.instrument_id] = price

            relatives = [
                latest_prices[instrument_id] / base_prices[instrument_id]
                for instrument_id in latest_prices
                if instrument_id in base_prices and base_prices[instrument_id] > 0
            ]
            if not relatives:
                continue

            series.append(
                {
                    "date": trade_date.isoformat(),
                    "value": _round_ratio(sum(relatives) / len(relatives)),
                }
            )
        return series
