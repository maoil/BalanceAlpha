"""
回测记录模型
"""
from app.extensions import db
from app.models.base_model import CreatedAtMixin


class BacktestRun(CreatedAtMixin, db.Model):
    __tablename__ = "backtest_runs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    run_name = db.Column(db.String(200), nullable=False, comment="运行名称")
    template_id = db.Column(db.Integer, db.ForeignKey("strategy_templates.id"))
    start_date = db.Column(db.Date, nullable=False, comment="开始日期")
    end_date = db.Column(db.Date, nullable=False, comment="结束日期")
    params_json = db.Column(db.Text, default="{}", comment="参数JSON")
    result_json = db.Column(db.Text, default="{}", comment="结果JSON")
    status = db.Column(db.String(20), default="running", comment="状态")

    def __repr__(self) -> str:
        return f"<BacktestRun {self.run_name} {self.status}>"
