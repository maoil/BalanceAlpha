from flask import request

from app.api import bp
from app.api.responses import error, success
from app.schemas.serializers import serialize_position
from app.services.account_service import AccountService
from app.services.instrument_service import InstrumentService
from app.services.position_service import PositionService


@bp.get("/positions")
def list_positions():
    positions = PositionService.get_all(account_id=request.args.get("account_id", type=int))
    return success([serialize_position(position) for position in positions])


@bp.post("/positions")
def create_position():
    data = request.get_json(silent=True) or {}
    try:
        account_id = int(data["account_id"])
        symbol = str(data["symbol"]).strip()
        quantity = float(data.get("quantity", 0))
        market_price = float(data.get("market_price", 0))
        unrealized_pnl = float(data.get("unrealized_pnl", 0))
    except KeyError as exc:
        return error("validation_error", f"Missing required field: {exc.args[0]}", 400)
    except (TypeError, ValueError):
        return error("validation_error", "Invalid position payload", 400)

    if not symbol:
        return error("validation_error", "symbol is required", 400)
    if quantity <= 0:
        return error("validation_error", "quantity must be greater than 0", 400)

    account = AccountService.get_by_id(account_id)
    if account is None:
        return error("not_found", "Account not found", 404)

    instrument = InstrumentService.get_by_symbol(symbol)
    if instrument is None:
        instrument_type = data.get("instrument_type", "etf")
        trade_mode = "exchange_traded" if instrument_type in ("etf", "lof") else "eod_nav"
        try:
            instrument = InstrumentService.create(
                {
                    "symbol": symbol,
                    "name": data.get("name") or symbol,
                    "instrument_type": instrument_type,
                    "trade_mode": data.get("trade_mode") or trade_mode,
                    "default_account_type": account.account_type,
                    "status": "active",
                }
            )
        except (TypeError, ValueError) as exc:
            return error("validation_error", str(exc), 400)

    market_value = quantity * market_price
    cost_value = market_value - unrealized_pnl
    avg_cost = cost_value / quantity if quantity > 0 else 0
    pnl_pct = unrealized_pnl / cost_value if cost_value > 0 else 0

    position = PositionService.create_manual(
        account_id=account_id,
        instrument_id=instrument.id,
        quantity=quantity,
        avg_cost=avg_cost,
        market_price=market_price,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=pnl_pct,
    )
    return success(serialize_position(position), status=201)


@bp.post("/positions/refresh-prices")
def refresh_market_prices():
    updated_count = PositionService.refresh_market_prices()
    positions = PositionService.get_all()
    return success(
        {
            "updated": updated_count,
            "positions": [serialize_position(position) for position in positions],
        }
    )


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

