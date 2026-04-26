import pytest

from app.models.position import Position
from app.services.instrument_service import InstrumentService
from app.services.position_service import PositionService


def test_update_from_trade_recalculates_quantity_cost_and_closing_fields(app, factories):
    account = factories.create_account(account_code="core-pos", account_name="核心仓位")
    instrument = factories.create_instrument(symbol="513110", name="纳指100ETF")

    position = PositionService.update_from_trade(
        account_id=account.id,
        instrument_id=instrument.id,
        side="buy",
        quantity=10,
        price=10,
    )
    assert position.quantity == 10
    assert position.avg_cost == 10
    assert position.market_value == 100
    assert position.weight_in_account == 1

    position = PositionService.update_from_trade(
        account_id=account.id,
        instrument_id=instrument.id,
        side="buy",
        quantity=10,
        price=20,
    )
    assert position.quantity == 20
    assert position.avg_cost == 15
    assert position.market_value == 400

    position = PositionService.update_from_trade(
        account_id=account.id,
        instrument_id=instrument.id,
        side="sell",
        quantity=5,
        price=18,
    )
    assert position.quantity == 15
    assert position.avg_cost == 15
    assert position.position_status == "open"

    position = PositionService.update_from_trade(
        account_id=account.id,
        instrument_id=instrument.id,
        side="sell",
        quantity=15,
        price=18,
    )
    assert position.quantity == 0
    assert position.position_status == "closed"
    assert position.market_value == 0
    assert position.unrealized_pnl == 0
    assert position.weight_in_account == 0

    stored = Position.query.filter_by(
        account_id=account.id,
        instrument_id=instrument.id,
    ).first()
    assert stored is not None
    assert stored.position_status == "closed"
    assert stored.market_value == 0


def test_update_from_trade_recalculates_account_weights(app, factories):
    account = factories.create_account(account_code="core-weight", account_name="权重账户")
    first = factories.create_instrument(symbol="510300", name="沪深300ETF")
    second = factories.create_instrument(symbol="159915", name="创业板ETF")

    first_position = PositionService.update_from_trade(
        account_id=account.id,
        instrument_id=first.id,
        side="buy",
        quantity=10,
        price=10,
    )
    assert first_position.weight_in_account == 1

    second_position = PositionService.update_from_trade(
        account_id=account.id,
        instrument_id=second.id,
        side="buy",
        quantity=10,
        price=10,
    )
    assert first_position.weight_in_account == pytest.approx(0.5)
    assert second_position.weight_in_account == pytest.approx(0.5)

    second_position = PositionService.update_from_trade(
        account_id=account.id,
        instrument_id=second.id,
        side="sell",
        quantity=5,
        price=10,
    )

    refreshed_first = Position.query.filter_by(
        account_id=account.id,
        instrument_id=first.id,
    ).one()
    assert refreshed_first.weight_in_account == pytest.approx(2 / 3)
    assert second_position.weight_in_account == pytest.approx(1 / 3)


def test_update_instrument_account_moves_open_position(app, factories):
    core = factories.create_account(
        account_code="core-sync",
        account_name="核心账户",
        account_type="core",
    )
    tactical = factories.create_account(
        account_code="tactical-sync",
        account_name="战术账户",
        account_type="tactical",
    )
    instrument = factories.create_instrument(
        symbol="512880",
        name="券商ETF",
        default_account_type="core",
    )
    factories.create_position(
        account_id=core.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=1,
        market_price=1.2,
    )

    updated = InstrumentService.update(
        instrument.id,
        {"default_account_type": "tactical"},
    )

    assert updated is not None
    assert updated.default_account_type == "tactical"

    moved = Position.query.filter_by(
        account_id=tactical.id,
        instrument_id=instrument.id,
        position_status="open",
    ).one()
    assert moved.quantity == 100
    assert moved.weight_in_account == 1
