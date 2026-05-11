"""
Instrument management service.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.extensions import db
from app.models.account import Account
from app.models.dca_plan import DcaPlan
from app.models.instrument import Instrument
from app.models.strategy_assignment import StrategyAssignment
from app.models.strategy_template import (
    StrategyTemplate,
    get_default_assignment_range,
    infer_core_template_code,
)
from app.services.trading_calendar_service import TradingCalendarService
from app.utils.constants import InstrumentStatus


class InstrumentService:
    """Instrument business logic."""

    @staticmethod
    def _normalize_confirm_cycle(value: object) -> int:
        if value in (None, ""):
            return 1
        cycle = int(value)
        if cycle not in {0, 1, 2}:
            raise ValueError("dca_confirm_cycle must be 0, 1, or 2")
        return cycle

    @staticmethod
    def get_all(status: Optional[str] = None, account_type: Optional[str] = None) -> list[Instrument]:
        query = Instrument.query
        if status:
            query = query.filter(Instrument.status == status)
        if account_type:
            query = query.filter(Instrument.default_account_type == account_type)
        return query.order_by(Instrument.symbol).all()

    @staticmethod
    def get_by_id(instrument_id: int) -> Optional[Instrument]:
        return db.session.get(Instrument, instrument_id)

    @staticmethod
    def get_by_symbol(symbol: str) -> Optional[Instrument]:
        return Instrument.query.filter_by(symbol=symbol).first()

    @staticmethod
    def create(data: dict) -> Instrument:
        instrument = Instrument(
            symbol=data["symbol"].strip(),
            name=data["name"].strip(),
            instrument_type=data["instrument_type"],
            market=data.get("market", ""),
            trade_mode=data.get("trade_mode", "eod_nav"),
            default_account_type=data.get("default_account_type", "core"),
            default_strategy_template=data.get("default_strategy_template", ""),
            is_dca_eligible=data.get("is_dca_eligible", False),
            dca_confirm_cycle=InstrumentService._normalize_confirm_cycle(
                data.get("dca_confirm_cycle", 1)
            ),
            status=data.get("status", InstrumentStatus.ACTIVE.value),
            notes=data.get("notes", ""),
            backtest_config_key=data.get("backtest_config_key", ""),
            tracking_index=data.get("tracking_index", ""),
        )
        db.session.add(instrument)
        db.session.commit()

        InstrumentService._auto_create_assignment(instrument, data)
        InstrumentService._sync_dca_plan(instrument, data)
        return instrument

    @staticmethod
    def update(instrument_id: int, data: dict) -> Optional[Instrument]:
        instrument = db.session.get(Instrument, instrument_id)
        if not instrument:
            return None

        original_account_type = instrument.default_account_type

        for field in [
            "name",
            "instrument_type",
            "market",
            "trade_mode",
            "default_account_type",
            "default_strategy_template",
            "is_dca_eligible",
            "dca_confirm_cycle",
            "status",
            "notes",
            "backtest_config_key",
            "tracking_index",
        ]:
            if field in data:
                if field == "dca_confirm_cycle":
                    setattr(
                        instrument,
                        field,
                        InstrumentService._normalize_confirm_cycle(data[field]),
                    )
                else:
                    setattr(instrument, field, data[field])

        if (
            "default_account_type" in data
            and instrument.default_account_type != original_account_type
        ):
            from app.services.position_service import PositionService

            PositionService.sync_instrument_account(
                instrument_id=instrument.id,
                account_type=instrument.default_account_type,
                commit=False,
            )

        db.session.commit()

        InstrumentService._auto_create_assignment(instrument, data)
        InstrumentService._sync_dca_plan(instrument, data)
        return instrument

    @staticmethod
    def _auto_create_assignment(instrument: Instrument, data: dict) -> None:
        template_code = data.get("default_strategy_template", "")
        account_type = data.get("default_account_type", instrument.default_account_type)

        if not template_code:
            template_code = InstrumentService._infer_template_code(
                data.get("instrument_type", instrument.instrument_type),
                account_type,
                data.get("name", instrument.name),
            )
            if template_code:
                instrument.default_strategy_template = template_code

        template = StrategyTemplate.query.filter_by(template_code=template_code).first()
        account = Account.query.filter_by(account_type=account_type).first()
        if not template or not account:
            db.session.commit()
            return

        existing = StrategyAssignment.query.filter_by(
            instrument_id=instrument.id,
            account_id=account.id,
        ).first()
        if existing:
            existing.allow_dca = bool(data.get("is_dca_eligible", instrument.is_dca_eligible))
            db.session.commit()
            return

        default_lower, default_upper = get_default_assignment_range(
            template.template_code,
            symbol=instrument.symbol,
            name=instrument.name,
        )

        assignment = StrategyAssignment(
            instrument_id=instrument.id,
            account_id=account.id,
            template_id=template.id,
            target_weight_lower=data.get("target_weight_lower", default_lower),
            target_weight_upper=data.get("target_weight_upper", default_upper),
            allow_dca=bool(data.get("is_dca_eligible", instrument.is_dca_eligible)),
            allow_rebalance=True,
        )
        db.session.add(assignment)
        db.session.commit()

    @staticmethod
    def _infer_template_code(instrument_type: str, account_type: str, name: str) -> str:
        if account_type == "tactical":
            return "tactical_theme_template"
        return infer_core_template_code(instrument_type, name)

    @staticmethod
    def _calculate_initial_next_order_date(schedule_day: int, start_date: date) -> date:
        current_anchor = TradingCalendarService.get_month_anchor(
            start_date.year,
            start_date.month,
            schedule_day,
        )
        current_run_date = TradingCalendarService.get_next_trading_day(current_anchor)
        if current_run_date >= start_date:
            return current_run_date
        return TradingCalendarService.get_next_monthly_run_date(schedule_day, start_date)

    @staticmethod
    def _sync_dca_plan(instrument: Instrument, data: dict) -> None:
        plans = DcaPlan.query.filter_by(instrument_id=instrument.id).all()
        account = Account.query.filter_by(account_type=instrument.default_account_type).first()

        amount_value = data.get("dca_amount")
        schedule_day_value = data.get("dca_schedule_day")
        plan_status = data.get("dca_plan_status", "active")

        amount = float(amount_value) if amount_value not in (None, "", 0, "0") else 0.0
        schedule_day = int(schedule_day_value) if schedule_day_value not in (None, "") else 0
        dca_enabled = (
            instrument.instrument_type == "fund"
            and bool(instrument.is_dca_eligible)
            and amount > 0
            and 1 <= schedule_day <= 31
            and account is not None
        )

        for plan in plans:
            if not account or plan.account_id != account.id:
                plan.status = "paused"

        if not dca_enabled:
            for plan in plans:
                plan.status = "paused"
            db.session.commit()
            return

        plan = DcaPlan.query.filter_by(
            instrument_id=instrument.id,
            account_id=account.id,
        ).first()

        start_date = data.get("dca_start_date") or date.today()
        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)

        next_order_date = InstrumentService._calculate_initial_next_order_date(
            schedule_day=schedule_day,
            start_date=start_date,
        )

        if plan:
            plan.amount = amount
            plan.schedule_type = "monthly"
            plan.schedule_day = schedule_day
            plan.start_date = start_date
            plan.status = plan_status
            if plan.last_order_date is None or plan.next_order_date < start_date:
                plan.next_order_date = next_order_date
        else:
            plan = DcaPlan(
                account_id=account.id,
                instrument_id=instrument.id,
                amount=amount,
                schedule_type="monthly",
                schedule_day=schedule_day,
                start_date=start_date,
                status=plan_status,
                next_order_date=next_order_date,
            )
            db.session.add(plan)

        db.session.commit()

    @staticmethod
    def update_status(instrument_id: int, new_status: str) -> Optional[Instrument]:
        instrument = db.session.get(Instrument, instrument_id)
        if not instrument:
            return None

        instrument.status = new_status
        db.session.commit()
        return instrument

    @staticmethod
    def get_active_instruments() -> list[Instrument]:
        return Instrument.query.filter(
            Instrument.status.in_([InstrumentStatus.ACTIVE.value, InstrumentStatus.WATCHLIST.value])
        ).all()
