"""
系统日志模型
"""
from datetime import datetime

from app.extensions import db


class SystemLog(db.Model):
    __tablename__ = "system_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    log_type = db.Column(db.String(30), nullable=False, comment="日志类型")
    level = db.Column(db.String(20), default="info", comment="日志级别")
    module = db.Column(db.String(100), default="", comment="来源模块")
    message = db.Column(db.Text, nullable=False, comment="日志内容")
    context_json = db.Column(db.Text, default="{}", comment="上下文JSON")
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<SystemLog [{self.level}] {self.log_type}: {self.message[:50]}>"
