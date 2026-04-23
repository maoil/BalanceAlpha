from app.services.account_service import AccountService
from app.services.market_sentiment_service import MarketSentimentService
from app.services.signal_service import SignalService
from app.services.trade_service import TradeService


def test_dashboard_handles_missing_change_pct_values(client, monkeypatch):
    MarketSentimentService._cache_snapshot = None
    MarketSentimentService._cache_expires_at = None

    monkeypatch.setattr(
        AccountService,
        "get_all_summaries",
        lambda: {
            "core": {
                "summary": {
                    "total_market_value": 100000.0,
                    "total_unrealized_pnl": 8000.0,
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
            "updated_at": "2026-04-23 15:30:00",
            "formula_note": "test formula",
            "errors": [],
            "heat": {
                "score": 55,
                "level_label": "neutral",
                "badge_class": "bg-secondary",
                "summary": "summary",
                "index_score": 52.0,
                "popularity_score": 50.0,
                "risk_score": 61.0,
                "avg_index_change_pct": 0.0,
                "hot_up_ratio": 0.0,
                "top_hot_avg_change_pct": 0.0,
            },
            "vix": {
                "name": "VIX",
                "value": 17.48,
                "change_pct": None,
                "change_amount": None,
                "open": 18.18,
                "prev_close": 17.94,
                "high": 18.24,
                "low": 16.87,
                "level_label": "alert",
                "badge_class": "bg-info text-dark",
                "description": "desc",
            },
            "indices": [
                {"name": "Index A", "latest": 3200.12, "change_pct": None, "change_amount": None},
            ],
            "hot_rank": [
                {"rank": 1, "name": "Hot A", "plain_code": "000001", "change_pct": None},
            ],
            "hot_up": [
                {"rank_change": 1234, "name": "Jump A", "plain_code": "300001", "change_pct": None},
            ],
        },
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "--" in response.get_data(as_text=True)
