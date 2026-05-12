import json
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import inspect, text

from app.extensions import db
from app.models.backtest_run import BacktestRun
from app.models.manual_fund_order import ManualFundOrder
from app.models.signal_ai_analysis import SignalAIAnalysis
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


def test_api_allows_127_0_0_1_vite_origin_by_default(client):
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"


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


def test_dashboard_asset_trend_api_returns_portfolio_history(client, factories):
    account = factories.create_account(
        account_code="core-trend",
        account_name="Core Trend",
        account_type="core",
    )
    first = factories.create_instrument(symbol="510300-trend", name="CSI 300 ETF")
    second = factories.create_instrument(symbol="159915-trend", name="Growth ETF")
    factories.create_position(
        account_id=account.id,
        instrument_id=first.id,
        quantity=100,
        avg_cost=2,
        market_price=2.2,
    )
    factories.create_position(
        account_id=account.id,
        instrument_id=second.id,
        quantity=50,
        avg_cost=4,
        market_price=4.4,
    )
    factories.create_market_data(
        instrument_id=first.id,
        trade_date=date(2026, 4, 20),
        close=2.0,
    )
    factories.create_market_data(
        instrument_id=second.id,
        trade_date=date(2026, 4, 20),
        close=4.0,
    )
    factories.create_market_data(
        instrument_id=first.id,
        trade_date=date(2026, 4, 21),
        close=2.2,
    )
    factories.create_market_data(
        instrument_id=second.id,
        trade_date=date(2026, 4, 21),
        close=4.4,
    )

    response = client.get("/api/v1/dashboard/asset-trend?days=30")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["series"] == [
        {
            "date": "2026-04-20",
            "total_assets": 400.0,
            "total_cost": 400.0,
            "unrealized_pnl": 0.0,
            "daily_pnl": 0.0,
            "net_value": 1.0,
            "daily_return": 0.0,
            "cumulative_return": 0.0,
        },
        {
            "date": "2026-04-21",
            "total_assets": 440.0,
            "total_cost": 400.0,
            "unrealized_pnl": 40.0,
            "daily_pnl": 40.0,
            "net_value": 1.1,
            "daily_return": 0.1,
            "cumulative_return": 0.1,
        },
    ]
    assert payload["summary"]["start_unrealized_pnl"] == 0.0
    assert payload["summary"]["end_unrealized_pnl"] == 40.0
    assert payload["summary"]["total_return"] == 0.1


def test_dashboard_performance_summary_api_returns_real_metrics(client, factories):
    account = factories.create_account(
        account_code="core-performance",
        account_name="Core Performance",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="510500-performance",
        name="CSI 500 ETF",
    )
    factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=2.0,
        market_price=2.4,
    )
    factories.create_market_data(
        instrument_id=instrument.id,
        trade_date=date(2026, 4, 20),
        close=2.2,
    )
    factories.create_market_data(
        instrument_id=instrument.id,
        trade_date=date(2026, 4, 21),
        close=2.4,
    )
    db.session.add(
        Trade(
            account_id=account.id,
            instrument_id=instrument.id,
            trade_date=date(2026, 1, 1),
            trade_type="buy",
            side="buy",
            quantity=100,
            price=2.0,
            amount=200,
        )
    )
    db.session.commit()

    response = client.get("/api/v1/dashboard/performance-summary")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["total_assets"] == 240.0
    assert payload["total_cost"] == 200.0
    assert payload["today_pnl"] == 20.0
    assert payload["change_vs_yesterday"] == 20.0
    assert payload["change_pct_vs_yesterday"] == 0.0909
    assert payload["cumulative_return"] == 0.2
    assert payload["as_of_date"] == "2026-04-21"
    assert payload["annualized_return"] > 0


