"""
策略建议路由
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash

from app.services.signal_service import SignalService
from app.services.account_service import AccountService

bp = Blueprint("signals", __name__)


@bp.route("/")
def list_signals():
    """当前建议列表"""
    account_id = request.args.get("account_id", type=int)
    show_all = request.args.get("show_all", "0") == "1"

    if show_all:
        signals = SignalService.get_latest_signals(account_id=account_id)
    else:
        signals = SignalService.get_latest_signals(
            account_id=account_id,
            status="pending",
        )

    accounts = AccountService.get_all()

    return render_template(
        "signals/list.html",
        signals=signals,
        accounts=accounts,
        selected_account_id=account_id,
        show_all=show_all,
    )


@bp.route("/generate", methods=["POST"])
def generate_signals():
    """手动触发信号生成"""
    signals = SignalService.generate_signals()
    flash(f"已生成 {len(signals)} 个策略信号", "success")
    return redirect(url_for("signals.list_signals"))


@bp.route("/history")
def signal_history():
    """信号历史"""
    signals = SignalService.get_history(limit=200)
    return render_template("signals/history.html", signals=signals)
