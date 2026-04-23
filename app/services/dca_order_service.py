"""
DCA order confirmation service.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from app.extensions import db
from app.models.dca_order import DcaOrder
from app.models.trade import Trade
from app.services.position_service import PositionService
from app.services.trading_calendar_service import TradingCalendarService


class DcaOrderService:
    """Confirm pending DCA orders and create formal trades."""

    @staticmethod
    def _normalize_quote_date(raw_value: object) -> Optional[date]:
        if isinstance(raw_value, date):
            return raw_value
        if hasattr(raw_value, "date"):
            return raw_value.date()
        if isinstance(raw_value, str) and raw_value:
            try:
                return datetime.strptime(raw_value[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _fetch_confirm_quote(instrument) -> Optional[dict]:
        from app.services.fund_data_fetcher import FundDataFetcher

        quote = FundDataFetcher.get_realtime_nav(instrument.symbol)
        if not quote:
            return None

        nav = quote.get("nav")
        nav_date = DcaOrderService._normalize_quote_date(quote.get("nav_date"))
        if not nav or not nav_date:
            return None

        return {
            "nav": float(nav),
            "nav_date": nav_date,
        }

    @staticmethod
    def confirm_pending_orders(run_date: date | None = None) -> dict[str, int]:
        run_date = run_date or date.today()
        orders = DcaOrder.query.filter(
            DcaOrder.status == "pending",
            DcaOrder.expected_confirm_date <= run_date,
        ).order_by(DcaOrder.expected_confirm_date.asc(), DcaOrder.id.asc()).all()

        confirmed = 0
        skipped = 0

        for order in orders:
            if order.linked_trade_id:
                skipped += 1
                continue

            quote = DcaOrderService._fetch_confirm_quote(order.instrument)
            if not quote:
                skipped += 1
                continue

            nav = float(quote["nav"])
            nav_date = DcaOrderService._normalize_quote_date(quote["nav_date"])
            if not nav_date or nav_date < order.expected_confirm_date or nav <= 0:
                skipped += 1
                continue

            confirm_quantity = (order.amount - (order.fee or 0.0)) / nav
            if confirm_quantity <= 0:
                skipped += 1
                continue

            trade = Trade(
                account_id=order.account_id,
                instrument_id=order.instrument_id,
                trade_date=nav_date,
                trade_type="dca_buy",
                side="buy",
                quantity=confirm_quantity,
                price=nav,
                amount=order.amount,
                fee=order.fee or 0.0,
                reason_code="auto_dca_confirmed",
                source_type="dca_order",
                source_id=order.id,
            )
            db.session.add(trade)
            db.session.flush()

            PositionService.update_from_trade(
                account_id=order.account_id,
                instrument_id=order.instrument_id,
                side="buy",
                quantity=confirm_quantity,
                price=nav,
                commit=False,
            )

            order.status = "confirmed"
            order.actual_confirm_date = nav_date
            order.confirm_nav = nav
            order.confirm_quantity = confirm_quantity
            order.quote_date_used = nav_date
            order.linked_trade_id = trade.id
            confirmed += 1

        db.session.commit()
        PositionService.recalculate_weights()
        db.session.commit()
        return {"confirmed": confirmed, "skipped": skipped}