def test_strategies_performance_api_returns_strategy_metrics(client, factories):
    account = factories.create_account(
        account_code="core-strategy-performance",
        account_name="Core Strategy Performance",
        account_type="core",
    )
    template = factories.create_template(
        template_code="strategy-performance-template",
        template_name="Strategy Performance",
        account_type="core",
        config={"target_weight_lower": 0.1},
    )
    instrument = factories.create_instrument(
        symbol="512880-strategy",
        name="Broker ETF",
    )
    factories.create_assignment(
        account_id=account.id,
        instrument_id=instrument.id,
        template_id=template.id,
        lower=0.1,
        upper=0.2,
    )
    closes = [10.0, 11.0, 10.5, 12.0]
    for offset, close in enumerate(closes):
        factories.create_market_data(
            instrument_id=instrument.id,
            trade_date=date(2026, 4, 20 + offset),
            close=close,
        )

    response = client.get("/api/v1/strategies/performance?days=7")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload[0]["strategy_name"] == "Strategy Performance"
    assert payload[0]["return_7d"] == 0.2
    assert payload[0]["win_rate"] == 0.6667
    assert payload[0]["max_drawdown"] == -0.0455
    assert payload[0]["status"] == "active"


def test_market_vix_history_api_returns_history_series(client, monkeypatch):
    from app.services.market_sentiment_service import MarketSentimentService

    monkeypatch.setattr(
        MarketSentimentService,
        "get_vix_history",
        classmethod(
            lambda cls, days=30, interval="daily": {
                "series": [
                    {"date": "2026-04-20", "value": 18.1},
                    {"date": "2026-04-21", "value": 19.2},
                ],
                "range": "30d",
                "interval": interval,
                "source": "test",
            }
        ),
    )

    response = client.get("/api/v1/market/vix/history?days=30")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["series"][0]["value"] == 18.1
    assert payload["range"] == "30d"


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


def test_positions_api_does_not_fetch_intraday_trends(
    client,
    factories,
    monkeypatch,
):
    from app.services.position_trend_service import PositionTrendService

    account = factories.create_account(
        account_code="core-position-trend",
        account_name="Core Position Trend",
        account_type="core",
    )
    instrument = factories.create_instrument(symbol="510500-trend", name="CSI 500 ETF")
    factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=50,
        avg_cost=3,
        market_price=4,
    )

    monkeypatch.setattr(
        PositionTrendService,
        "build_for_position",
        staticmethod(lambda position: (_ for _ in ()).throw(AssertionError("trend called"))),
    )

    response = client.get(f"/api/v1/positions?account_id={account.id}")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload[0]["instrument"]["symbol"] == "510500-trend"
    assert "trend" not in payload[0]


def test_positions_trends_api_returns_intraday_trend_and_today_change(
    client,
    factories,
    monkeypatch,
):
    from app.services.position_trend_service import PositionTrendService

    account = factories.create_account(
        account_code="core-position-trend-api",
        account_name="Core Position Trend API",
        account_type="core",
    )
    instrument = factories.create_instrument(symbol="510500-trend-api", name="CSI 500 ETF")
    position = factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=50,
        avg_cost=3,
        market_price=4,
    )

    monkeypatch.setattr(
        PositionTrendService,
        "_fetch_intraday_history",
        staticmethod(
            lambda symbol: [
                {"time": "2026-05-12 09:31:00", "value": 3.8},
                {"time": "2026-05-12 14:55:00", "value": 4.0},
            ]
        ),
    )
    monkeypatch.setattr(
        PositionTrendService,
        "_fetch_realtime_change_pct",
        staticmethod(lambda symbol: 0.0123),
    )

    response = client.get(f"/api/v1/positions/trends?account_id={account.id}")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["positions"] == [
        {
            "position_id": position.id,
            "today_change_pct": 0.0123,
            "trend": {
                "source_type": "instrument",
                "interval": "intraday",
                "symbol": "510500-trend-api",
                "points": [
                    {"time": "2026-05-12 09:31:00", "value": 3.8},
                    {"time": "2026-05-12 14:55:00", "value": 4.0},
                ],
                "change_pct": 0.0526,
            },
        }
    ]


