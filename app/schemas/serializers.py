import json
from datetime import date, datetime
from typing import Any


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None


def _number(value: Any) -> Any:
    return value if value is not None else None


def _json(value: str | None, default: Any = None) -> Any:
    if default is None:
        default = {}
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def serialize_account(account) -> dict:
    return {
        "id": account.id,
        "account_code": account.account_code,
        "account_name": account.account_name,
        "account_type": account.account_type,
        "description": account.description,
        "status": account.status,
        "created_at": _iso(getattr(account, "created_at", None)),
        "updated_at": _iso(getattr(account, "updated_at", None)),
    }


def serialize_account_summary(account, summary: dict) -> dict:
    data = serialize_account(account)
    data["summary"] = {
        "market_value": summary["total_market_value"],
        "cost": summary["total_cost"],
        "unrealized_pnl": summary["total_unrealized_pnl"],
        "unrealized_pnl_pct": summary["total_unrealized_pnl_pct"],
        "position_count": summary["position_count"],
    }
    return data


def serialize_instrument(instrument) -> dict:
    return {
        "id": instrument.id,
        "symbol": instrument.symbol,
        "name": instrument.name,
        "instrument_type": instrument.instrument_type,
        "market": instrument.market,
        "trade_mode": instrument.trade_mode,
        "default_account_type": instrument.default_account_type,
        "default_strategy_template": instrument.default_strategy_template,
        "is_dca_eligible": bool(instrument.is_dca_eligible),
        "dca_confirm_cycle": instrument.dca_confirm_cycle,
        "status": instrument.status,
        "notes": instrument.notes,
        "created_at": _iso(getattr(instrument, "created_at", None)),
        "updated_at": _iso(getattr(instrument, "updated_at", None)),
    }


def serialize_position(position) -> dict:
    return {
        "id": position.id,
        "account_id": position.account_id,
        "instrument_id": position.instrument_id,
        "account": serialize_account(position.account) if position.account else None,
        "instrument": (
            serialize_instrument(position.instrument) if position.instrument else None
        ),
        "quantity": _number(position.quantity),
        "avg_cost": _number(position.avg_cost),
        "market_price": _number(position.market_price),
        "price_date": position.price_date,
        "market_value": _number(position.market_value),
        "unrealized_pnl": _number(position.unrealized_pnl),
        "unrealized_pnl_pct": _number(position.unrealized_pnl_pct),
        "today_pnl": _number(position.today_pnl),
        "weight_in_account": _number(position.weight_in_account),
        "position_status": position.position_status,
        "opened_at": _iso(position.opened_at),
        "updated_at": _iso(position.updated_at),
    }


def serialize_trade(trade) -> dict:
    return {
        "id": trade.id,
        "account_id": trade.account_id,
        "instrument_id": trade.instrument_id,
        "account": serialize_account(trade.account) if trade.account else None,
        "instrument": serialize_instrument(trade.instrument) if trade.instrument else None,
        "trade_date": _iso(trade.trade_date),
        "trade_type": trade.trade_type,
        "side": trade.side,
        "quantity": _number(trade.quantity),
        "price": _number(trade.price),
        "amount": _number(trade.amount),
        "fee": _number(trade.fee),
        "reason_code": trade.reason_code,
        "notes": trade.notes,
        "source_type": trade.source_type,
        "source_id": trade.source_id,
        "created_at": _iso(getattr(trade, "created_at", None)),
    }


def serialize_manual_fund_order(order) -> dict:
    return {
        "id": order.id,
        "account_id": order.account_id,
        "instrument_id": order.instrument_id,
        "account": serialize_account(order.account) if order.account else None,
        "instrument": (
            serialize_instrument(order.instrument) if order.instrument else None
        ),
        "order_date": _iso(order.order_date),
        "expected_confirm_date": _iso(order.expected_confirm_date),
        "actual_confirm_date": _iso(order.actual_confirm_date),
        "trade_type": order.trade_type,
        "side": order.side,
        "quantity": _number(order.quantity),
        "amount": _number(order.amount),
        "fee": _number(order.fee),
        "confirm_nav": _number(order.confirm_nav),
        "confirm_quantity": _number(order.confirm_quantity),
        "quote_date_used": _iso(order.quote_date_used),
        "status": order.status,
        "reason_code": order.reason_code,
        "notes": order.notes,
        "linked_trade_id": order.linked_trade_id,
        "created_at": _iso(getattr(order, "created_at", None)),
        "updated_at": _iso(getattr(order, "updated_at", None)),
    }


def serialize_signal(signal) -> dict:
    return {
        "id": signal.id,
        "batch_id": signal.batch_id,
        "batch_version": signal.batch_version,
        "signal_date": _iso(signal.signal_date),
        "account_id": signal.account_id,
        "instrument_id": signal.instrument_id,
        "account": serialize_account(signal.account) if signal.account else None,
        "instrument": (
            serialize_instrument(signal.instrument) if signal.instrument else None
        ),
        "signal_type": signal.signal_type,
        "priority": signal.priority,
        "reason_code": signal.reason_code,
        "explanation": signal.explanation,
        "score": _number(signal.score),
        "risk_flag": signal.risk_flag,
        "status": signal.status,
        "created_at": _iso(getattr(signal, "created_at", None)),
    }


def serialize_strategy_template(template) -> dict:
    return {
        "id": template.id,
        "template_code": template.template_code,
        "template_name": template.template_name,
        "account_type": template.account_type,
        "description": template.description,
        "config": _json(template.config_json, {}),
        "version": template.version,
        "status": template.status,
        "created_at": _iso(template.created_at),
        "updated_at": _iso(template.updated_at),
    }


def serialize_signal_ai_analysis(analysis) -> dict | None:
    if analysis is None:
        return None

    return {
        "id": analysis.id,
        "signal_id": analysis.signal_id,
        "analysis_type": analysis.analysis_type,
        "provider": analysis.provider,
        "model_name": analysis.model_name,
        "prompt_version": analysis.prompt_version,
        "summary": analysis.summary,
        "confidence": _number(analysis.confidence),
        "status": analysis.status,
        "error_message": analysis.error_message,
        "input_snapshot": _json(analysis.input_snapshot_json, {}),
        "output": _json(analysis.output_json, {}),
        "created_at": _iso(getattr(analysis, "created_at", None)),
        "updated_at": _iso(getattr(analysis, "updated_at", None)),
    }


def serialize_backtest_run(run) -> dict:
    result = _json(run.result_json, {})
    return {
        "id": run.id,
        "run_name": run.run_name,
        "template_id": run.template_id,
        "template": serialize_strategy_template(run.template) if run.template else None,
        "start_date": _iso(run.start_date),
        "end_date": _iso(run.end_date),
        "params": _json(run.params_json, {}),
        "result": result,
        "summary": result.get("summary", {}) if isinstance(result, dict) else {},
        "status": run.status,
        "created_at": _iso(getattr(run, "created_at", None)),
    }


def serialize_system_log(log) -> dict:
    return {
        "id": log.id,
        "log_type": log.log_type,
        "level": log.level,
        "module": log.module,
        "message": log.message,
        "context": _json(log.context_json, {}),
        "created_at": _iso(getattr(log, "created_at", None)),
    }
