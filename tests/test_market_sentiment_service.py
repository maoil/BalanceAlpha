from app.services.account_service import AccountService
from app.services.market_sentiment_service import MarketSentimentService
from app.services.signal_service import SignalService
from app.services.trade_service import TradeService


def test_build_market_heat_combines_indices_hot_rank_and_vix():
    heat = MarketSentimentService._build_market_heat(
        indices=[
            {"name": "上证指数", "change_pct": 1.2},
            {"name": "深证成指", "change_pct": 0.8},
            {"name": "创业板指", "change_pct": 1.5},
            {"name": "沪深300", "change_pct": 0.9},
        ],
        hot_rank=[
            {"change_pct": 9.8},
            {"change_pct": 7.2},
            {"change_pct": 4.1},
            {"change_pct": 2.5},
            {"change_pct": 1.3},
        ],
        hot_up=[
            {"rank_change": 4200},
            {"rank_change": 2800},
            {"rank_change": 1600},
        ],
        vix={"value": 16.5},
    )

    assert heat["score"] is not None
    assert heat["score"] >= 60
    assert heat["level_label"] in {"偏热", "过热"}
    assert "核心指数整体偏强" in heat["summary"]
    assert heat["avg_index_change_pct"] == 1.1
    assert heat["hot_up_ratio"] == 100.0


def test_dashboard_api_returns_market_sentiment_snapshot(client, factories, monkeypatch):
    MarketSentimentService._cache_snapshot = None
    MarketSentimentService._cache_expires_at = None
    account = factories.create_account(
        account_code="core-market-sentiment",
        account_name="Market Sentiment",
        account_type="core",
    )

    monkeypatch.setattr(
        AccountService,
        "get_all_summaries",
        lambda: {
            "core": {
                "account": account,
                "summary": {
                    "total_market_value": 100000.0,
                    "total_unrealized_pnl": 8000.0,
                    "total_unrealized_pnl_pct": 8000.0 / 92000.0,
                    "total_cost": 92000.0,
                    "position_count": 3,
                }
            }
        },
    )
    monkeypatch.setattr(TradeService, "get_recent", lambda limit=5: [])
    monkeypatch.setattr(SignalService, "get_pending_signals", lambda: [])
    monkeypatch.setattr(
        MarketSentimentService,
        "get_dashboard_snapshot",
        lambda force_refresh=False: {
            "updated_at": "2026-04-20 12:00:00",
            "formula_note": "热度评分为自定义观察指标，综合A股指数、人气榜与VIX估算。",
            "errors": [],
            "heat": {
                "score": 68,
                "level_label": "偏热",
                "badge_class": "bg-warning text-dark",
                "summary": "核心指数整体偏强，人气股赚钱效应明显，VIX处于常态警戒区间。",
                "index_score": 64.2,
                "popularity_score": 73.5,
                "risk_score": 71.0,
                "avg_index_change_pct": 0.86,
                "hot_up_ratio": 80.0,
                "top_hot_avg_change_pct": 4.2,
            },
            "vix": {
                "name": "VIX恐慌指数",
                "value": 17.48,
                "change_pct": -2.56,
                "change_amount": -0.46,
                "open": 18.18,
                "prev_close": 17.94,
                "high": 18.24,
                "low": 16.87,
                "level_label": "警戒",
                "badge_class": "bg-info text-dark",
                "description": "情绪开始紧张，需留意外部风险放大。",
            },
            "indices": [
                {"name": "上证指数", "latest": 3200.12, "change_pct": 0.86, "change_amount": 27.31},
                {"name": "深证成指", "latest": 10123.21, "change_pct": 0.71, "change_amount": 70.52},
            ],
            "hot_rank": [
                {"rank": 1, "name": "测试热股", "plain_code": "000001", "change_pct": 5.4},
            ],
            "hot_up": [
                {"rank_change": 1234, "name": "测试飙升股", "plain_code": "300001", "change_pct": 8.2},
            ],
        },
    )

    response = client.get("/api/v1/dashboard")
    payload = response.get_json()["data"]
    market_sentiment = payload["market_sentiment"]

    assert response.status_code == 200
    assert payload["totals"]["market_value"] == 100000.0
    assert market_sentiment["heat"]["score"] == 68
    assert market_sentiment["vix"]["value"] == 17.48
    assert market_sentiment["hot_rank"][0]["plain_code"] == "000001"
    assert market_sentiment["hot_up"][0]["plain_code"] == "300001"
