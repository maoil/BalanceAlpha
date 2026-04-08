"""
行情数据模型
"""
from datetime import datetime

from app.extensions import db


class MarketData(db.Model):
    __tablename__ = "market_data"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    instrument_id = db.Column(db.Integer, db.ForeignKey("instruments.id"), nullable=False)
    trade_date = db.Column(db.Date, nullable=False, comment="交易日期")
    open = db.Column(db.Float, comment="开盘价")
    high = db.Column(db.Float, comment="最高价")
    low = db.Column(db.Float, comment="最低价")
    close = db.Column(db.Float, comment="收盘价")
    volume = db.Column(db.Float, comment="成交量")
    nav = db.Column(db.Float, comment="单位净值")
    acc_nav = db.Column(db.Float, comment="累计净值")
    ma20 = db.Column(db.Float, comment="20日均线")
    ma60 = db.Column(db.Float, comment="60日均线")
    ma120 = db.Column(db.Float, comment="120日均线")
    drawdown_60d = db.Column(db.Float, comment="60日回撤")
    relative_strength_20d = db.Column(db.Float, comment="20日相对强弱")
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 唯一约束 + 索引
    __table_args__ = (
        db.UniqueConstraint("instrument_id", "trade_date", name="uq_instrument_date"),
        db.Index("idx_market_data_instrument_date", "instrument_id", "trade_date"),
    )

    def __repr__(self) -> str:
        return f"<MarketData {self.instrument_id} {self.trade_date}>"