def test_positions_trends_api_returns_no_today_change_without_realtime_quote(
    client,
    factories,
    monkeypatch,
):
    from app.services.position_trend_service import PositionTrendService

    account = factories.create_account(
        account_code="core-position-no-trend",
        account_name="Core Position No Trend",
        account_type="core",
    )
    instrument = factories.create_instrument(symbol="020840-no-trend", name="Unbound Fund")
    position = factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=1,
        market_price=1.1,
    )
    monkeypatch.setattr(
        PositionTrendService,
        "_fetch_intraday_history",
        staticmethod(lambda symbol: []),
    )
    monkeypatch.setattr(
        PositionTrendService,
        "_fetch_realtime_change_pct",
        staticmethod(lambda symbol: None),
    )

    response = client.get(f"/api/v1/positions/trends?account_id={account.id}")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["positions"] == [
        {
            "position_id": position.id,
            "today_change_pct": None,
            "trend": None,
        }
    ]


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


def test_manual_fund_buy_api_creates_pending_order_instead_of_trade(
    client, factories, monkeypatch
):
    from app.services.fund_data_fetcher import FundDataFetcher

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

    monkeypatch.setattr(
        FundDataFetcher,
        "get_fund_nav_history_extended",
        staticmethod(lambda *args, **kwargs: pd.DataFrame()),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_realtime_nav",
        staticmethod(lambda symbol: None),
    )

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


def test_manual_fund_buy_api_does_not_use_late_realtime_nav_for_old_order(
    client, factories, monkeypatch
):
    from app.services.fund_data_fetcher import FundDataFetcher
    from app.services.trading_calendar_service import TradingCalendarService

    account = factories.create_account(
        account_code="core-old-fund",
        account_name="Old Fund Order",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="007721-old",
        name="天弘标普500(QDII-FOF)A",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.dca_confirm_cycle = 1
    db.session.commit()

    order_date = date(2026, 1, 5)
    confirm_date = date(2026, 1, 7)

    monkeypatch.setattr(
        TradingCalendarService,
        "add_trading_days",
        staticmethod(lambda current_date, offset: current_date + timedelta(days=offset)),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_fund_nav_history_extended",
        staticmethod(lambda *args, **kwargs: pd.DataFrame()),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_realtime_nav",
        staticmethod(lambda symbol: {"nav": 2.2, "nav_date": date(2026, 4, 27)}),
    )

    response = client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": order_date.isoformat(),
            "trade_type": "buy",
            "amount": 50,
            "fee": 0.05,
        },
    )

    assert response.status_code == 201
    payload = response.get_json()["data"]
    assert payload["status"] == "pending"
    assert payload["order_date"] == order_date.isoformat()
    assert payload["expected_confirm_date"] == confirm_date.isoformat()
    assert Trade.query.count() == 0


def test_manual_fund_buy_api_auto_confirm_preserves_source_order(
    client, factories, monkeypatch
):
    from app.services.fund_data_fetcher import FundDataFetcher
    from app.services.trading_calendar_service import TradingCalendarService

    account = factories.create_account(
        account_code="core-historical-fund",
        account_name="Historical Fund Order",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="007721-history",
        name="天弘标普500(QDII-FOF)A",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.dca_confirm_cycle = 2
    db.session.commit()

    order_date = date(2026, 1, 5)
    confirm_date = date(2026, 1, 7)

    monkeypatch.setattr(
        TradingCalendarService,
        "add_trading_days",
        staticmethod(lambda current_date, offset: current_date + timedelta(days=offset)),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_fund_nav_history_extended",
        staticmethod(
            lambda symbol, start_date=None, end_date=None: pd.DataFrame(
                [
                    {
                        "trade_date": order_date,
                        "nav": 2.0,
                        "acc_nav": 2.0,
                    },
                    {
                        "trade_date": confirm_date,
                        "nav": 2.5,
                        "acc_nav": 2.5,
                    }
                ]
                if start_date == order_date.isoformat()
                else []
            )
        ),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_realtime_nav",
        staticmethod(lambda symbol: None),
    )

    response = client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": order_date.isoformat(),
            "trade_type": "buy",
            "amount": 50,
            "fee": 0.05,
        },
    )

    assert response.status_code == 201
    payload = response.get_json()["data"]
    assert payload["trade_date"] == order_date.isoformat()
    assert payload["price"] == 2.0
    assert payload["source_order"]["order_date"] == order_date.isoformat()
    assert payload["source_order"]["expected_confirm_date"] == confirm_date.isoformat()
    assert payload["source_order"]["actual_confirm_date"] == confirm_date.isoformat()
    assert payload["source_order"]["quote_date_used"] == order_date.isoformat()

    order = ManualFundOrder.query.one()
    assert order.status == "confirmed"
    assert order.linked_trade_id == payload["id"]


