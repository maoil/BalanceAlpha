"""
DCA plan scheduling service.
"""
from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models.dca_order import DcaOrder
from app.models.dca_plan import DcaPlan
from app.services.trading_calendar_service import TradingCalendarService


class DcaPlanService:
    """Generate pending DCA orders from active plans."""

    @staticmethod
    def calculate_next_order_date(plan: DcaPlan, from_date: date | None = None) -> date:
        base_date = from_date or plan.next_order_date
        return TradingCalendarService.get_next_monthly_run_date(
            schedule_day=plan.schedule_day,
            from_date=base_date,
        )

    @staticmethod
    def generate_due_orders(run_date: date | None = None) -> dict[str, int]:
        run_date = run_date or date.today()
        plans = DcaPlan.query.filter(
            DcaPlan.status == "active",
            DcaPlan.next_order_date <= run_date,
        ).order_by(DcaPlan.next_order_date.asc(), DcaPlan.id.asc()).all()

        created = 0
        skipped = 0

        for plan in plans:
            existing = DcaOrder.query.filter_by(
                plan_id=plan.id,
                order_date=plan.next_order_date,
            ).first()
            if existing:
                skipped += 1
                continue

            confirm_cycle = max(1, min(2, int(plan.instrument.dca_confirm_cycle or 1)))
            order = DcaOrder(
                plan_id=plan.id,
                account_id=plan.account_id,
                instrument_id=plan.instrument_id,
                order_date=plan.next_order_date,
                expected_confirm_date=TradingCalendarService.add_trading_days(
                    plan.next_order_date,
                    confirm_cycle,
                ),
                amount=plan.amount,
                fee=0.0,
                status="pending",
            )
            db.session.add(order)

            plan.last_order_date = plan.next_order_date
            plan.next_order_date = DcaPlanService.calculate_next_order_date(
                plan,
                from_date=plan.next_order_date,
            )
            created += 1

        db.session.commit()
        return {"created": created, "skipped": skipped}
