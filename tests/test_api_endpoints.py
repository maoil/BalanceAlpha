from datetime import date

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
