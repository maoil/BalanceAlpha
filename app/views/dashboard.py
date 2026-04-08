"""
仪表盘路由
"""
from flask import Blueprint, render_template

from app.services.account_service import AccountService
from app.services.trade_service import TradeService
from app.services.signal_service import SignalService

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    """首页仪表盘"""
    # 账户汇总
    account_summaries = AccountService.get_all_summaries()

    # 计算总览
    total_value = sum(
        s["summary"]["total_market_value"]
        for s in account_summaries.values()
    )
    total_pnl = sum(
        s["summary"]["total_unrealized_pnl"]
        for s in account_summaries.values()
    )
    total_cost = sum(
        s["summary"]["total_cost"]
        for s in account_summaries.values()
    )
    total_positions = sum(
        s["summary"]["position_count"]
        for s in account_summaries.values()
    )

    # 最近交易
    recent_trades = TradeService.get_recent(limit=5)

    # 待处理信号
    pending_signals = SignalService.get_pending_signals()

    return render_template(
        "dashboard.html",
        account_summaries=account_summaries,
        total_value=total_value,
        total_pnl=total_pnl,
        total_cost=total_cost,
        total_pnl_pct=total_pnl / total_cost if total_cost > 0 else 0,
        total_positions=total_positions,
        recent_trades=recent_trades,
        pending_signals=pending_signals,
    )
