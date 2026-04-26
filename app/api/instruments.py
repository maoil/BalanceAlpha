from flask import request

from app.api import bp
from app.api.responses import error, success
from app.schemas.serializers import serialize_instrument
from app.services.instrument_service import InstrumentService


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

