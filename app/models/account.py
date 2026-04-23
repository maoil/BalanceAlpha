"""
账户模型 - 逻辑账户（核心配置 / 战术轮动）
"""
from app.extensions import db
from app.models.base_model import TimestampMixin


class Account(TimestampMixin, db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_code = db.Column(db.String(50), unique=True, nullable=False, comment="账户编码")
    account_name = db.Column(db.String(100), nullable=False, comment="账户名称")
    account_type = db.Column(db.String(20), nullable=False, comment="账户类型: core/tactical")
    description = db.Column(db.Text, default="", comment="描述")
    status = db.Column(db.String(20), default="active", comment="状态: active/disabled")

    # 关系
    positions = db.relationship("Position", backref="account", lazy="dynamic")
    trades = db.relationship("Trade", backref="account", lazy="dynamic")
    signals = db.relationship("Signal", backref="account", lazy="dynamic")
    strategy_assignments = db.relationship("StrategyAssignment", backref="account", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Account {self.account_code}: {self.account_name}>"