def test_trade_list_ignores_stale_manual_order_link_without_source_marker(
    client, factories
):
    account = factories.create_account(
        account_code="core-stale-trade",
        account_name="Stale Trade",
        account_type="core",
    )
    stale_account = factories.create_account(
        account_code="core-stale-order",
        account_name="Stale Order",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="007721-stale",
        name="天弘标普500(QDII-FOF)A",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    stale_instrument = factories.create_instrument(
        symbol="012922-stale",
        name="旧关联基金",
        instrument_type="fund",
        trade_mode="eod_nav",
    )

    trade = Trade(
        account_id=account.id,
        instrument_id=instrument.id,
        trade_date=date(2026, 1, 7),
        trade_type="subscribe",
        side="buy",
        quantity=10,
        price=2,
        amount=20,
        fee=0,
    )
    db.session.add(trade)
    db.session.flush()
    db.session.add(
        ManualFundOrder(
            account_id=stale_account.id,
            instrument_id=stale_instrument.id,
            order_date=date(2026, 4, 24),
            expected_confirm_date=date(2026, 4, 27),
            actual_confirm_date=date(2026, 4, 27),
            trade_type="subscribe",
            side="buy",
            amount=100,
            fee=0,
            confirm_nav=1.99,
            confirm_quantity=50,
            quote_date_used=date(2026, 4, 27),
            status="confirmed",
            linked_trade_id=trade.id,
        )
    )
    db.session.commit()

    response = client.get(f"/api/v1/trades?instrument_id={instrument.id}")

    assert response.status_code == 200
    payload = response.get_json()["data"][0]
    assert payload["id"] == trade.id
    assert payload["source_order"] is None


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


def test_create_instrument_api_persists_zero_confirm_cycle(client):
    response = client.post(
        "/api/v1/instruments",
        json={
            "symbol": "600000",
            "name": "Future Stock",
            "instrument_type": "stock",
            "trade_mode": "exchange_traded",
            "default_account_type": "core",
            "is_dca_eligible": False,
            "dca_confirm_cycle": 0,
            "status": "active",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["data"]["dca_confirm_cycle"] == 0


def test_zero_confirm_cycle_trade_rejects_missing_fee(client, factories):
    account = factories.create_account(
        account_code="core-t0-missing-fee",
        account_name="T0 Missing Fee",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="161725-t0-fee",
        name="T0 Product",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.dca_confirm_cycle = 0
    db.session.commit()

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

    assert response.status_code == 400
    assert "fee is required" in response.get_json()["error"]["message"]
    assert Trade.query.count() == 0
    assert ManualFundOrder.query.count() == 0


def test_zero_confirm_cycle_trade_rejects_missing_price_without_pending_order(
    client, factories
):
    account = factories.create_account(
        account_code="core-t0-missing-price",
        account_name="T0 Missing Price",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="161725-t0-price",
        name="T0 Product",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.dca_confirm_cycle = 0
    db.session.commit()

    response = client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": date.today().isoformat(),
            "trade_type": "buy",
            "quantity": 100,
            "amount": 200,
            "fee": 0,
        },
    )

    assert response.status_code == 400
    assert "price is required" in response.get_json()["error"]["message"]
    assert Trade.query.count() == 0
    assert ManualFundOrder.query.count() == 0


def test_zero_confirm_cycle_trade_creates_trade_and_updates_position(
    client, factories
):
    from app.models.position import Position

    account = factories.create_account(
        account_code="core-t0-trade",
        account_name="T0 Trade",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="161725-t0-ok",
        name="T0 Product",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.dca_confirm_cycle = 0
    db.session.commit()

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
            "fee": 0,
        },
    )

    assert response.status_code == 201
    payload = response.get_json()["data"]
    assert payload["quantity"] == 100
    assert payload["price"] == 2
    assert payload["amount"] == 200
    assert payload["fee"] == 0
    assert payload["source_order"] is None
    assert Trade.query.count() == 1
    assert ManualFundOrder.query.count() == 0

    position = Position.query.one()
    assert position.quantity == 100
    assert position.avg_cost == 2


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
    from app.services.trading_calendar_service import TradingCalendarService

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

    monkeypatch.setattr(
        FundDataFetcher,
        "get_fund_nav_history_extended",
        staticmethod(lambda *args, **kwargs: pd.DataFrame()),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_realtime_nav",
        staticmethod(lambda symbol: None),
    )
    monkeypatch.setattr(
        TradingCalendarService,
        "add_trading_days",
        staticmethod(lambda current_date, offset: current_date + timedelta(days=offset)),
    )

    order_date = date.today() - timedelta(days=1)
    create_response = client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": order_date.isoformat(),
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
        "get_fund_nav_history_extended",
        staticmethod(
            lambda symbol, start_date=None, end_date=None: pd.DataFrame(
                    [
                        {
                            "trade_date": pd.Timestamp(order_date),
                            "nav": 1.25,
                            "acc_nav": 1.25,
                        }
                ]
                if start_date == order_date.isoformat()
                else []
            )
        ),
    )

    response = client.post(f"/api/v1/manual-fund-orders/{order_id}/confirm")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["order"]["status"] == "confirmed"
    assert payload["trade"]["trade_type"] == "subscribe"
    assert payload["trade"]["quantity"] == 800
    assert payload["trade"]["source_order"]["order_date"] == order_date.isoformat()
    assert payload["trade"]["source_order"]["actual_confirm_date"] == date.today().isoformat()
    assert payload["trade"]["source_order"]["quote_date_used"] == order_date.isoformat()
    assert payload["trade"]["source_order"]["confirm_nav"] == 1.25

    trade = Trade.query.one()
    assert trade.price == 1.25
    assert trade.trade_date == order_date
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
    from app.services.trading_calendar_service import TradingCalendarService

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

    monkeypatch.setattr(
        FundDataFetcher,
        "get_fund_nav_history_extended",
        staticmethod(lambda *args, **kwargs: pd.DataFrame()),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_realtime_nav",
        staticmethod(lambda symbol: None),
    )
    monkeypatch.setattr(
        TradingCalendarService,
        "add_trading_days",
        staticmethod(lambda current_date, offset: current_date + timedelta(days=offset)),
    )

    order_date = date.today() - timedelta(days=1)
    client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": order_date.isoformat(),
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
        "get_fund_nav_history_extended",
        staticmethod(
            lambda symbol, start_date=None, end_date=None: pd.DataFrame(
                [
                    {
                        "trade_date": order_date,
                        "nav": 1.2,
                        "acc_nav": 1.2,
                    }
                ]
                if start_date == order_date.isoformat()
                else []
            )
        ),
    )

    response = client.post("/api/v1/positions/refresh")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["summary"]["manual_fund_confirmed"] == 1
    assert Trade.query.count() == 1


