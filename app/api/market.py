from flask import request

from app.api import bp
from app.api.responses import error, success
from app.services.market_sentiment_service import MarketSentimentService


@bp.get("/market/vix/history")
def vix_history():
    days = request.args.get("days", default=30, type=int)
    interval = request.args.get("interval", "daily")
    if days <= 0:
        return error("validation_error", "days must be greater than 0", 400)
    if interval not in {"daily", "intraday"}:
        return error("validation_error", "interval must be daily or intraday", 400)
    return success(MarketSentimentService.get_vix_history(days=days, interval=interval))
