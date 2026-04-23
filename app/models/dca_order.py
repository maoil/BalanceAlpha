"""
Pending and confirmed DCA orders.
"""
from app.extensions import db
from app.models.base_model import TimestampMixin


class DcaOrder(TimestampMixin, db.Model):
    __tablename__ = "dca_orders"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("dca_plans.id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    instrument_id = db.Column(db.Integer, db.ForeignKey("instruments.id"), nullable=False)
    order_date = db.Column(db.Date, nullable=False)
    expected_confirm_date = db.Column(db.Date, nullable=False)
    actual_confirm_date = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Float, nullable=False, comment="申购金额")
    fee = db.Column(db.Float, default=0.0, comment="手续费")
    confirm_nav = db.Column(db.Float, nullable=True)
    confirm_quantity = db.Column(db.Float, nullable=True)
    quote_date_used = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="pending", comment="pending/confirmed/cancelled")
    linked_trade_id = db.Column(db.Integer, db.ForeignKey("trades.id"), nullable=True)

    account = db.relationship("Account", backref=db.backref("dca_orders", lazy="dynamic"))
    linked_trade = db.relationship("Trade", backref=db.backref("dca_order", uselist=False))

    __table_args__ = (
        db.UniqueConstraint("plan_id", "order_date", name="uq_dca_plan_order_date"),
        db.UniqueConstraint("linked_trade_id", name="uq_dca_linked_trade"),
        db.Index("idx_dca_orders_pending", "status", "expected_confirm_date"),
    )

    def __repr__(self) -> str:
        return f"<DcaOrder plan={self.plan_id} order_date={self.order_date} status={self.status}>"
