"""
Trade management service.
"""
from datetime import date
from typing import Optional

from app.extensions import db
from app.models.instrument import Instrument
from app.models.trade import Trade
from app.services.log_service import LogService
from app.services.manual_fund_order_service import ManualFundOrderService
from app.services.position_service import PositionService
from app.utils.constants import TRADE_TYPE_SIDE_MAP, TradeSide, TradeType


class TradeService:
    """Trade business logic."""

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
    def get_all(
        account_id: Optional[int] = None,
        instrument_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
    ) -> list[Trade]:
        query = Trade.query
        if account_id:
            query = query.filter_by(account_id=account_id)
        if instrument_id:
            query = query.filter_by(instrument_id=instrument_id)
        if start_date:
            query = query.filter(Trade.trade_date >= start_date)
        if end_date:
            query = query.filter(Trade.trade_date <= end_date)
        return query.order_by(Trade.trade_date.desc(), Trade.id.desc()).limit(limit).all()

    @staticmethod
    def get_by_id(trade_id: int) -> Optional[Trade]:
        return db.session.get(Trade, trade_id)

    @staticmethod
    def create(data: dict):
        trade_type = data["trade_type"]

        side = data.get("side", "")
        if not side:
            trade_type_enum = TradeType(trade_type)
            side = TRADE_TYPE_SIDE_MAP.get(trade_type_enum, TradeSide.BUY).value

        instrument = db.session.get(Instrument, int(data["instrument_id"]))
        if instrument is None:
            raise ValueError("Instrument not found")

        quantity = TradeService._coerce_float(data.get("quantity"))
        price = TradeService._coerce_float(data.get("price"))
        amount = TradeService._coerce_float(data.get("amount"))
        fee = TradeService._coerce_float(data.get("fee"))

        if price <= 0 and ManualFundOrderService.should_create_pending_order(
            instrument,
            side,
        ):
            return ManualFundOrderService.create_or_confirm(data, instrument, side)

        if price <= 0:
            raise ValueError("price must be positive")

        if quantity <= 0 and side == "buy" and amount > 0:
            net_amount = amount - fee
            if net_amount <= 0:
                raise ValueError("amount must be greater than fee")
            quantity = net_amount / price

        if quantity <= 0:
            raise ValueError("quantity must be positive")

        if amount == 0 and quantity > 0 and price > 0:
            amount = quantity * price

        trade = Trade(
            account_id=int(data["account_id"]),
            instrument_id=int(data["instrument_id"]),
            trade_date=data.get("trade_date", date.today()),
            trade_type=trade_type,
            side=side,
            quantity=quantity,
            price=price,
            amount=amount,
            fee=fee,
            reason_code=data.get("reason_code", ""),
            notes=data.get("notes", ""),
        )

        try:
            db.session.add(trade)
            db.session.flush()

            PositionService.update_from_trade(
                account_id=trade.account_id,
                instrument_id=trade.instrument_id,
                side=trade.side,
                quantity=trade.quantity,
                price=trade.price,
                commit=False,
                recalculate_weights=True,
            )

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        LogService.log(
            log_type="manual",
            level="info",
            module="trade",
            message=f"Recorded trade: {trade.side} {trade.quantity} @ {trade.price}",
            context={"trade_id": trade.id, "instrument_id": trade.instrument_id},
        )

        return trade

    @staticmethod
    def get_recent(limit: int = 10) -> list[Trade]:
        return Trade.query.order_by(Trade.trade_date.desc(), Trade.id.desc()).limit(limit).all()
