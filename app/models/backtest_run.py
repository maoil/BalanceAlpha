"""
回测记录模型

第一阶段语义：单产品 backtesting.py 原生回测
"""
from app.extensions import db
from app.models.base_model import CreatedAtMixin


class BacktestRun(CreatedAtMixin, db.Model):
    __tablename__ = "backtest_runs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    run_name = db.Column(db.String(200), nullable=False, comment="运行名称")

    instrument_id = db.Column(
        db.Integer,
        db.ForeignKey("instruments.id"),
        nullable=True,
        comment="产品 ID",
    )
    backtest_config_key = db.Column(
        db.String(100),
        default="",
        comment="回测配置键",
    )

    start_date = db.Column(db.Date, nullable=False, comment="开始日期")
    end_date = db.Column(db.Date, nullable=False, comment="结束日期")
    warmup_start_date = db.Column(db.Date, nullable=True, comment="预热开始日期")

    params_json = db.Column(db.Text, default="{}", comment="参数JSON")
    result_json = db.Column(db.Text, default="{}", comment="结果JSON")
    status = db.Column(db.String(20), default="running", comment="状态")

    template_id = db.Column(
        db.Integer,
        db.ForeignKey("strategy_templates.id"),
        nullable=True,
        comment="(旧) 策略模板 ID，仅用于兼容旧数据",
    )

    instrument = db.relationship("Instrument", backref="backtest_runs", lazy="select")

    def __repr__(self) -> str:
        return f"<BacktestRun {self.run_name} {self.status}>"