def test_refresh_positions_auto_confirms_ready_manual_fund_sell_orders(
    client, factories, monkeypatch
):
    from app.models.position import Position
    from app.services.fund_data_fetcher import FundDataFetcher
    from app.services.trading_calendar_service import TradingCalendarService

    account = factories.create_account(
        account_code="core-manual-sell-refresh",
        account_name="Manual Sell Refresh",
        account_type="core",
    )
    instrument = factories.create_instrument(
        symbol="001939",
        name="Refresh Sell Fund",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.dca_confirm_cycle = 1
    db.session.commit()

    factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=300,
        avg_cost=1.0,
        market_price=1.1,
    )

    sell_date = date(2026, 4, 20)
    confirm_date = sell_date + timedelta(days=1)

    monkeypatch.setattr(
        TradingCalendarService,
        "add_trading_days",
        staticmethod(lambda current_date, offset: current_date + timedelta(days=offset)),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_fund_nav_history_extended",
        staticmethod(lambda *args, **kwargs: pd.DataFrame()),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_realtime_nav",
        staticmethod(lambda symbol: None),
    )

    create_response = client.post(
        "/api/v1/trades",
        json={
            "account_id": account.id,
            "instrument_id": instrument.id,
            "trade_date": sell_date.isoformat(),
            "trade_type": "sell",
            "quantity": 120,
            "fee": 0,
        },
    )

    assert create_response.status_code == 201
    assert create_response.get_json()["data"]["status"] == "pending"

    monkeypatch.setattr(
        FundDataFetcher,
        "fetch_and_update_price",
        staticmethod(lambda instrument_id: {"price": 1.05, "source": "test"}),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_fund_nav_history_extended",
        staticmethod(
            lambda symbol, start_date=None, end_date=None: pd.DataFrame(
                [
                    {
                        "trade_date": sell_date,
                        "nav": 1.2,
                        "acc_nav": 1.2,
                    }
                ]
                if start_date == sell_date.isoformat()
                else []
            )
        ),
    )

    response = client.post("/api/v1/positions/refresh")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["summary"]["manual_fund_confirmed"] == 1

    trade = Trade.query.one()
    assert trade.side == "sell"
    assert trade.trade_type == "redeem"
    assert trade.price == 1.2

    position = Position.query.one()
    assert position.quantity == 180


