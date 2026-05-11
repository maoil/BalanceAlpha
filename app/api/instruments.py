from flask import request

from app.api import bp
from app.api.responses import error, success
from app.backtesting.registry import list_configs
from app.schemas.serializers import serialize_instrument
from app.services.fund_data_fetcher import DEFAULT_HISTORY_DAYS, FundDataFetcher
from app.services.instrument_service import InstrumentService


@bp.get("/backtest-configs")
def get_backtest_configs():
    """Get all available backtest configurations for binding to instruments."""
    configs = list_configs()
    return success(
        [
            {"key": key, "name": config["name"], "strategy": config["strategy_class"]}
            for key, config in configs.items()
        ]
    )


@bp.get("/instruments/search-fund")
def search_fund():
    keyword = request.args.get("keyword", "").strip()
    if not keyword or len(keyword) < 2:
        return success([])
    return success(FundDataFetcher.search_fund(keyword))


@bp.get("/instruments/fund-info/<fund_code>")
def get_fund_info(fund_code: str):
    info = FundDataFetcher.get_fund_info(fund_code)
    if info is None:
        return error("not_found", "Fund info not found", 404)
    return success(info)


@bp.get("/instruments")
def list_instruments():
    instruments = InstrumentService.get_all(
        status=request.args.get("status"),
        account_type=request.args.get("account_type"),
    )
    return success([serialize_instrument(instrument) for instrument in instruments])


@bp.post("/instruments")
def create_instrument():
    data = request.get_json(silent=True) or {}
    try:
        instrument = InstrumentService.create(data)
    except KeyError as exc:
        return error("validation_error", f"Missing required field: {exc.args[0]}", 400)
    except (TypeError, ValueError) as exc:
        return error("validation_error", str(exc), 400)
    return success(serialize_instrument(instrument), status=201)


@bp.get("/instruments/<int:instrument_id>")
def get_instrument(instrument_id: int):
    instrument = InstrumentService.get_by_id(instrument_id)
    if instrument is None:
        return error("not_found", "Instrument not found", 404)
    return success(serialize_instrument(instrument))


@bp.patch("/instruments/<int:instrument_id>")
def update_instrument(instrument_id: int):
    data = request.get_json(silent=True) or {}
    try:
        instrument = InstrumentService.update(instrument_id, data)
    except (TypeError, ValueError) as exc:
        return error("validation_error", str(exc), 400)
    if instrument is None:
        return error("not_found", "Instrument not found", 404)
    return success(serialize_instrument(instrument))


@bp.patch("/instruments/<int:instrument_id>/status")
def update_instrument_status(instrument_id: int):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not new_status:
        return error("validation_error", "status is required", 400)

    instrument = InstrumentService.update_status(instrument_id, new_status)
    if instrument is None:
        return error("not_found", "Instrument not found", 404)
    return success(serialize_instrument(instrument))


@bp.post("/instruments/<int:instrument_id>/fetch-price")
def fetch_price(instrument_id: int):
    if InstrumentService.get_by_id(instrument_id) is None:
        return error("not_found", "Instrument not found", 404)

    result = FundDataFetcher.fetch_and_update_price(instrument_id)
    if not result:
        return error("fetch_failed", "Failed to fetch price", 502)
    return success(result)


@bp.post("/instruments/<int:instrument_id>/fetch-history")
def fetch_history(instrument_id: int):
    if InstrumentService.get_by_id(instrument_id) is None:
        return error("not_found", "Instrument not found", 404)

    data = request.get_json(silent=True) or {}
    days = data.get("days", request.args.get("days", DEFAULT_HISTORY_DAYS))
    try:
        days = int(days)
    except (TypeError, ValueError):
        return error("validation_error", "days must be an integer", 400)
    if days <= 0:
        return error("validation_error", "days must be greater than 0", 400)

    result = FundDataFetcher.fetch_and_import_history(instrument_id, days=days)
    if isinstance(result, dict) and result.get("error"):
        return error("fetch_failed", result["error"], 502)
    return success(result)


@bp.post("/instruments/fetch-all-prices")
def fetch_all_prices():
    return success(FundDataFetcher.fetch_all_prices())

