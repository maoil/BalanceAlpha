"""
持仓管理服务
"""
from typing import Optional
from datetime import date

from app.extensions import db
from app.models.position import Position
from app.models.market_data import MarketData
from app.utils.constants import PositionStatus


class PositionService:
    """持仓管理业务逻辑"""

    @staticmethod
    def get_all(account_id: Optional[int] = None) -> list[Position]:
        """
        获取持仓列表

        Args:
            account_id: 按账户筛选，None 则返回全部
        """
        query = Position.query.filter_by(position_status=PositionStatus.OPEN.value)
        if account_id:
            query = query.filter_by(account_id=account_id)
        return query.all()

    @staticmethod
    def get_by_id(position_id: int) -> Optional[Position]:
        """按 ID 获取持仓"""
        return db.session.get(Position, position_id)

    @staticmethod
    def get_or_create(account_id: int, instrument_id: int) -> Position:
        """
        获取或创建持仓记录

        PRD 规则：同一账户同一产品只有一条持仓记录
        """
        position = Position.query.filter_by(
            account_id=account_id,
            instrument_id=instrument_id
        ).first()

        if not position:
            position = Position(
                account_id=account_id,
                instrument_id=instrument_id,
                quantity=0,
                avg_cost=0,
                position_status=PositionStatus.OPEN.value,
                opened_at=date.today(),
            )
            db.session.add(position)
            db.session.commit()

        return position

    @staticmethod
    def update_from_trade(
        account_id: int,
        instrument_id: int,
        side: str,
        quantity: float,
        price: float,
    ) -> Position:
        """
        根据交易更新持仓

        买入：加权平均成本计算
        卖出：减少数量，成本不变
        """
        position = PositionService.get_or_create(account_id, instrument_id)

        if side == "buy":
            # 加权平均成本
            total_cost = position.quantity * position.avg_cost + quantity * price
            position.quantity += quantity
            if position.quantity > 0:
                position.avg_cost = total_cost / position.quantity
            position.position_status = PositionStatus.OPEN.value
        else:
            # 卖出，减少数量
            position.quantity = max(0, position.quantity - quantity)
            if position.quantity == 0:
                position.position_status = PositionStatus.CLOSED.value

        # 更新市值
        position.market_price = price
        position.update_market_value()

        db.session.commit()
        return position

    @staticmethod
    def refresh_market_prices() -> int:
        """
        刷新所有持仓的市场价格（使用最新行情数据）

        Returns:
            更新的持仓数量
        """
        positions = Position.query.filter_by(
            position_status=PositionStatus.OPEN.value
        ).all()

        updated_count = 0
        for pos in positions:
            # 获取最新行情
            latest = MarketData.query.filter_by(
                instrument_id=pos.instrument_id
            ).order_by(MarketData.trade_date.desc()).first()

            if latest:
                # ETF/LOF 用 close 价格，场外基金用 nav
                new_price = latest.close if latest.close else latest.nav
                if new_price and new_price > 0:
                    pos.market_price = new_price
                    pos.update_market_value()
                    updated_count += 1

        # 更新权重
        PositionService.recalculate_weights()

        db.session.commit()
        return updated_count

    @staticmethod
    def recalculate_weights() -> None:
        """重新计算所有账户内持仓权重"""
        from app.models.account import Account

        accounts = Account.query.all()
        for account in accounts:
            positions = Position.query.filter_by(
                account_id=account.id,
                position_status=PositionStatus.OPEN.value
            ).all()

            total_value = sum(p.market_value or 0 for p in positions)
            for pos in positions:
                if total_value > 0:
                    pos.weight_in_account = (pos.market_value or 0) / total_value
                else:
                    pos.weight_in_account = 0

    @staticmethod
    def manual_update(position_id: int, data: dict) -> Optional[Position]:
        """手工修正持仓"""
        position = db.session.get(Position, position_id)
        if not position:
            return None

        for field in ["quantity", "avg_cost", "market_price"]:
            if field in data:
                setattr(position, field, float(data[field]))

        position.update_market_value()
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
        """
        手动录入持仓

        如果同账户同产品已有持仓，则更新；否则新建。

        Args:
            account_id: 账户 ID
            instrument_id: 产品 ID
            quantity: 份额
            avg_cost: 成本价（自动计算得出）
            market_price: 当前价格
            market_value: 市值
            unrealized_pnl: 浮动盈亏
            unrealized_pnl_pct: 盈亏百分比
        """
        position = Position.query.filter_by(
            account_id=account_id,
            instrument_id=instrument_id,
        ).first()

        if position:
            # 已存在则更新
            position.quantity = quantity
            position.avg_cost = avg_cost
            position.market_price = market_price
            position.market_value = market_value
            position.unrealized_pnl = unrealized_pnl
            position.unrealized_pnl_pct = unrealized_pnl_pct
            position.position_status = PositionStatus.OPEN.value
        else:
            # 新建
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

        # 重新计算权重
        PositionService.recalculate_weights()
        db.session.commit()

        return position

