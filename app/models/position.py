"""
持仓模型 - 当前持仓快照
"""
from datetime import date

from app.extensions import db
from app.models.base_model import utcnow


class Position(db.Model):
    __tablename__ = "positions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    instrument_id = db.Column(db.Integer, db.ForeignKey("instruments.id"), nullable=False)
    quantity = db.Column(db.Float, default=0.0, comment="持仓份额/数量")
    avg_cost = db.Column(db.Float, default=0.0, comment="平均成本价")
    market_price = db.Column(db.Float, default=0.0, comment="最新市场价/净值")
    price_date = db.Column(db.String(20), default="", comment="报价日期 YYYY-MM-DD")
    market_value = db.Column(db.Float, default=0.0, comment="当前市值")
    unrealized_pnl = db.Column(db.Float, default=0.0, comment="总浮动盈亏")
    unrealized_pnl_pct = db.Column(db.Float, default=0.0, comment="总浮盈浮亏百分比")
    today_pnl = db.Column(db.Float, default=0.0, comment="今日盈亏")
    weight_in_account = db.Column(db.Float, default=0.0, comment="账户内权重")
    position_status = db.Column(db.String(20), default="open", comment="状态: open/closed")
    opened_at = db.Column(db.Date, default=date.today, comment="首次建仓日期")
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    # 唯一约束：同一账户同一产品只有一条持仓
    __table_args__ = (
        db.UniqueConstraint("account_id", "instrument_id", name="uq_account_instrument_pos"),
    )

    def __repr__(self) -> str:
        return f"<Position account={self.account_id} instrument={self.instrument_id} qty={self.quantity}>"

    def update_market_value(self) -> None:
        """根据最新价格更新市值和盈亏"""
        if self.market_price and self.quantity:
            self.market_value = self.quantity * self.market_price
            cost_value = self.quantity * self.avg_cost
            self.unrealized_pnl = self.market_value - cost_value
            if cost_value > 0:
                self.unrealized_pnl_pct = self.unrealized_pnl / cost_value
            else:
                self.unrealized_pnl_pct = 0.0
