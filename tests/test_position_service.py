from app.models.position import Position
from app.services.position_service import PositionService


def test_update_from_trade_recalculates_quantity_and_cost(app, factories):
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

    stored = Position.query.filter_by(
        account_id=account.id,
        instrument_id=instrument.id,
    ).first()
    assert stored is not None
    assert stored.position_status == "closed"
