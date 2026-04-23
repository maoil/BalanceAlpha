"""
Monthly DCA plan configuration.
"""
from app.extensions import db
from app.models.base_model import TimestampMixin


class DcaPlan(TimestampMixin, db.Model):
    __tablename__ = "dca_plans"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    instrument_id = db.Column(db.Integer, db.ForeignKey("instruments.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False, comment="每期定投金额")
    schedule_type = db.Column(db.String(20), default="monthly", comment="计划类型")
    schedule_day = db.Column(db.Integer, nullable=False, comment="每月执行日")
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="active", comment="active/paused/closed")
    last_order_date = db.Column(db.Date, nullable=True)
    next_order_date = db.Column(db.Date, nullable=False)

    account = db.relationship("Account", backref=db.backref("dca_plans", lazy="dynamic"))
    orders = db.relationship(
        "DcaOrder",
        backref="plan",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.Index("idx_dca_plans_next_order", "status", "next_order_date"),
    )

    def __repr__(self) -> str:
        return f"<DcaPlan account={self.account_id} instrument={self.instrument_id} amount={self.amount}>"
