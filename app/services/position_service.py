"""
Position management service.
"""
from datetime import date
from typing import Optional

from app.extensions import db
from app.models.market_data import MarketData
from app.models.position import Position
from app.utils.constants import PositionStatus


class PositionService:
    """Position business logic."""

    @staticmethod
    def get_all(account_id: Optional[int] = None) -> list[Position]:
        query = Position.query.filter_by(position_status=PositionStatus.OPEN.value)
        if account_id:
            query = query.filter_by(account_id=account_id)
        return query.all()

    @staticmethod
    def get_by_id(position_id: int) -> Optional[Position]:
        return db.session.get(Position, position_id)

    @staticmethod
    def get_or_create(
        account_id: int,
        instrument_id: int,
        commit: bool = True,
    ) -> Position:
        position = Position.query.filter_by(
            account_id=account_id,
            instrument_id=instrument_id,
        ).first()

        if position:
            return position

        position = Position(
            account_id=account_id,
            instrument_id=instrument_id,
            quantity=0,
            avg_cost=0,
            position_status=PositionStatus.OPEN.value,
            opened_at=date.today(),
        )
        db.session.add(position)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return position

    @staticmethod
    def update_from_trade(
        account_id: int,
        instrument_id: int,
        side: str,
        quantity: float,
        price: float,
        commit: bool = True,
        recalculate_weights: Optional[bool] = None,
    ) -> Position:
        if recalculate_weights is None:
            recalculate_weights = commit

        position = PositionService.get_or_create(
            account_id=account_id,
            instrument_id=instrument_id,
            commit=False,
        )

        if side == "buy":
            total_cost = position.quantity * position.avg_cost + quantity * price
            position.quantity += quantity
            if position.quantity > 0:
                position.avg_cost = total_cost / position.quantity
            position.position_status = PositionStatus.OPEN.value
        else:
            position.quantity = max(0, position.quantity - quantity)
            position.position_status = (
                PositionStatus.CLOSED.value
                if position.quantity == 0
                else PositionStatus.OPEN.value
            )

        position.market_price = price
        position.update_market_value()

        if recalculate_weights:
            PositionService.recalculate_weights()

        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return position

    @staticmethod
    def refresh_market_prices() -> int:
        positions = Position.query.filter_by(
            position_status=PositionStatus.OPEN.value
        ).all()

        updated_count = 0
        for position in positions:
            latest = MarketData.query.filter_by(
                instrument_id=position.instrument_id
            ).order_by(MarketData.trade_date.desc()).first()

            if not latest:
                continue

            new_price = latest.close if latest.close else latest.nav
            if new_price and new_price > 0:
                position.market_price = new_price
                position.update_market_value()
                updated_count += 1

        PositionService.recalculate_weights()
        db.session.commit()
        return updated_count

    @staticmethod
    def recalculate_weights() -> None:
        from app.models.account import Account

        accounts = Account.query.all()
        for account in accounts:
            positions = Position.query.filter_by(
                account_id=account.id,
                position_status=PositionStatus.OPEN.value,
            ).all()
            total_value = sum(position.market_value or 0 for position in positions)
            for position in positions:
                if total_value > 0:
                    position.weight_in_account = (position.market_value or 0) / total_value
                else:
                    position.weight_in_account = 0

    @staticmethod
    def manual_update(position_id: int, data: dict) -> Optional[Position]:
        position = db.session.get(Position, position_id)
        if not position:
            return None

        for field in ["quantity", "avg_cost", "market_price"]:
            if field in data:
                setattr(position, field, float(data[field]))

        position.position_status = (
            PositionStatus.OPEN.value
            if (position.quantity or 0) > 0
            else PositionStatus.CLOSED.value
        )
        position.update_market_value()
        PositionService.recalculate_weights()
        db.session.commit()
        return position

    @staticmethod
    def create_manual(
        account_id: int,
        instrument_id: int,
        quantity: float,
        avg_cost: float,
        market_price: float,
        market_value: float,
        unrealized_pnl: float,
        unrealized_pnl_pct: float,
    ) -> Position:
        position = Position.query.filter_by(
            account_id=account_id,
            instrument_id=instrument_id,
        ).first()

        if position:
            position.quantity = quantity
            position.avg_cost = avg_cost
            position.market_price = market_price
            position.market_value = market_value
            position.unrealized_pnl = unrealized_pnl
            position.unrealized_pnl_pct = unrealized_pnl_pct
            position.position_status = PositionStatus.OPEN.value
        else:
            position = Position(
                account_id=account_id,
                instrument_id=instrument_id,
                quantity=quantity,
                avg_cost=avg_cost,
                market_price=market_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                position_status=PositionStatus.OPEN.value,
                opened_at=date.today(),
            )
            db.session.add(position)

        db.session.commit()
        PositionService.recalculate_weights()
        db.session.commit()
        return position

    @staticmethod
    def sync_instrument_account(
        instrument_id: int,
        account_type: str,
        commit: bool = True,
    ) -> int:
        from app.models.account import Account

        target_account = Account.query.filter_by(
            account_type=account_type,
            status="active",
        ).first()
        if target_account is None:
            raise ValueError(f"Active account not found for account type: {account_type}")

        positions = Position.query.filter_by(
            instrument_id=instrument_id,
            position_status=PositionStatus.OPEN.value,
        ).all()
        if not positions:
            return 0

        moved_count = 0
        target_position = Position.query.filter_by(
            account_id=target_account.id,
            instrument_id=instrument_id,
        ).first()

        for position in positions:
            if position.account_id == target_account.id:
                target_position = position
                continue

            moved_count += 1

            if target_position is None:
                position.account_id = target_account.id
                target_position = position
                continue

            existing_qty = target_position.quantity or 0.0
            incoming_qty = position.quantity or 0.0
            total_qty = existing_qty + incoming_qty
            total_cost = (
                existing_qty * (target_position.avg_cost or 0.0)
                + incoming_qty * (position.avg_cost or 0.0)
            )

            target_position.quantity = total_qty
            target_position.avg_cost = total_cost / total_qty if total_qty > 0 else 0.0
            if position.market_price:
                target_position.market_price = position.market_price
            if position.opened_at and (
                target_position.opened_at is None
                or position.opened_at < target_position.opened_at
            ):
                target_position.opened_at = position.opened_at
            target_position.position_status = (
                PositionStatus.OPEN.value
                if total_qty > 0
                else PositionStatus.CLOSED.value
            )
            target_position.update_market_value()

            position.quantity = 0.0
            position.position_status = PositionStatus.CLOSED.value
            position.update_market_value()

        if moved_count:
            PositionService.recalculate_weights()

        if commit:
            db.session.commit()
        else:
            db.session.flush()

        return moved_count
