"""
产品模型 - 基金/ETF/LOF/现金
"""
from datetime import datetime

from app.extensions import db


class Instrument(db.Model):
    __tablename__ = "instruments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), unique=True, nullable=False, comment="产品代码")
    name = db.Column(db.String(200), nullable=False, comment="产品名称")
    instrument_type = db.Column(db.String(20), nullable=False, comment="类型: fund/etf/lof/cash")
    market = db.Column(db.String(50), default="", comment="市场")
    trade_mode = db.Column(db.String(30), default="eod_nav", comment="交易方式: exchange_traded/eod_nav")
    default_account_type = db.Column(db.String(20), default="core", comment="默认账户类型")
    default_strategy_template = db.Column(db.String(100), default="", comment="默认策略模板编码")
    is_dca_eligible = db.Column(db.Boolean, default=False, comment="是否可定投")
    status = db.Column(db.String(20), default="active", comment="状态: watchlist/active/paused/closed/archived")
    notes = db.Column(db.Text, default="", comment="备注")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    positions = db.relationship("Position", backref="instrument", lazy="dynamic")
    trades = db.relationship("Trade", backref="instrument", lazy="dynamic")
    signals = db.relationship("Signal", backref="instrument", lazy="dynamic")
    market_data = db.relationship("MarketData", backref="instrument", lazy="dynamic")
    strategy_assignments = db.relationship("StrategyAssignment", backref="instrument", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Instrument {self.symbol}: {self.name}>"
