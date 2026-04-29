from flask import request

from app.api import bp
from app.api.responses import error, success
from app.services.strategy_performance_service import StrategyPerformanceService


@bp.get("/strategies/performance")
def strategies_performance():
    days = request.args.get("days", default=7, type=int)
    if days <= 0:
        return error("validation_error", "days must be greater than 0", 400)
    return success(StrategyPerformanceService.get_performance(days=days))
