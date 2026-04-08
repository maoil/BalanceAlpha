"""
策略绑定模型 - 产品与策略模板的绑定关系
"""
from datetime import datetime

from app.extensions import db


class StrategyAssignment(db.Model):
    __tablename__ = "strategy_assignments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    instrument_id = db.Column(db.Integer, db.ForeignKey("instruments.id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey("strategy_templates.id"), nullable=False)
    target_weight_lower = db.Column(db.Float, default=0.0, comment="目标权重下限")
    target_weight_upper = db.Column(db.Float, default=0.0, comment="目标权重上限")
    allow_dca = db.Column(db.Boolean, default=False, comment="是否允许定投")
    allow_rebalance = db.Column(db.Boolean, default=True, comment="是否参与再平衡")
    custom_config_json = db.Column(db.Text, default="{}", comment="产品级覆盖参数")
    status = db.Column(db.String(20), default="active", comment="状态")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 唯一约束：同一产品在同一账户只有一个绑定
    __table_args__ = (
        db.UniqueConstraint("instrument_id", "account_id", name="uq_instrument_account"),
    )

    def __repr__(self) -> str:
        return f"<StrategyAssignment instrument={self.instrument_id} account={self.account_id}>"
