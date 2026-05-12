from app.extensions import db
from app.services.position_trend_service import PositionTrendService


def test_position_trend_uses_intraday_market_data_for_exchange_traded_position(
    app,
    factories,
    monkeypatch,
):
    account = factories.create_account(account_code="core-trend-own")
    instrument = factories.create_instrument(
        symbol="510500",
        name="CSI 500 ETF",
        instrument_type="etf",
        trade_mode="exchange_traded",
    )
    position = factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=2,
        market_price=2.4,
    )

    def fake_intraday_history(symbol: str):
        assert symbol == "510500"
        return [
            {"time": "2026-05-12 09:31:00", "value": 2.0},
            {"time": "2026-05-12 10:30:00", "value": 2.2},
            {"time": "2026-05-12 14:55:00", "value": 2.4},
        ]

    monkeypatch.setattr(
        PositionTrendService,
        "_fetch_intraday_history",
        staticmethod(fake_intraday_history),
    )

    trend = PositionTrendService.build_for_position(position)

    assert trend == {
        "source_type": "instrument",
        "interval": "intraday",
        "symbol": "510500",
        "points": [
            {"time": "2026-05-12 09:31:00", "value": 2.0},
            {"time": "2026-05-12 10:30:00", "value": 2.2},
            {"time": "2026-05-12 14:55:00", "value": 2.4},
        ],
        "change_pct": 0.2,
    }


def test_position_trend_uses_tracking_index_for_bound_fund(app, factories, monkeypatch):
    account = factories.create_account(account_code="core-trend-index")
    instrument = factories.create_instrument(
        symbol="012734",
        name="E Fund AI ETF Link C",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.tracking_index = "930713.CSI"
    db.session.commit()
    position = factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=1,
        market_price=1.1,
    )

    def fake_intraday_history(symbol: str):
        assert symbol == "930713.CSI"
        return [
            {"time": "2026-05-12 09:31:00", "value": 1000.0},
            {"time": "2026-05-12 14:55:00", "value": 1015.0},
        ]

    monkeypatch.setattr(
        PositionTrendService,
        "_fetch_intraday_history",
        staticmethod(fake_intraday_history),
    )

    trend = PositionTrendService.build_for_position(position)

    assert trend == {
        "source_type": "tracking_index",
        "interval": "intraday",
        "symbol": "930713.CSI",
        "points": [
            {"time": "2026-05-12 09:31:00", "value": 1000.0},
            {"time": "2026-05-12 14:55:00", "value": 1015.0},
        ],
        "change_pct": 0.015,
    }


def test_position_trend_is_empty_for_unbound_fund(app, factories):
    account = factories.create_account(account_code="core-trend-empty")
    instrument = factories.create_instrument(
        symbol="020840",
        name="Unbound Fund",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    position = factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=1,
        market_price=1.1,
    )

    assert PositionTrendService.build_for_position(position) is None


def test_position_snapshot_uses_realtime_quote_change_not_intraday_change(
    app,
    factories,
    monkeypatch,
):
    account = factories.create_account(account_code="core-quote-change")
    instrument = factories.create_instrument(
        symbol="510500",
        name="CSI 500 ETF",
        instrument_type="etf",
        trade_mode="exchange_traded",
    )
    position = factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=2,
        market_price=2.4,
    )

    monkeypatch.setattr(
        PositionTrendService,
        "_fetch_intraday_history",
        staticmethod(
            lambda symbol: [
                {"time": "2026-05-12 09:31:00", "value": 2.0},
                {"time": "2026-05-12 14:55:00", "value": 2.4},
            ]
        ),
    )
    monkeypatch.setattr(
        PositionTrendService,
        "_fetch_realtime_change_pct",
        staticmethod(lambda symbol: 0.0123),
    )

    snapshot = PositionTrendService.build_snapshot_for_position(position)

    assert snapshot["today_change_pct"] == 0.0123
    assert snapshot["trend"]["change_pct"] == 0.2


def test_position_snapshot_uses_tracking_index_realtime_change_for_bound_fund(
    app,
    factories,
    monkeypatch,
):
    account = factories.create_account(account_code="core-index-quote-change")
    instrument = factories.create_instrument(
        symbol="012734",
        name="E Fund AI ETF Link C",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.tracking_index = "930713.CSI"
    db.session.commit()
    position = factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=1,
        market_price=1.1,
    )
    requested_symbols = []

    monkeypatch.setattr(
        PositionTrendService,
        "_fetch_intraday_history",
        staticmethod(
            lambda symbol: [
                {"time": "2026-05-12 09:31:00", "value": 1000.0},
                {"time": "2026-05-12 14:55:00", "value": 1015.0},
            ]
        ),
    )

    def fake_realtime_change(symbol: str):
        requested_symbols.append(symbol)
        return -0.006

    monkeypatch.setattr(
        PositionTrendService,
        "_fetch_realtime_change_pct",
        staticmethod(fake_realtime_change),
    )

    snapshot = PositionTrendService.build_snapshot_for_position(position)

    assert requested_symbols == ["930713.CSI"]
    assert snapshot["today_change_pct"] == -0.006
    assert snapshot["trend"]["source_type"] == "tracking_index"


def test_parse_sina_stock_quote_change_pct_as_ratio():
    raw = (
        'var hq_str_sh510500="500ETF,3.800,3.900,3.948,3.970,3.780,'
        '0,0,100,200,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-05-12,14:55:00";'
    )

    assert PositionTrendService._parse_sina_quote_change_pct(raw, "sh510500") == 0.0123


def test_parse_sina_index_quote_change_pct_as_ratio():
    raw = 'var hq_str_s_sh930713="CS人工智,1015.00,12.30,1.23,100,200";'

    assert PositionTrendService._parse_sina_quote_change_pct(raw, "s_sh930713") == 0.0123
