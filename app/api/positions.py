from flask import request

from app.api import bp
from app.api.responses import error, success
from app.schemas.serializers import serialize_position
from app.services.position_service import PositionService


@bp.get("/positions")
def list_positions():
    positions = PositionService.get_all(account_id=request.args.get("account_id", type=int))
    return success([serialize_position(position) for position in positions])


@bp.get("/positions/<int:position_id>")
def get_position(position_id: int):
    position = PositionService.get_by_id(position_id)
    if position is None:
        return error("not_found", "Position not found", 404)
    return success(serialize_position(position))


@bp.patch("/positions/<int:position_id>")
def update_position(position_id: int):
    data = request.get_json(silent=True) or {}
    allowed_fields = {"quantity", "avg_cost", "market_price"}
    update_data = {key: data[key] for key in allowed_fields if key in data}

    try:
        position = PositionService.manual_update(position_id, update_data)
    except (TypeError, ValueError) as exc:
        return error("validation_error", str(exc), 400)

    if position is None:
        return error("not_found", "Position not found", 404)
    return success(serialize_position(position))


@bp.post("/positions/refresh")
def refresh_positions():
    from app.services.fund_data_fetcher import FundDataFetcher

    try:
        summary = FundDataFetcher.fetch_all_prices()
    except Exception as exc:
        return error("refresh_failed", str(exc), 500)

    positions = PositionService.get_all()
    return success(
        {
            "summary": summary,
            "positions": [serialize_position(position) for position in positions],
        }
    )

