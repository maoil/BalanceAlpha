from datetime import date, timedelta

import pytest

from app.models.market_data import MarketData
from app.services.market_data_service import MarketDataService


def test_calculate_indicators_generates_ma_drawdown_and_relative_strength(app, factories):
    instrument = factories.create_instrument(symbol="161125", name="标普500LOF")
    start = date(2025, 1, 1)

    for offset in range(25):
        factories.create_market_data(
            instrument_id=instrument.id,
            trade_date=start + timedelta(days=offset),
            close=float(offset + 1),
        )

    MarketDataService.calculate_indicators(instrument.id)

    latest = MarketData.query.filter_by(instrument_id=instrument.id).order_by(
        MarketData.trade_date.desc()
    ).first()

    assert latest is not None
    assert latest.ma20 == pytest.approx(15.5)
    assert latest.ma60 == pytest.approx(13.0)
    assert latest.drawdown_60d == pytest.approx(0.0)
    assert latest.relative_strength_20d == pytest.approx(4.0)
