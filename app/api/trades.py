from datetime import date

from flask import request

from app.api import bp
from app.api.responses import error, success
from app.schemas.serializers import serialize_trade
from app.services.trade_service import TradeService


def _parse_date(value: str | None, field_name: str):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


@bp.get("/trades")
def list_trades():
    try:
        trades = TradeService.get_all(
            account_id=request.args.get("account_id", type=int),
            instrument_id=request.args.get("instrument_id", type=int),
            start_date=_parse_date(request.args.get("start_date"), "start_date"),
            end_date=_parse_date(request.args.get("end_date"), "end_date"),
            limit=request.args.get("limit", default=100, type=int),
        )
    except ValueError as exc:
        return error("validation_error", str(exc), 400)

    return success([serialize_trade(trade) for trade in trades])


@bp.post("/trades")
def create_trade():
    data = request.get_json(silent=True) or {}
    if isinstance(data.get("trade_date"), str):
        try:
            data["trade_date"] = date.fromisoformat(data["trade_date"])
        except ValueError:
            return error("validation_error", "trade_date must be an ISO date", 400)

    try:
        trade = TradeService.create(data)
    except KeyError as exc:
        return error("validation_error", f"Missing required field: {exc.args[0]}", 400)
    except (TypeError, ValueError) as exc:
        return error("validation_error", str(exc), 400)

    return success(serialize_trade(trade), status=201)

