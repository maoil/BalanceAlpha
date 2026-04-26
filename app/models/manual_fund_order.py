"""
Pending manual off-exchange fund buy orders.
"""
from app.extensions import db
from app.models.base_model import TimestampMixin


class ManualFundOrder(TimestampMixin, db.Model):
    __tablename__ = "manual_fund_orders"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    instrument_id = db.Column(db.Integer, db.ForeignKey("instruments.id"), nullable=False)
    order_date = db.Column(db.Date, nullable=False)
    expected_confirm_date = db.Column(db.Date, nullable=False)
    actual_confirm_date = db.Column(db.Date, nullable=True)
    trade_type = db.Column(db.String(30), default="subscribe", nullable=False)
    side = db.Column(db.String(10), default="buy", nullable=False)
    quantity = db.Column(db.Float, nullable=True)
    amount = db.Column(db.Float, nullable=False)
    fee = db.Column(db.Float, default=0.0)
    confirm_nav = db.Column(db.Float, nullable=True)
    confirm_quantity = db.Column(db.Float, nullable=True)
    quote_date_used = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="pending", nullable=False)
    reason_code = db.Column(db.String(100), default="")
    notes = db.Column(db.Text, default="")
    linked_trade_id = db.Column(db.Integer, db.ForeignKey("trades.id"), nullable=True)

    account = db.relationship(
        "Account", backref=db.backref("manual_fund_orders", lazy="dynamic")
    )
    instrument = db.relationship(
        "Instrument", backref=db.backref("manual_fund_orders", lazy="dynamic")
    )
    linked_trade = db.relationship(
        "Trade", backref=db.backref("manual_fund_order", uselist=False)
    )

    __table_args__ = (
        db.UniqueConstraint("linked_trade_id", name="uq_manual_fund_order_trade"),
        db.Index(
            "idx_manual_fund_orders_pending", "status", "expected_confirm_date"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ManualFundOrder account={self.account_id} "
            f"instrument={self.instrument_id} status={self.status}>"
        )
