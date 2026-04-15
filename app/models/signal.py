"""
策略信号模型
"""
from datetime import datetime

from app.extensions import db


class Signal(db.Model):
    __tablename__ = "signals"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_id = db.Column(db.String(36), default="", comment="生成批次ID")
    batch_version = db.Column(db.Integer, default=1, nullable=False, comment="生成版本号")
    signal_date = db.Column(db.Date, nullable=False, comment="信号日期")
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    instrument_id = db.Column(db.Integer, db.ForeignKey("instruments.id"), nullable=False)
    signal_type = db.Column(db.String(30), nullable=False, comment="信号类型")
    priority = db.Column(db.Integer, default=5, comment="优先级: 1=最高")
    reason_code = db.Column(db.String(200), default="", comment="原因码")
    explanation = db.Column(db.Text, default="", comment="信号解释")
    score = db.Column(db.Float, comment="评分(核心账户)")
    risk_flag = db.Column(db.String(50), default="", comment="风险标记")
    status = db.Column(db.String(20), default="pending", comment="状态")
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 索引
    __table_args__ = (
        db.Index("idx_signals_date_account", "signal_date", "account_id"),
        db.Index("idx_signals_batch_version", "batch_version"),
    )

    def __repr__(self) -> str:
        return f"<Signal {self.signal_date} {self.signal_type} instrument={self.instrument_id}>"
