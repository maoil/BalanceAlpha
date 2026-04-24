"""
Manual off-exchange fund pending-order workflow.
"""
from datetime import date, datetime
from typing import Optional

from app.extensions import db
from app.models.manual_fund_order import ManualFundOrder
from app.models.trade import Trade
from app.services.log_service import LogService
from app.services.position_service import PositionService
from app.services.trading_calendar_service import TradingCalendarService


class ManualFundOrderService:
    """Create pending confirmation records for manual fund buys."""

    @staticmethod
    def should_create_pending_order(instrument, side: str) -> bool:
        return (
            instrument.instrument_type == "fund"
            and instrument.trade_mode == "eod_nav"
            and side == "buy"
        )

    @staticmethod
    def _get_confirm_cycle(instrument) -> int:
        cycle = int(instrument.dca_confirm_cycle or 1)
        if cycle not in {1, 2}:
            raise ValueError("dca_confirm_cycle must be 1 or 2")
        return cycle

    @staticmethod
    def create_pending_order(data: dict, instrument) -> ManualFundOrder:
        if not ManualFundOrderService.should_create_pending_order(instrument, "buy"):
            raise ValueError("Instrument does not support manual fund pending orders")

        amount = float(data.get("amount", 0))
        fee = float(data.get("fee", 0))
        order_date = data.get("trade_date", date.today())

        if amount <= 0:
            raise ValueError("amount must be positive")
        if fee < 0:
            raise ValueError("fee must be non-negative")

        order = ManualFundOrder(
            account_id=int(data["account_id"]),
            instrument_id=int(data["instrument_id"]),
            order_date=order_date,
            expected_confirm_date=TradingCalendarService.add_trading_days(
                order_date,
                ManualFundOrderService._get_confirm_cycle(instrument),
            ),
            amount=amount,
            fee=fee,
            status="pending",
            reason_code=data.get("reason_code", ""),
            notes=data.get("notes", ""),
        )
        db.session.add(order)
        db.session.commit()
        return order

    @staticmethod
    def get_by_id(order_id: int) -> Optional[ManualFundOrder]:
        return db.session.get(ManualFundOrder, order_id)

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
        nav_date = ManualFundOrderService._normalize_quote_date(quote.get("nav_date"))
        if not nav or not nav_date:
            return None

        return {
            "nav": float(nav),
            "nav_date": nav_date,
        }

    @staticmethod
    def confirm_order(order_id: int, run_date: date | None = None) -> dict:
        order = ManualFundOrderService.get_by_id(order_id)
        if order is None:
            raise LookupError("Manual fund order not found")

        if order.linked_trade_id and order.linked_trade:
            return {"order": order, "trade": order.linked_trade, "created": False}

        if order.status != "pending":
            raise ValueError("Manual fund order is not pending")

        run_date = run_date or date.today()
        if run_date < order.expected_confirm_date:
            raise ValueError("Manual fund order is not ready for confirmation")

        quote = ManualFundOrderService._fetch_confirm_quote(order.instrument)
        if not quote:
            raise ValueError("NAV is not ready")

        nav = float(quote["nav"])
        nav_date = quote["nav_date"]
        if nav_date < order.expected_confirm_date:
            raise ValueError("NAV is not ready")
        if nav <= 0:
            raise ValueError("NAV must be positive")

        confirm_quantity = (order.amount - (order.fee or 0.0)) / nav
        if confirm_quantity <= 0:
            raise ValueError("Confirmed quantity must be positive")

        trade = Trade(
            account_id=order.account_id,
            instrument_id=order.instrument_id,
            trade_date=nav_date,
            trade_type="subscribe",
            side="buy",
            quantity=confirm_quantity,
            price=nav,
            amount=order.amount,
            fee=order.fee or 0.0,
            reason_code=order.reason_code or "manual_fund_confirmed",
            notes=order.notes or "",
            source_type="manual_fund_order",
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

        db.session.commit()
        PositionService.recalculate_weights()
        db.session.commit()

        LogService.log(
            log_type="manual",
            level="info",
            module="manual_fund_order",
            message=(
                f"Confirmed manual fund order {order.id}: "
                f"{confirm_quantity} @ {nav}"
            ),
            context={"order_id": order.id, "trade_id": trade.id},
        )

        return {"order": order, "trade": trade, "created": True}

    @staticmethod
    def confirm_due_orders(run_date: date | None = None) -> dict[str, int]:
        run_date = run_date or date.today()
        orders = ManualFundOrder.query.filter(
            ManualFundOrder.status == "pending",
            ManualFundOrder.expected_confirm_date <= run_date,
        ).order_by(
            ManualFundOrder.expected_confirm_date.asc(),
            ManualFundOrder.id.asc(),
        ).all()

        confirmed = 0
        skipped = 0

        for order in orders:
            try:
                result = ManualFundOrderService.confirm_order(
                    order.id,
                    run_date=run_date,
                )
            except (LookupError, ValueError):
                skipped += 1
                continue

            if result.get("created"):
                confirmed += 1
            else:
                skipped += 1

        return {"confirmed": confirmed, "skipped": skipped}