def test_instrument_page_actions_have_api_equivalents(client, factories, monkeypatch):
    from app.services.fund_data_fetcher import FundDataFetcher

    instrument = factories.create_instrument(symbol="510300", name="CSI 300 ETF")

    monkeypatch.setattr(
        FundDataFetcher,
        "search_fund",
        staticmethod(lambda keyword: [{"symbol": keyword, "name": "CSI 300 ETF"}]),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "get_fund_info",
        staticmethod(lambda fund_code: {"symbol": fund_code, "name": "CSI 300 ETF"}),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "fetch_and_update_price",
        staticmethod(lambda instrument_id: {"price": 4.2, "source": "test"}),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "fetch_and_import_history",
        staticmethod(
            lambda instrument_id, days: {
                "days_requested": days,
                "imported": 2,
                "skipped": 1,
            }
        ),
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "fetch_all_prices",
        staticmethod(lambda: {"updated": 1, "failed": 0, "dca_created": 0}),
    )

    search_response = client.get("/api/v1/instruments/search-fund?keyword=510300")
    assert search_response.status_code == 200
    assert search_response.get_json()["data"][0]["symbol"] == "510300"

    info_response = client.get("/api/v1/instruments/fund-info/510300")
    assert info_response.status_code == 200
    assert info_response.get_json()["data"]["name"] == "CSI 300 ETF"

    price_response = client.post(f"/api/v1/instruments/{instrument.id}/fetch-price")
    assert price_response.status_code == 200
    assert price_response.get_json()["data"] == {"price": 4.2, "source": "test"}

    history_response = client.post(
        f"/api/v1/instruments/{instrument.id}/fetch-history",
        json={"days": 30},
    )
    assert history_response.status_code == 200
    assert history_response.get_json()["data"]["days_requested"] == 30

    all_prices_response = client.post("/api/v1/instruments/fetch-all-prices")
    assert all_prices_response.status_code == 200
    assert all_prices_response.get_json()["data"]["updated"] == 1

    status_response = client.patch(
        f"/api/v1/instruments/{instrument.id}/status",
        json={"status": "disabled"},
    )
    assert status_response.status_code == 200
    assert status_response.get_json()["data"]["status"] == "disabled"


def test_position_manual_create_and_price_refresh_apis(client, factories):
    account = factories.create_account(
        account_code="core-manual-position",
        account_name="Core Manual Position",
        account_type="core",
    )

    create_response = client.post(
        "/api/v1/positions",
        json={
            "account_id": account.id,
            "symbol": "588080",
            "name": "Science ETF",
            "instrument_type": "etf",
            "quantity": 100,
            "market_price": 2.5,
            "unrealized_pnl": 50,
        },
    )

    assert create_response.status_code == 201
    created = create_response.get_json()["data"]
    assert created["quantity"] == 100
    assert created["avg_cost"] == 2.0
    assert created["instrument"]["symbol"] == "588080"

    factories.create_market_data(
        instrument_id=created["instrument_id"],
        trade_date=date(2026, 4, 24),
        close=2.8,
    )

    refresh_response = client.post("/api/v1/positions/refresh-prices")

    assert refresh_response.status_code == 200
    payload = refresh_response.get_json()["data"]
    assert payload["updated"] == 1
    assert payload["positions"][0]["market_price"] == 2.8


