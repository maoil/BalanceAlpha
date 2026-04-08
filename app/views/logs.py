"""
日志路由
"""
from flask import Blueprint, render_template, request

from app.services.log_service import LogService

bp = Blueprint("logs", __name__)


@bp.route("/")
def list_logs():
    """日志列表"""
    log_type = request.args.get("log_type", "")
    level = request.args.get("level", "")

    logs = LogService.get_logs(
        log_type=log_type or None,
        level=level or None,
        limit=200,
    )

    return render_template(
        "logs/list.html",
        logs=logs,
        selected_log_type=log_type,
        selected_level=level,
    )
