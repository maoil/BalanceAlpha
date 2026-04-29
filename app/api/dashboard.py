from flask import request

from app.api import bp
from app.api.responses import success
from app.schemas.serializers import serialize_account_summary, serialize_signal, serialize_trade
from app.services.account_service import AccountService
from app.services.dashboard_metrics_service import DashboardMetricsService
from app.services.market_sentiment_service import MarketSentimentService
from app.services.signal_service import SignalService
from app.services.trade_service import TradeService


@bp.get("/dashboard")
def dashboard_snapshot():
    account_summaries = AccountService.get_all_summaries()
    summaries = [entry["summary"] for entry in account_summaries.values()]

    total_value = sum(summary["total_market_value"] for summary in summaries)
    total_pnl = sum(summary["total_unrealized_pnl"] for summary in summaries)
    total_cost = sum(summary["total_cost"] for summary in summaries)
    total_positions = sum(summary["position_count"] for summary in summaries)

    accounts = [
        serialize_account_summary(entry["account"], entry["summary"])
        for entry in account_summaries.values()
    ]
    accounts.sort(key=lambda item: item["id"])

    return success(
        {
            "totals": {
                "market_value": total_value,
                "cost": total_cost,
                "unrealized_pnl": total_pnl,
                "unrealized_pnl_pct": total_pnl / total_cost if total_cost > 0 else 0,
                "position_count": total_positions,
            },
            "accounts": accounts,
            "recent_trades": [
                serialize_trade(trade) for trade in TradeService.get_recent(limit=5)
            ],
            "pending_signals": [
                serialize_signal(signal) for signal in SignalService.get_pending_signals()
            ],
            "market_sentiment": MarketSentimentService.get_dashboard_snapshot(),
        }
    )


@bp.get("/dashboard/asset-trend")
def dashboard_asset_trend():
    days = request.args.get("days", default=30, type=int)
    return success(DashboardMetricsService.get_asset_trend(days=days))


@bp.get("/dashboard/performance-summary")
def dashboard_performance_summary():
    return success(DashboardMetricsService.get_performance_summary())

