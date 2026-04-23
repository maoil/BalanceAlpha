"""
策略建议 AI 分析结果模型
"""
from app.extensions import db
from app.models.base_model import TimestampMixin


class SignalAIAnalysis(TimestampMixin, db.Model):
    __tablename__ = "signal_ai_analysis"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    signal_id = db.Column(
        db.Integer,
        db.ForeignKey("signals.id"),
        nullable=False,
        index=True,
    )
    analysis_type = db.Column(
        db.String(50),
        default="signal_explanation",
        nullable=False,
        comment="分析类型",
    )
    provider = db.Column(
        db.String(50),
        default="langchain_openai",
        nullable=False,
        comment="模型提供方",
    )
    model_name = db.Column(
        db.String(100),
        default="",
        nullable=False,
        comment="模型名称",
    )
    prompt_version = db.Column(
        db.String(50),
        default="v1",
        nullable=False,
        comment="提示词版本",
    )
    input_snapshot_json = db.Column(
        db.Text,
        default="{}",
        nullable=False,
        comment="输入快照 JSON",
    )
    output_json = db.Column(
        db.Text,
        default="{}",
        nullable=False,
        comment="输出结果 JSON",
    )
    summary = db.Column(
        db.Text,
        default="",
        nullable=False,
        comment="AI 总结",
    )
    confidence = db.Column(
        db.Float,
        default=0.0,
        nullable=False,
        comment="置信度",
    )
    status = db.Column(
        db.String(20),
        default="success",
        nullable=False,
        comment="状态 success/error/pending",
    )
    error_message = db.Column(
        db.Text,
        default="",
        nullable=False,
        comment="错误信息",
    )

    signal = db.relationship(
        "Signal",
        backref=db.backref("ai_analyses", lazy="dynamic"),
    )

    __table_args__ = (
        db.Index(
            "idx_signal_ai_analysis_signal_created",
            "signal_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SignalAIAnalysis signal_id={self.signal_id} "
            f"model={self.model_name} status={self.status}>"
        )
