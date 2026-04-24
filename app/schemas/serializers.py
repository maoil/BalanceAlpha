import json
from datetime import date, datetime
from typing import Any


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None


def _number(value: Any) -> Any:
    return value if value is not None else None


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
    try:
        config = json.loads(template.config_json or "{}")
    except json.JSONDecodeError:
        config = {}

    return {
        "id": template.id,
        "template_code": template.template_code,
        "template_name": template.template_name,
        "account_type": template.account_type,
        "description": template.description,
        "config": config,
        "version": template.version,
        "status": template.status,
        "created_at": _iso(template.created_at),
        "updated_at": _iso(template.updated_at),
    }