def test_trade_detail_api_returns_single_trade(client, factories):
    account = factories.create_account(
        account_code="core-trade-detail",
        account_name="Core Trade Detail",
    )
    instrument = factories.create_instrument(symbol="510050", name="SSE 50 ETF")
    trade = Trade(
        account_id=account.id,
        instrument_id=instrument.id,
        trade_date=date(2026, 4, 23),
        trade_type="buy",
        side="buy",
        quantity=100,
        price=3,
        amount=300,
    )
    db.session.add(trade)
    db.session.commit()

    response = client.get(f"/api/v1/trades/{trade.id}")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["id"] == trade.id
    assert payload["instrument"]["symbol"] == "510050"


def test_signal_history_and_ai_analysis_apis(client, factories, monkeypatch):
    from app.services.ai_analysis_service import AIAnalysisService

    account = factories.create_account(
        account_code="core-signal-api",
        account_name="Core Signal API",
    )
    instrument = factories.create_instrument(symbol="512000", name="Broker ETF")
    signal = Signal(
        account_id=account.id,
        instrument_id=instrument.id,
        signal_date=date(2026, 4, 22),
        signal_type="hold",
        priority=5,
        reason_code="test",
        explanation="Hold",
        status="pending",
        batch_version=2,
    )
    db.session.add(signal)
    db.session.commit()
    analysis = SignalAIAnalysis(
        signal_id=signal.id,
        model_name="test-model",
        summary="Steady hold",
        confidence=0.8,
        status="success",
        output_json=json.dumps({"risk": "low"}),
    )
    db.session.add(analysis)
    db.session.commit()

    history_response = client.get(
        f"/api/v1/signals/history?instrument_id={instrument.id}&account_id={account.id}"
    )
    assert history_response.status_code == 200
    assert history_response.get_json()["data"][0]["id"] == signal.id

    latest_response = client.get(f"/api/v1/signals/{signal.id}/ai-analysis")
    assert latest_response.status_code == 200
    latest_payload = latest_response.get_json()["data"]
    assert latest_payload["summary"] == "Steady hold"
    assert latest_payload["output"] == {"risk": "low"}

    monkeypatch.setattr(
        AIAnalysisService,
        "create_analysis",
        staticmethod(lambda signal_id: analysis),
    )
    create_response = client.post(f"/api/v1/signals/{signal.id}/ai-analysis")
    assert create_response.status_code == 201
    assert create_response.get_json()["data"]["id"] == analysis.id

    monkeypatch.setattr(
        AIAnalysisService,
        "create_batch_analysis",
        staticmethod(lambda signals: {"success": len(signals), "error": 0}),
    )
    batch_response = client.post(
        "/api/v1/signals/ai-analysis/batch",
        json={"account_id": account.id},
    )
    assert batch_response.status_code == 200
    assert batch_response.get_json()["data"] == {"success": 1, "error": 0}


def test_strategy_template_detail_and_update_api_logs_change(client, factories):
    template = factories.create_template(
        template_code="core-api-template",
        template_name="Core API Template",
        account_type="core",
        config={"target_weight_lower": 0.1},
        version="1.0",
    )

    detail_response = client.get(f"/api/v1/settings/strategy-templates/{template.id}")
    assert detail_response.status_code == 200
    assert detail_response.get_json()["data"]["template_code"] == "core-api-template"

    update_response = client.patch(
        f"/api/v1/settings/strategy-templates/{template.id}",
        json={
            "template_name": "Updated Template",
            "description": "updated",
            "config": {"target_weight_lower": 0.2},
        },
    )

    assert update_response.status_code == 200
    payload = update_response.get_json()["data"]
    assert payload["template_name"] == "Updated Template"
    assert payload["config"] == {"target_weight_lower": 0.2}
    assert payload["version"] == "1.1"

    log_count = db.session.execute(
        text("SELECT COUNT(*) FROM system_logs WHERE log_type = 'param_change'")
    ).scalar_one()
    assert log_count == 1


