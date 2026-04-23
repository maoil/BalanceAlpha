from datetime import date

from app.extensions import db


def test_generate_due_order_creates_pending_order_with_expected_confirm_date(app, factories, monkeypatch):
    from app.models.dca_order import DcaOrder
    from app.models.dca_plan import DcaPlan
    from app.services.dca_plan_service import DcaPlanService
    from app.services.trading_calendar_service import TradingCalendarService

    account = factories.create_account(
        account_code="core-dca-generate",
        account_name="DCA Generate",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="163406",
        name="兴全合润",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.is_dca_eligible = True
    instrument.dca_confirm_cycle = 2
    db.session.commit()

    plan = DcaPlan(
        account_id=account.id,
        instrument_id=instrument.id,
        amount=1000.0,
        schedule_type="monthly",
        schedule_day=31,
        start_date=date(2026, 1, 1),
        next_order_date=date(2026, 2, 27),
        status="active",
    )
    db.session.add(plan)
    db.session.commit()

    monkeypatch.setattr(
        TradingCalendarService,
        "add_trading_days",
        staticmethod(lambda current_date, offset: date(2026, 3, 3)),
    )
    monkeypatch.setattr(
        DcaPlanService,
        "calculate_next_order_date",
        staticmethod(lambda plan, from_date=None: date(2026, 3, 31)),
    )

    summary = DcaPlanService.generate_due_orders(run_date=date(2026, 2, 27))

    assert summary == {"created": 1, "skipped": 0}

    order = DcaOrder.query.one()
    assert order.plan_id == plan.id
    assert order.order_date == date(2026, 2, 27)
    assert order.expected_confirm_date == date(2026, 3, 3)
    assert order.amount == 1000.0
    assert order.status == "pending"


def test_confirm_pending_order_creates_trade_and_updates_position(app, factories, monkeypatch):
    from app.models.dca_order import DcaOrder
    from app.models.dca_plan import DcaPlan
    from app.models.position import Position
    from app.models.trade import Trade
    from app.services.dca_order_service import DcaOrderService

    account = factories.create_account(
        account_code="core-dca-confirm",
        account_name="DCA Confirm",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="161725",
        name="招商中证白酒",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.is_dca_eligible = True
    instrument.dca_confirm_cycle = 1
    db.session.commit()

    plan = DcaPlan(
        account_id=account.id,
        instrument_id=instrument.id,
        amount=1000.0,
        schedule_type="monthly",
        schedule_day=15,
        start_date=date(2026, 1, 1),
        next_order_date=date(2026, 5, 15),
        status="active",
    )
    db.session.add(plan)
    db.session.commit()

    order = DcaOrder(
        plan_id=plan.id,
        account_id=account.id,
        instrument_id=instrument.id,
        order_date=date(2026, 4, 15),
        expected_confirm_date=date(2026, 4, 16),
        amount=1000.0,
        fee=0.0,
        status="pending",
    )
    db.session.add(order)
    db.session.commit()

    monkeypatch.setattr(
        DcaOrderService,
        "_fetch_confirm_quote",
        staticmethod(lambda instrument: {"nav": 1.25, "nav_date": date(2026, 4, 16)}),
    )

    summary = DcaOrderService.confirm_pending_orders(run_date=date(2026, 4, 16))

    assert summary == {"confirmed": 1, "skipped": 0}

    trade = Trade.query.one()
    assert trade.trade_type == "dca_buy"
    assert trade.trade_date == date(2026, 4, 16)
    assert trade.price == 1.25
    assert trade.quantity == 800.0
    assert trade.amount == 1000.0

    position = Position.query.one()
    assert position.quantity == 800.0
    assert position.avg_cost == 1.25

    db.session.refresh(order)
    assert order.status == "confirmed"
    assert order.actual_confirm_date == date(2026, 4, 16)
    assert order.confirm_nav == 1.25
    assert order.confirm_quantity == 800.0
    assert order.linked_trade_id == trade.id


def test_create_dca_instrument_upserts_monthly_plan(app, factories):
    from app.models.dca_plan import DcaPlan
    from app.services.instrument_service import InstrumentService

    factories.create_account(
        account_code="core-dca-plan",
        account_name="DCA Plan",
        account_type="core",
    )

    instrument = InstrumentService.create(
        {
            "symbol": "000001",
            "name": "定投基金",
            "instrument_type": "fund",
            "trade_mode": "eod_nav",
            "default_account_type": "core",
            "is_dca_eligible": True,
            "dca_confirm_cycle": 2,
            "dca_amount": 500.0,
            "dca_schedule_day": 15,
            "status": "active",
        }
    )

    plan = DcaPlan.query.one()
    assert plan.instrument_id == instrument.id
    assert plan.amount == 500.0
    assert plan.schedule_day == 15
    assert plan.status == "active"
    assert instrument.dca_confirm_cycle == 2


def test_fetch_all_prices_triggers_dca_generation_and_confirmation(app, factories, monkeypatch):
    from app.services.dca_order_service import DcaOrderService
    from app.services.dca_plan_service import DcaPlanService
    from app.services.fund_data_fetcher import FundDataFetcher

    factories.create_instrument(symbol="510300", name="沪深300ETF")

    monkeypatch.setattr(
        FundDataFetcher,
        "fetch_and_update_price",
        staticmethod(lambda instrument_id: {"price": 1.0, "source": "test"}),
    )
    monkeypatch.setattr(
        DcaPlanService,
        "generate_due_orders",
        staticmethod(lambda run_date=None: {"created": 2, "skipped": 0}),
    )
    monkeypatch.setattr(
        DcaOrderService,
        "confirm_pending_orders",
        staticmethod(lambda run_date=None: {"confirmed": 1, "skipped": 3}),
    )

    summary = FundDataFetcher.fetch_all_prices()

    assert summary["updated"] == 1
    assert summary["dca_created"] == 2
    assert summary["dca_confirmed"] == 1


def test_create_instrument_view_persists_dca_configuration(app, client, factories):
    from app.models.dca_plan import DcaPlan
    from app.models.instrument import Instrument

    app.config["WTF_CSRF_ENABLED"] = False
    factories.create_account(
        account_code="core-dca-view",
        account_name="DCA View",
        account_type="core",
    )

    response = client.post(
        "/instruments/create",
        data={
            "symbol": "002190",
            "name": "定投创建页基金",
            "instrument_type": "fund",
            "trade_mode": "eod_nav",
            "default_account_type": "core",
            "is_dca_eligible": "on",
            "dca_confirm_cycle": "2",
            "dca_amount": "800",
            "dca_schedule_day": "18",
            "status": "active",
        },
    )

    assert response.status_code == 302

    instrument = Instrument.query.filter_by(symbol="002190").one()
    plan = DcaPlan.query.filter_by(instrument_id=instrument.id).one()
    assert instrument.dca_confirm_cycle == 2
    assert plan.amount == 800.0
    assert plan.schedule_day == 18
