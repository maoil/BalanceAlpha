from datetime import date, timedelta

import pandas as pd
import pytest

from app.models.market_data import MarketData
from app.services.market_data_service import MarketDataService


def test_calculate_indicators_uses_nav_series_when_close_is_missing(app, factories):
    instrument = factories.create_instrument(
        symbol="000001",
        name="场外基金",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    start = date(2025, 1, 1)

    for offset in range(25):
        factories.create_market_data(
            instrument_id=instrument.id,
            trade_date=start + timedelta(days=offset),
            nav=float(offset + 1),
            acc_nav=float(offset + 1),
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
    assert latest.return_5d == pytest.approx(0.25)
    assert latest.return_20d == pytest.approx(4.0)


def test_calculate_indicators_populates_exchange_traded_metrics(app, factories):
    instrument = factories.create_instrument(symbol="161125", name="标普500LOF")
    start = date(2025, 1, 1)

    for offset in range(25):
        close = float(100 + offset)
        factories.create_market_data(
            instrument_id=instrument.id,
            trade_date=start + timedelta(days=offset),
            open=close + 0.5,
            high=close + 1,
            low=close - 1,
            close=close,
            nav=round(close / 1.02, 6),
            volume=float(1000 + offset * 10),
            amount=float((1000 + offset * 10) * close),
            turnover_rate=1.5 + offset * 0.01,
        )

    MarketDataService.calculate_indicators(instrument.id)

    latest = MarketData.query.filter_by(instrument_id=instrument.id).order_by(
        MarketData.trade_date.desc()
    ).first()
    history_df = MarketDataService.get_history_df(instrument.id)

    assert latest is not None
    assert latest.prev_close == pytest.approx(123.0)
    assert latest.atr14 == pytest.approx(2.0)
    assert latest.open_gap_pct == pytest.approx(round((124.5 / 123.0) - 1, 4))
    assert latest.amplitude == pytest.approx(round((125.0 - 123.0) / 123.0, 4))
    assert latest.premium_discount_pct == pytest.approx(0.02, abs=1e-4)
    assert latest.breakout_high_20d == pytest.approx(round((124.0 / 123.0) - 1, 4))
    assert latest.breakdown_low_20d == pytest.approx(round((124.0 / 104.0) - 1, 4))
    assert latest.max_drawdown_120d == pytest.approx(0.0, abs=1e-6)
    assert latest.volume_ma20 == pytest.approx(1145.0)
    assert latest.volume_ratio_5d == pytest.approx(round(1240.0 / 1210.0, 4))

    returns = pd.Series([100 + offset for offset in range(25)], dtype=float).pct_change()
    navs = pd.Series([round((100 + offset) / 1.02, 6) for offset in range(25)], dtype=float)
    premium = pd.Series([100 + offset for offset in range(25)], dtype=float) / navs - 1
    expected_volatility = round(
        returns.rolling(window=20, min_periods=5).std(ddof=0).iloc[-1] * (252 ** 0.5),
        4,
    )
    expected_premium_zscore = round(
        (
            (premium - premium.rolling(window=20, min_periods=5).mean())
            / premium.rolling(window=20, min_periods=5).std(ddof=0)
        ).iloc[-1],
        4,
    )
    assert latest.premium_discount_zscore_20d == pytest.approx(expected_premium_zscore)
    assert latest.volatility_20d == pytest.approx(expected_volatility)
    assert {
        "prev_close",
        "amount",
        "turnover_rate",
        "premium_discount_pct",
        "atr14",
        "volatility_20d",
        "volume_ratio_5d",
    }.issubset(history_df.columns)