def test_backtest_page_apis_list_create_and_show_detail(
    client, factories, monkeypatch
):
    from app.services.backtest_service import BacktestService

    account = factories.create_account(
        account_code="core-backtest-api",
        account_name="Core Backtest API",
    )
    run = BacktestRun(
        run_name="Existing Run",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        params_json=json.dumps({"account_id": account.id}),
        result_json=json.dumps({"summary": {"final_equity": 101000}}),
        status="completed",
    )
    db.session.add(run)
    db.session.commit()

    list_response = client.get("/api/v1/backtests")
    assert list_response.status_code == 200
    assert list_response.get_json()["data"][0]["run_name"] == "Existing Run"

    def fake_run_backtest(**kwargs):
        created = BacktestRun(
            run_name=kwargs["run_name"],
            start_date=kwargs["start_date"],
            end_date=kwargs["end_date"],
            params_json=json.dumps({"initial_capital": kwargs["initial_capital"]}),
            result_json=json.dumps({"summary": {"final_equity": 100500}}),
            status="completed",
        )
        db.session.add(created)
        db.session.commit()
        return created

    monkeypatch.setattr(
        BacktestService,
        "run_backtest",
        staticmethod(fake_run_backtest),
    )

    create_response = client.post(
        "/api/v1/backtests",
        json={
            "run_name": "API Run",
            "account_id": account.id,
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "initial_capital": 100000,
            "fee_rate": 0.001,
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.get_json()["data"]
    assert created_payload["run_name"] == "API Run"
    assert created_payload["params"] == {"initial_capital": 100000}

    detail_response = client.get(f"/api/v1/backtests/{run.id}")
    assert detail_response.status_code == 200
    assert detail_response.get_json()["data"]["result"]["summary"]["final_equity"] == 101000


def test_logs_api_filters_system_logs(client):
    from app.services.log_service import LogService

    LogService.log(
        log_type="param_change",
        level="info",
        module="settings",
        message="template updated",
        context={"template_id": 1},
    )
    LogService.log(
        log_type="signal",
        level="warning",
        module="signals",
        message="ignored",
    )

    response = client.get("/api/v1/logs?log_type=param_change&level=info&limit=5")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert len(payload) == 1
    assert payload[0]["message"] == "template updated"
    assert payload[0]["context"] == {"template_id": 1}


def test_manual_fund_order_list_and_detail_apis(client, factories):
    account = factories.create_account(
        account_code="core-order-api",
        account_name="Core Order API",
    )
    instrument = factories.create_instrument(
        symbol="161725-api",
        name="Order Fund",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    order = ManualFundOrder(
        account_id=account.id,
        instrument_id=instrument.id,
        order_date=date(2026, 4, 20),
        expected_confirm_date=date(2026, 4, 21),
        trade_type="subscribe",
        side="buy",
        amount=1000,
        status="pending",
    )
    confirmed_order = ManualFundOrder(
        account_id=account.id,
        instrument_id=instrument.id,
        order_date=date(2026, 4, 18),
        expected_confirm_date=date(2026, 4, 19),
        actual_confirm_date=date(2026, 4, 19),
        trade_type="subscribe",
        side="buy",
        amount=500,
        status="confirmed",
    )
    db.session.add_all([order, confirmed_order])
    db.session.commit()

    list_response = client.get(
        f"/api/v1/manual-fund-orders?account_id={account.id}&status=pending"
    )
    assert list_response.status_code == 200
    assert list_response.get_json()["data"][0]["id"] == order.id

    detail_response = client.get(f"/api/v1/manual-fund-orders/{order.id}")
    assert detail_response.status_code == 200
    assert detail_response.get_json()["data"]["instrument"]["symbol"] == "161725-api"

    all_response = client.get(f"/api/v1/manual-fund-orders?account_id={account.id}")
    assert all_response.status_code == 200
    statuses = {item["status"] for item in all_response.get_json()["data"]}
    assert statuses == {"pending", "confirmed"}
