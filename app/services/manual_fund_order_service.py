"""
Manual off-exchange fund pending-order workflow.
"""
from datetime import date, datetime
from typing import Optional

from app.extensions import db
from app.models.manual_fund_order import ManualFundOrder
from app.models.market_data import MarketData
from app.models.trade import Trade
from app.services.log_service import LogService
from app.services.position_service import PositionService
from app.services.trading_calendar_service import TradingCalendarService


class ManualFundOrderService:
    """Create and confirm pending manual fund orders for off-exchange funds."""

    @staticmethod
    def should_create_pending_order(instrument, side: str) -> bool:
        confirm_cycle = getattr(instrument, "dca_confirm_cycle", None)
        if confirm_cycle is not None and int(confirm_cycle) == 0:
            return False

        return (
            instrument.instrument_type == "fund"
            and instrument.trade_mode == "eod_nav"
            and side in {"buy", "sell"}
        )

    @staticmethod
    def _get_confirm_cycle(instrument) -> int:
        cycle = int(instrument.dca_confirm_cycle or 1)
        instrument_text = " ".join(
            [
                str(getattr(instrument, "name", "") or ""),
                str(getattr(instrument, "market", "") or ""),
            ]
        ).upper()
        if "QDII" in instrument_text:
            cycle = max(cycle, 2)
        if cycle not in {1, 2}:
            raise ValueError("dca_confirm_cycle must be 1 or 2")
        return cycle

    @staticmethod
    def _coerce_float(value: object, default: float = 0.0) -> float:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return default
        return float(value)

    @staticmethod
    def _normalize_trade_type(trade_type: str, side: str) -> str:
        normalized = (trade_type or "").strip()
        if not normalized:
            return "subscribe" if side == "buy" else "redeem"
        if normalized == "buy":
            return "subscribe"
        if normalized == "sell":
            return "redeem"
        return normalized

    @staticmethod
    def _normalize_quote_date(raw_value: object) -> Optional[date]:
        if hasattr(raw_value, "date"):
            return raw_value.date()
        if isinstance(raw_value, date):
            return raw_value
        if isinstance(raw_value, str) and raw_value:
            try:
                return datetime.strptime(raw_value[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _extract_order_inputs(data: dict, side: str) -> tuple[float, float, float]:
        quantity = ManualFundOrderService._coerce_float(data.get("quantity"))
        amount = ManualFundOrderService._coerce_float(data.get("amount"))
        fee = ManualFundOrderService._coerce_float(data.get("fee"))

        if fee < 0:
            raise ValueError("fee must be non-negative")

        if side == "buy":
            if quantity <= 0 and amount <= 0:
                raise ValueError("buy order requires quantity or amount")
        elif quantity <= 0:
            raise ValueError("sell order requires quantity")

        return quantity, amount, fee

    @staticmethod
    def _resolve_trade_values(
        side: str,
        quantity: float,
        amount: float,
        fee: float,
        nav: float,
    ) -> tuple[float, float]:
        if nav <= 0:
            raise ValueError("NAV must be positive")

        if side == "buy":
            if quantity <= 0:
                net_amount = amount - fee
                if net_amount <= 0:
                    raise ValueError("amount must be greater than fee")
                quantity = net_amount / nav
            if amount <= 0:
                amount = quantity * nav
        else:
            if quantity <= 0:
                raise ValueError("sell order requires quantity")
            if amount <= 0:
                amount = quantity * nav

        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if amount <= 0:
            raise ValueError("amount must be positive")

        return quantity, amount

    @staticmethod
    def _build_expected_confirm_date(order_date: date, instrument) -> date:
        return TradingCalendarService.add_trading_days(
            order_date,
            ManualFundOrderService._get_confirm_cycle(instrument),
        )

    @staticmethod
    def _get_market_data_quote(instrument_id: int, quote_date: date) -> Optional[dict]:
        market_data = MarketData.query.filter_by(
            instrument_id=instrument_id,
            trade_date=quote_date,
        ).first()
        if not market_data:
            return None

        nav = float(market_data.nav or market_data.close or 0)
        if nav <= 0:
            return None

        return {"nav": nav, "nav_date": quote_date}

    @staticmethod
    def _fetch_trade_date_quote(instrument, trade_date: date) -> Optional[dict]:
        from app.services.fund_data_fetcher import FundDataFetcher
        if trade_date > date.today():
            return None
        cached_quote = ManualFundOrderService._get_market_data_quote(
            instrument.id,
            trade_date,
        )
        if cached_quote:
            return cached_quote

        history = FundDataFetcher.get_fund_nav_history_extended(
            instrument.symbol,
            start_date=trade_date.isoformat(),
            end_date=trade_date.isoformat(),
        )
        if history is not None and not history.empty:
            for _, row in history.iloc[::-1].iterrows():
                nav = ManualFundOrderService._coerce_float(row.get("nav"))
                nav_date = ManualFundOrderService._normalize_quote_date(
                    row.get("trade_date")
                )
                if nav > 0 and nav_date == trade_date:
                    return {"nav": nav, "nav_date": nav_date}

        quote = FundDataFetcher.get_realtime_nav(instrument.symbol)
        if not quote:
            return None

        nav = ManualFundOrderService._coerce_float(quote.get("nav"))
        nav_date = ManualFundOrderService._normalize_quote_date(quote.get("nav_date"))
        if nav <= 0 or nav_date != trade_date:
            return None

        return {"nav": nav, "nav_date": nav_date}

    @staticmethod
    def _create_trade_record(
        *,
        account_id: int,
        instrument_id: int,
        trade_type: str,
        side: str,
        quantity: float,
        amount: float,
        fee: float,
        nav: float,
        nav_date: date,
        reason_code: str,
        notes: str,
        source_type: str = "",
        source_id: int | None = None,
    ) -> Trade:
        trade = Trade(
            account_id=account_id,
            instrument_id=instrument_id,
            trade_date=nav_date,
            trade_type=trade_type,
            side=side,
            quantity=quantity,
            price=nav,
            amount=amount,
            fee=fee,
            reason_code=reason_code,
            notes=notes,
            source_type=source_type,
            source_id=source_id,
        )
        db.session.add(trade)
        db.session.flush()

        PositionService.update_from_trade(
            account_id=account_id,
            instrument_id=instrument_id,
            side=side,
            quantity=quantity,
            price=nav,
            commit=False,
            recalculate_weights=False,
        )
        return trade

    @staticmethod
    def create_pending_order(
        data: dict,
        instrument,
        side: str = "buy",
    ) -> ManualFundOrder:
        if not ManualFundOrderService.should_create_pending_order(instrument, side):
            raise ValueError("Instrument does not support manual fund pending orders")

        quantity, amount, fee = ManualFundOrderService._extract_order_inputs(
            data,
            side,
        )
        order_date = data.get("trade_date", date.today())

        order = ManualFundOrder(
            account_id=int(data["account_id"]),
            instrument_id=int(data["instrument_id"]),
            order_date=order_date,
            expected_confirm_date=ManualFundOrderService._build_expected_confirm_date(
                order_date,
                instrument,
            ),
            trade_type=ManualFundOrderService._normalize_trade_type(
                data.get("trade_type", ""),
                side,
            ),
            side=side,
            quantity=quantity if quantity > 0 else None,
            amount=amount,
            fee=fee,
            status="pending",
            reason_code=data.get("reason_code", ""),
            notes=data.get("notes", ""),
        )

        try:
            db.session.add(order)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        LogService.log(
            log_type="manual",
            level="info",
            module="manual_fund_order",
            message=(
                f"Created pending manual fund order {order.id}: "
                f"{side} {quantity or amount}"
            ),
            context={"order_id": order.id, "instrument_id": order.instrument_id},
        )

        return order

    @staticmethod
    def create_or_confirm(data: dict, instrument, side: str):
        if not ManualFundOrderService.should_create_pending_order(instrument, side):
            raise ValueError("Instrument does not support manual fund pending orders")

        quantity, amount, fee = ManualFundOrderService._extract_order_inputs(
            data,
            side,
        )
        order_date = data.get("trade_date", date.today())
        expected_confirm_date = ManualFundOrderService._build_expected_confirm_date(
            order_date,
            instrument,
        )

        if expected_confirm_date > date.today():
            return ManualFundOrderService.create_pending_order(data, instrument, side)

        quote = ManualFundOrderService._fetch_trade_date_quote(instrument, order_date)

        if not quote:
            return ManualFundOrderService.create_pending_order(data, instrument, side)

        nav = ManualFundOrderService._coerce_float(quote["nav"])
        nav_date = quote["nav_date"]
        trade_type = ManualFundOrderService._normalize_trade_type(
            data.get("trade_type", ""),
            side,
        )
        order = ManualFundOrder(
            account_id=int(data["account_id"]),
            instrument_id=int(data["instrument_id"]),
            order_date=order_date,
            expected_confirm_date=expected_confirm_date,
            actual_confirm_date=expected_confirm_date,
            trade_type=trade_type,
            side=side,
            quantity=quantity if quantity > 0 else None,
            amount=amount,
            fee=fee,
            confirm_nav=nav,
            quote_date_used=nav_date,
            status="confirmed",
            reason_code=data.get("reason_code", ""),
            notes=data.get("notes", ""),
        )
        quantity, amount = ManualFundOrderService._resolve_trade_values(
            side,
            quantity,
            amount,
            fee,
            nav,
        )
        order.confirm_quantity = quantity

        try:
            db.session.add(order)
            db.session.flush()

            trade = ManualFundOrderService._create_trade_record(
                account_id=int(data["account_id"]),
                instrument_id=int(data["instrument_id"]),
                trade_type=trade_type,
                side=side,
                quantity=quantity,
                amount=amount,
                fee=fee,
                nav=nav,
                nav_date=nav_date,
                reason_code=data.get("reason_code", ""),
                notes=data.get("notes", ""),
                source_type="manual_fund_order",
                source_id=order.id,
            )
            order.linked_trade = trade
            order.linked_trade_id = trade.id
            PositionService.recalculate_weights()
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        LogService.log(
            log_type="manual",
            level="info",
            module="trade",
            message=f"Recorded auto-nav trade: {trade.side} {trade.quantity} @ {trade.price}",
            context={"trade_id": trade.id, "instrument_id": trade.instrument_id},
        )

        return trade

    @staticmethod
    def get_by_id(order_id: int) -> Optional[ManualFundOrder]:
        return db.session.get(ManualFundOrder, order_id)

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

        quote = ManualFundOrderService._fetch_trade_date_quote(
            order.instrument,
            order.order_date,
        )
        if not quote:
            raise ValueError("NAV is not ready")

        nav = ManualFundOrderService._coerce_float(quote["nav"])
        nav_date = quote["nav_date"]
        quantity, amount = ManualFundOrderService._resolve_trade_values(
            order.side,
            ManualFundOrderService._coerce_float(order.quantity),
            ManualFundOrderService._coerce_float(order.amount),
            ManualFundOrderService._coerce_float(order.fee),
            nav,
        )

        try:
            trade = ManualFundOrderService._create_trade_record(
                account_id=order.account_id,
                instrument_id=order.instrument_id,
                trade_type=order.trade_type or (
                    "subscribe" if order.side == "buy" else "redeem"
                ),
                side=order.side,
                quantity=quantity,
                amount=amount,
                fee=order.fee or 0.0,
                nav=nav,
                nav_date=nav_date,
                reason_code=order.reason_code or "",
                notes=order.notes or "",
                source_type="manual_fund_order",
                source_id=order.id,
            )

            order.status = "confirmed"
            order.actual_confirm_date = order.expected_confirm_date
            order.confirm_nav = nav
            order.confirm_quantity = quantity
            order.quote_date_used = nav_date
            order.linked_trade_id = trade.id

            PositionService.recalculate_weights()
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        LogService.log(
            log_type="manual",
            level="info",
            module="manual_fund_order",
            message=(
                f"Confirmed manual fund order {order.id}: "
                f"{quantity} @ {nav}"
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
