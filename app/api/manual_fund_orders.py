from app.api import bp
from app.api.responses import error, success
from app.schemas.serializers import serialize_manual_fund_order, serialize_trade
from app.services.manual_fund_order_service import ManualFundOrderService


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
