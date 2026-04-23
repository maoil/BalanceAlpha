"""
模型基础 Mixin

提供统一的时间戳字段，使用 UTC 时区。
"""
from datetime import datetime, timezone

from app.extensions import db


def utcnow() -> datetime:
    """返回当前 UTC 时间（timezone-aware）"""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """
    统一时间戳 Mixin

    所有需要 created_at / updated_at 的模型继承此 Mixin。
    时间统一使用 UTC，避免跨时区部署时的不一致问题。
    """
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class CreatedAtMixin:
    """仅有 created_at 的 Mixin（适用于不需要 updated_at 的模型）"""
    created_at = db.Column(db.DateTime, default=utcnow)
