"""
策略模板模型
"""
from datetime import datetime

from app.extensions import db


class StrategyTemplate(db.Model):
    __tablename__ = "strategy_templates"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    template_code = db.Column(db.String(100), unique=True, nullable=False, comment="模板编码")
    template_name = db.Column(db.String(200), nullable=False, comment="模板名称")
    account_type = db.Column(db.String(20), nullable=False, comment="适用账户类型: core/tactical")
    description = db.Column(db.Text, default="", comment="描述")
    config_json = db.Column(db.Text, default="{}", comment="默认参数JSON")
    version = db.Column(db.String(20), default="1.0", comment="版本号")
    status = db.Column(db.String(20), default="active", comment="状态: active/disabled")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    assignments = db.relationship("StrategyAssignment", backref="template", lazy="dynamic")
    backtest_runs = db.relationship("BacktestRun", backref="template", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<StrategyTemplate {self.template_code}>"
