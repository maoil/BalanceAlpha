from datetime import date

from flask import request

from app.api import bp
from app.api.responses import error, success
from app.schemas.serializers import serialize_backtest_run
from app.services.backtest_service import BacktestService


def _parse_date(value: str | None, field_name: str) -> date:
    if not value:
        raise ValueError(f"{field_name} is required")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


@bp.get("/backtests")
def list_backtests():
    limit = request.args.get("limit", default=100, type=int)
    runs = BacktestService.list_runs(limit=limit)
    return success([serialize_backtest_run(run) for run in runs])


@bp.post("/backtests")
def create_backtest():
    data = request.get_json(silent=True) or {}
    try:
        run_name = (data.get("run_name") or "").strip()
        account_id = int(data["account_id"])
        start_date = _parse_date(data.get("start_date"), "start_date")
        end_date = _parse_date(data.get("end_date"), "end_date")
        initial_capital = float(data.get("initial_capital", 100000.0))
        fee_rate = float(data.get("fee_rate", 0.001))
        instrument_id = data.get("instrument_id")
        template_id = data.get("template_id")
        instrument_id = int(instrument_id) if instrument_id else None
        template_id = int(template_id) if template_id else None
    except KeyError as exc:
        return error("validation_error", f"Missing required field: {exc.args[0]}", 400)
    except (TypeError, ValueError) as exc:
        return error("validation_error", str(exc), 400)

    if not run_name:
        run_name = f"backtest_{account_id}_{start_date}_{end_date}"

    try:
        run = BacktestService.run_backtest(
            run_name=run_name,
            account_id=account_id,
            instrument_id=instrument_id,
            template_id=template_id,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
        )
    except ValueError as exc:
        return error("validation_error", str(exc), 400)

    return success(serialize_backtest_run(run), status=201)


@bp.get("/backtests/<int:run_id>")
def get_backtest(run_id: int):
    run = BacktestService.get_run(run_id)
    if run is None:
        return error("not_found", "Backtest run not found", 404)
    return success(serialize_backtest_run(run))
