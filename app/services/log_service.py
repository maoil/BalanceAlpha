"""
系统日志服务
"""
import json
from typing import Optional
from datetime import datetime

from app.extensions import db
from app.models.system_log import SystemLog


class LogService:
    """系统日志业务逻辑"""

    @staticmethod
    def log(
        log_type: str,
        level: str,
        module: str,
        message: str,
        context: Optional[dict] = None,
    ) -> SystemLog:
        """
        写入系统日志

        Args:
            log_type: 日志类型 (signal/param_change/manual/error/data_import)
            level: 日志级别 (info/warning/error)
            module: 来源模块
            message: 日志内容
            context: 上下文信息字典
        """
        log_entry = SystemLog(
            log_type=log_type,
            level=level,
            module=module,
            message=message,
            context_json=json.dumps(context or {}, ensure_ascii=False),
        )
        db.session.add(log_entry)
        db.session.commit()
        return log_entry

    @staticmethod
    def get_logs(
        log_type: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> list[SystemLog]:
        """
        获取日志列表

        Args:
            log_type: 按类型筛选
            level: 按级别筛选
            limit: 返回数量限制
        """
        query = SystemLog.query
        if log_type:
            query = query.filter_by(log_type=log_type)
        if level:
            query = query.filter_by(level=level)
        return query.order_by(SystemLog.created_at.desc()).limit(limit).all()
