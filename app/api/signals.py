from datetime import date

from flask import request

from app.api import bp
from app.api.responses import error, success
from app.extensions import db
from app.models.market_data import MarketData
from app.models.position import Position
from app.models.signal import Signal
from app.models.strategy_assignment import StrategyAssignment
from app.schemas.serializers import serialize_signal
from app.services.signal_service import SignalService
from app.utils.constants import PositionStatus


@bp.get("/signals")
def list_signals():
    account_id = request.args.get("account_id", type=int)
    status = request.args.get("status")
    include_history = request.args.get("history") == "true"
    limit = request.args.get("limit", default=100, type=int)

    if include_history:
        signals = SignalService.get_history(limit=limit)
    else:
        signals = SignalService.get_latest_signals(account_id=account_id, status=status)

    return success([serialize_signal(signal) for signal in signals])


@bp.post("/signals/generate")
def generate_signals():
    data = request.get_json(silent=True) or {}
    signal_date = data.get("signal_date")
    try:
        parsed_date = date.fromisoformat(signal_date) if signal_date else None
    except ValueError:
        return error("validation_error", "signal_date must be an ISO date", 400)

    signals = SignalService.generate_signals(signal_date=parsed_date)
    return success([serialize_signal(signal) for signal in signals], status=201)


@bp.get("/signals/<int:signal_id>")
def get_signal(signal_id: int):
    signal = db.session.get(Signal, signal_id)
    if signal is None:
        return error("not_found", "Signal not found", 404)
    return success(serialize_signal(signal))


def _load_rebalance_context(signal: Signal):
    position = Position.query.filter_by(
        account_id=signal.account_id,
        instrument_id=signal.instrument_id,
        position_status=PositionStatus.OPEN.value,
    ).first()

    latest_md = MarketData.query.filter_by(
        instrument_id=signal.instrument_id,
    ).order_by(MarketData.trade_date.desc()).first()

    assignment = StrategyAssignment.query.filter_by(
        account_id=signal.account_id,
        instrument_id=signal.instrument_id,
        status="active",
    ).first()

    return position, latest_md, assignment


@bp.get("/signals/<int:signal_id>/rebalance-guidance")
def get_rebalance_guidance(signal_id: int):
    signal = db.session.get(Signal, signal_id)
    if signal is None:
        return error("not_found", "Signal not found", 404)

    position, latest_md, assignment = _load_rebalance_context(signal)
    guidance = SignalService.get_rebalance_guidance(
        signal=signal,
        position=position,
        latest_md=latest_md,
        assignment=assignment,
    )
    return success(guidance)
