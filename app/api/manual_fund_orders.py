from flask import request

from app.api import bp
from app.api.responses import error, success
from app.models.manual_fund_order import ManualFundOrder
from app.schemas.serializers import serialize_manual_fund_order, serialize_trade
from app.services.manual_fund_order_service import ManualFundOrderService


@bp.get("/manual-fund-orders")
def list_manual_fund_orders():
    query = ManualFundOrder.query
    account_id = request.args.get("account_id", type=int)
    instrument_id = request.args.get("instrument_id", type=int)
    status = request.args.get("status")
    limit = request.args.get("limit", default=100, type=int)

    if account_id:
        query = query.filter_by(account_id=account_id)
    if instrument_id:
        query = query.filter_by(instrument_id=instrument_id)
    if status:
        query = query.filter_by(status=status)

    orders = query.order_by(
        ManualFundOrder.order_date.desc(),
        ManualFundOrder.id.desc(),
    ).limit(limit).all()
    return success([serialize_manual_fund_order(order) for order in orders])


@bp.get("/manual-fund-orders/<int:order_id>")
def get_manual_fund_order(order_id: int):
    order = ManualFundOrderService.get_by_id(order_id)
    if order is None:
        return error("not_found", "Manual fund order not found", 404)
    return success(serialize_manual_fund_order(order))


@bp.post("/manual-fund-orders/<int:order_id>/confirm")
def confirm_manual_fund_order(order_id: int):
    try:
        result = ManualFundOrderService.confirm_order(order_id)
    except LookupError as exc:
        return error("not_found", str(exc), 404)
    except ValueError as exc:
        return error("validation_error", str(exc), 400)

    return success(
        {
            "order": serialize_manual_fund_order(result["order"]),
            "trade": serialize_trade(result["trade"]),
        }
    )
