"""
交易记录服务
"""
from typing import Optional
from datetime import date, datetime

from app.extensions import db
from app.models.instrument import Instrument
from app.models.trade import Trade
from app.services.manual_fund_order_service import ManualFundOrderService
from app.services.position_service import PositionService
from app.services.log_service import LogService
from app.utils.constants import TRADE_TYPE_SIDE_MAP, TradeType, TradeSide


class TradeService:
    """交易记录业务逻辑"""

    @staticmethod
    def get_all(
        account_id: Optional[int] = None,
        instrument_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
    ) -> list[Trade]:
        """
        获取交易列表，支持多维度筛选

        Args:
            account_id: 账户筛选
            instrument_id: 产品筛选
            start_date: 起始日期
            end_date: 结束日期
            limit: 返回数量限制
        """
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
        """按 ID 获取交易"""
        return db.session.get(Trade, trade_id)

    @staticmethod
    def create(data: dict):
        """
        创建交易记录并自动更新持仓

        PRD 规则：
        - 每笔交易必须有时间、产品、账户、金额、方向
        - 不允许无产品、无账户的孤立交易记录

        Args:
            data: 交易数据字典
        Returns:
            新创建的交易对象
        """
        trade_type = data["trade_type"]

        # 自动推断方向
        side = data.get("side", "")
        if not side:
            trade_type_enum = TradeType(trade_type)
            side = TRADE_TYPE_SIDE_MAP.get(trade_type_enum, TradeSide.BUY).value

        instrument = db.session.get(Instrument, int(data["instrument_id"]))
        if instrument is None:
            raise ValueError("Instrument not found")

        if ManualFundOrderService.should_create_pending_order(instrument, side):
            return ManualFundOrderService.create_pending_order(data, instrument)

        quantity = float(data.get("quantity", 0))
        price = float(data.get("price", 0))
        amount = float(data.get("amount", 0))

        # 如果没有提供金额，自动计算
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
            fee=float(data.get("fee", 0)),
            reason_code=data.get("reason_code", ""),
            notes=data.get("notes", ""),
        )
        db.session.add(trade)
        db.session.commit()

        # 自动更新持仓
        PositionService.update_from_trade(
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
            side=trade.side,
            quantity=trade.quantity,
            price=trade.price,
        )

        # 记录日志
        LogService.log(
            log_type="manual",
            level="info",
            module="trade",
            message=f"录入交易: {trade.side} {trade.quantity}份 @ {trade.price}",
            context={"trade_id": trade.id, "instrument_id": trade.instrument_id},
        )

        return trade

    @staticmethod
    def get_recent(limit: int = 10) -> list[Trade]:
        """获取最近交易"""
        return Trade.query.order_by(
            Trade.trade_date.desc(), Trade.id.desc()
        ).limit(limit).all()
