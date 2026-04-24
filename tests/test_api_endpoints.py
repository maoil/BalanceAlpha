from datetime import date, timedelta

from sqlalchemy import inspect, text

from app.extensions import db
from app.models.signal import Signal
from app.models.trade import Trade


def test_api_health_returns_versioned_status(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "data": {
            "service": "balancealpha-api",
            "status": "ok",
            "version": "v1",
        }
    }


def test_api_adds_cors_headers_for_configured_origin(client):
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Content-Type" in response.headers["Access-Control-Allow-Headers"]
    assert "PATCH" in response.headers["Access-Control-Allow-Methods"]


def test_dashboard_api_returns_aggregate_snapshot(app, client, factories, monkeypatch):
    from app.services.market_sentiment_service import MarketSentimentService

    account = factories.create_account(
        account_code="core-api",
        account_name="Core API",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="510300",
        name="CSI 300 ETF",
        instrument_type="etf",
    )
    factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=2.0,
        market_price=2.5,
    )
    db.session.add(
        Trade(
            account_id=account.id,
            instrument_id=instrument.id,
            trade_date=date(2026, 4, 20),
            trade_type="buy",
            side="buy",
            quantity=100,
            price=2.0,
            amount=200,
        )
    )
    db.session.add(
        Signal(
            account_id=account.id,
            instrument_id=instrument.id,
            signal_date=date(2026, 4, 21),
            signal_type="hold",
            priority=5,
            reason_code="test",
            explanation="Hold",
            status="pending",
            batch_version=1,
        )
    )
    db.session.commit()

    monkeypatch.setattr(
        MarketSentimentService,
        "get_dashboard_snapshot",
        staticmethod(lambda: {"vix": {"value": 18.5}}),
    )

    response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["totals"]["market_value"] == 250
    assert payload["totals"]["cost"] == 200
    assert payload["totals"]["unrealized_pnl"] == 50
    assert payload["totals"]["position_count"] == 1
    assert payload["accounts"][0]["account_code"] == "core-api"
    assert payload["recent_trades"][0]["instrument"]["symbol"] == "510300"
    assert payload["pending_signals"][0]["signal_type"] == "hold"
    assert payload["market_sentiment"] == {"vix": {"value": 18.5}}


def test_positions_api_lists_and_filters_positions(client, factories):
    core = factories.create_account(
        account_code="core-positions",
        account_name="Core Positions",
        account_type="core",
    )
    tactical = factories.create_account(
        account_code="tactical-positions",
        account_name="Tactical Positions",
        account_type="tactical",
    )
    first = factories.create_instrument(symbol="510500", name="CSI 500 ETF")
    second = factories.create_instrument(symbol="159915", name="Growth ETF")
    factories.create_position(
        account_id=core.id,
        instrument_id=first.id,
        quantity=50,
        avg_cost=3,
        market_price=4,
    )
    factories.create_position(
        account_id=tactical.id,
        instrument_id=second.id,
        quantity=20,
        avg_cost=5,
        market_price=6,
    )

    response = client.get(f"/api/v1/positions?account_id={core.id}")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert len(payload) == 1
    assert payload[0]["account"]["account_code"] == "core-positions"
    assert payload[0]["instrument"]["symbol"] == "510500"
    assert payload[0]["market_value"] == 200


def test_position_api_patch_updates_position_without_csrf_token(client, factories):
    account = factories.create_account(
        account_code="core-patch",
        account_name="Core Patch",
        account_type="core",
    )
    instrument = factories.create_instrument(symbol="588000", name="STAR ETF")
    position = factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=10,
        avg_cost=1,
        market_price=1.5,
    )

    response = client.patch(
        f"/api/v1/positions/{position.id}",
        json={"quantity": 12, "avg_cost": 1.25, "market_price": 1.8},
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["quantity"] == 12
    assert payload["avg_cost"] == 1.25
    assert payload["market_price"] == 1.8
    assert payload["market_value"] == 21.6


def test_signal_guidance_api_loads_rebalance_context(client, factories, monkeypatch):
    from app.services.signal_service import SignalService

    account = factories.create_account(
        account_code="core-guidance",
        account_name="Core Guidance",
        account_type="core",
    )
    instrument = factories.create_instrument(symbol="512880", name="Broker ETF")
    template = factories.create_template(
        template_code="guidance-template",
        template_name="Guidance Template",
        account_type="core",
        config={"target_weight_lower": 0.1, "target_weight_upper": 0.2},
    )
    factories.create_assignment(
        account_id=account.id,
        instrument_id=instrument.id,
        template_id=template.id,
        lower=0.1,
        upper=0.2,
    )
    position = factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=1.0,
        market_price=1.2,
    )
    market_data = factories.create_market_data(
        instrument_id=instrument.id,
        trade_date=date(2026, 4, 22),
        close=1.2,
    )
    signal = Signal(
        account_id=account.id,
        instrument_id=instrument.id,
        signal_date=date(2026, 4, 22),
        signal_type="rebalance",
        priority=1,
        reason_code="test",
        explanation="Rebalance",
        status="pending",
        batch_version=1,
    )
    db.session.add(signal)
    db.session.commit()

    def fake_guidance(signal, position, latest_md, assignment):
        assert position.id == position_id
        assert latest_md.id == market_data.id
        assert assignment.instrument_id == instrument.id
        return {"position_id": position.id, "market_data_id": latest_md.id}

    position_id = position.id
    monkeypatch.setattr(
        SignalService,
        "get_rebalance_guidance",
        staticmethod(fake_guidance),
    )

    response = client.get(f"/api/v1/signals/{signal.id}/rebalance-guidance")

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "position_id": position.id,
        "market_data_id": market_data.id,
    }


