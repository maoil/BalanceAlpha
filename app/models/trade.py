"""
Confirmed trade records.
"""
from app.extensions import db
from app.models.base_model import CreatedAtMixin


class Trade(CreatedAtMixin, db.Model):
    __tablename__ = "trades"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    instrument_id = db.Column(db.Integer, db.ForeignKey("instruments.id"), nullable=False)
    trade_date = db.Column(db.Date, nullable=False, comment="交易日期")
    trade_type = db.Column(db.String(30), nullable=False, comment="交易类型")
    side = db.Column(db.String(10), nullable=False, comment="方向: buy/sell")
    quantity = db.Column(db.Float, default=0.0, comment="数量")
    price = db.Column(db.Float, default=0.0, comment="成交价/净值")
    amount = db.Column(db.Float, default=0.0, comment="成交金额")
    fee = db.Column(db.Float, default=0.0, comment="手续费")
    reason_code = db.Column(db.String(100), default="", comment="原因代码")
    notes = db.Column(db.Text, default="", comment="备注")
    source_type = db.Column(db.String(30), default="", comment="来源类型")
    source_id = db.Column(db.Integer, nullable=True, comment="来源记录 ID")

    __table_args__ = (
        db.Index("idx_trades_account_date", "account_id", "trade_date"),
        db.Index("idx_trades_source", "source_type", "source_id"),
    )

    def __repr__(self) -> str:
        return f"<Trade {self.trade_date} {self.side} {self.instrument_id}>"
