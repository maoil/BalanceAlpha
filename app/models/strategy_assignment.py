"""
策略绑定模型 - 产品与策略模板的绑定关系
"""
import json

from app.extensions import db
from app.models.base_model import TimestampMixin


class StrategyAssignment(TimestampMixin, db.Model):
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

    # 唯一约束：同一产品在同一账户只有一个绑定
    __table_args__ = (
        db.UniqueConstraint("instrument_id", "account_id", name="uq_instrument_account"),
    )

    def get_effective_config(self) -> dict:
        """
        获取合并后的有效策略参数。

        模板基础参数 + 产品级覆盖参数，覆盖参数优先。
        消除 signal_service / rebalance_guidance / backtest_service 中重复的解析逻辑。
        """
        from app.models.strategy_template import StrategyTemplate
        template = db.session.get(StrategyTemplate, self.template_id)
        config = json.loads(template.config_json) if template and template.config_json else {}
        if self.custom_config_json:
            config.update(json.loads(self.custom_config_json))
        return config

    def __repr__(self) -> str:
        return f"<StrategyAssignment instrument={self.instrument_id} account={self.account_id}>"