def test_manual_fund_buy_api_creates_pending_order_instead_of_trade(client, factories):
    account = factories.create_account(
        account_code="core-manual-fund",
        account_name="Manual Fund",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="161725",
        name="招商中证白酒",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.dca_confirm_cycle = 1
    db.session.commit()

    trade_date = date.today() - timedelta(days=1)
    response = client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": trade_date.isoformat(),
            "trade_type": "buy",
            "amount": 1000,
            "fee": 5,
            "reason_code": "manual_entry",
            "notes": "pending first",
        },
    )

    assert response.status_code == 201
    payload = response.get_json()["data"]
    assert payload["status"] == "pending"
    assert payload["amount"] == 1000
    assert payload["fee"] == 5
    assert payload["instrument"]["symbol"] == "161725"
    assert Trade.query.count() == 0
    assert inspect(db.engine).has_table("manual_fund_orders")
    pending_count = db.session.execute(
        text("SELECT COUNT(*) FROM manual_fund_orders")
    ).scalar_one()
    assert pending_count == 1


def test_exchange_traded_buy_api_still_creates_trade(client, factories):
    account = factories.create_account(
        account_code="core-etf-buy",
        account_name="ETF Buy",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="510300",
        name="CSI 300 ETF",
        instrument_type="etf",
        trade_mode="exchange_traded",
    )

    response = client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": date.today().isoformat(),
            "trade_type": "buy",
            "quantity": 100,
            "price": 2,
            "amount": 200,
        },
    )

    assert response.status_code == 201
    payload = response.get_json()["data"]
    assert payload["trade_type"] == "buy"
    assert Trade.query.count() == 1
    pending_count = db.session.execute(
        text("SELECT COUNT(*) FROM manual_fund_orders")
    ).scalar_one()
    assert pending_count == 0


def test_manual_fund_order_confirm_api_returns_not_ready_error_before_expected_date(
    client, factories, monkeypatch
):
    from app.services.fund_data_fetcher import FundDataFetcher

    account = factories.create_account(
        account_code="core-manual-not-ready",
        account_name="Manual Not Ready",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="163406",
        name="兴全合润",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.dca_confirm_cycle = 2
    db.session.commit()

    create_response = client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": date.today().isoformat(),
            "trade_type": "buy",
            "amount": 1000,
        },
    )
    order_id = create_response.get_json()["data"]["id"]

    monkeypatch.setattr(
        FundDataFetcher,
        "get_realtime_nav",
        staticmethod(lambda symbol: {"nav": 1.2, "nav_date": date.today()}),
    )

    response = client.post(f"/api/v1/manual-fund-orders/{order_id}/confirm")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    assert Trade.query.count() == 0


def test_manual_fund_order_confirm_api_creates_trade_and_position_when_ready(
    client, factories, monkeypatch
):
    from app.models.position import Position
    from app.services.fund_data_fetcher import FundDataFetcher

    account = factories.create_account(
        account_code="core-manual-confirm",
        account_name="Manual Confirm",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="161725-confirm",
        name="Confirm Fund",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.dca_confirm_cycle = 1
    db.session.commit()

    create_response = client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": (date.today() - timedelta(days=3)).isoformat(),
            "trade_type": "buy",
            "amount": 1000,
            "fee": 0,
            "reason_code": "manual_confirm",
            "notes": "confirm later",
        },
    )
    order_id = create_response.get_json()["data"]["id"]

    monkeypatch.setattr(
        FundDataFetcher,
        "get_realtime_nav",
        staticmethod(lambda symbol: {"nav": 1.25, "nav_date": date.today()}),
    )

    response = client.post(f"/api/v1/manual-fund-orders/{order_id}/confirm")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["order"]["status"] == "confirmed"
    assert payload["trade"]["trade_type"] == "subscribe"
    assert payload["trade"]["quantity"] == 800

    trade = Trade.query.one()
    assert trade.price == 1.25
    assert trade.trade_date == date.today()
    assert trade.reason_code == "manual_confirm"
    assert trade.notes == "confirm later"

    position = Position.query.one()
    assert position.quantity == 800
    assert position.avg_cost == 1.25

    row = db.session.execute(
        text(
            "SELECT status, confirm_nav, confirm_quantity, linked_trade_id "
            "FROM manual_fund_orders WHERE id = :order_id"
        ),
        {"order_id": order_id},
    ).mappings().one()
    assert row["status"] == "confirmed"
    assert row["confirm_nav"] == 1.25
    assert row["confirm_quantity"] == 800
    assert row["linked_trade_id"] == trade.id


def test_refresh_positions_auto_confirms_ready_manual_fund_orders(
    client, factories, monkeypatch
):
    from app.services.fund_data_fetcher import FundDataFetcher

    account = factories.create_account(
        account_code="core-manual-refresh",
        account_name="Manual Refresh",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="001938",
        name="Refresh Fund",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.dca_confirm_cycle = 1
    db.session.commit()

    client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": (date.today() - timedelta(days=3)).isoformat(),
            "trade_type": "buy",
            "amount": 600,
        },
    )

    monkeypatch.setattr(
        FundDataFetcher,
        "fetch_and_update_price",
        staticmethod(lambda instrument_id: {"price": 1.0, "source": "test"}),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_realtime_nav",
        staticmethod(lambda symbol: {"nav": 1.2, "nav_date": date.today()}),
    )

    response = client.post("/api/v1/positions/refresh")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["summary"]["manual_fund_confirmed"] == 1
    assert Trade.query.count() == 1
