from flask import request

from app.api import bp
from app.api.responses import success
from app.schemas.serializers import serialize_system_log
from app.services.log_service import LogService


@bp.get("/logs")
def list_logs():
    limit = request.args.get("limit", default=200, type=int)
    logs = LogService.get_logs(
        log_type=request.args.get("log_type") or None,
        level=request.args.get("level") or None,
        limit=limit,
    )
    return success([serialize_system_log(log) for log in logs])
