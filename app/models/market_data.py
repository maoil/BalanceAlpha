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
    prev_close = db.Column(db.Float, comment="昨收价")
    volume = db.Column(db.Float, comment="成交量")
    amount = db.Column(db.Float, comment="成交额")
    turnover_rate = db.Column(db.Float, comment="换手率")
    amplitude = db.Column(db.Float, comment="振幅")
    open_gap_pct = db.Column(db.Float, comment="开盘跳空幅度")
    nav = db.Column(db.Float, comment="单位净值")
    acc_nav = db.Column(db.Float, comment="累计净值")
    est_nav = db.Column(db.Float, comment="估算净值")
    iopv = db.Column(db.Float, comment="IOPV")
    premium_discount_pct = db.Column(db.Float, comment="溢价折价率")
    premium_discount_zscore_20d = db.Column(db.Float, comment="20日溢价Z分数")
    ma20 = db.Column(db.Float, comment="20日均线")
    ma60 = db.Column(db.Float, comment="60日均线")
    ma120 = db.Column(db.Float, comment="120日均线")
    atr14 = db.Column(db.Float, comment="14日ATR")
    volatility_20d = db.Column(db.Float, comment="20日年化波动率")
    return_5d = db.Column(db.Float, comment="5日收益率")
    return_20d = db.Column(db.Float, comment="20日收益率")
    return_60d = db.Column(db.Float, comment="60日收益率")
    breakout_high_20d = db.Column(db.Float, comment="相对前20日高点突破幅度")
    breakdown_low_20d = db.Column(db.Float, comment="相对前20日低点距离")
    drawdown_60d = db.Column(db.Float, comment="60日回撤")
    max_drawdown_120d = db.Column(db.Float, comment="120日最大回撤")
    relative_strength_20d = db.Column(db.Float, comment="20日相对强弱")
    volume_ma20 = db.Column(db.Float, comment="20日均量")
    volume_ratio_5d = db.Column(db.Float, comment="相对前5日量比")
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 唯一约束 + 索引
    __table_args__ = (
        db.UniqueConstraint("instrument_id", "trade_date", name="uq_instrument_date"),
        db.Index("idx_market_data_instrument_date", "instrument_id", "trade_date"),
    )

    def __repr__(self) -> str:
        return f"<MarketData {self.instrument_id} {self.trade_date}>"
