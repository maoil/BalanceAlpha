"""
Trade record views.
"""
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.models.manual_fund_order import ManualFundOrder
from app.services.account_service import AccountService
from app.services.instrument_service import InstrumentService
from app.services.trade_service import TradeService

bp = Blueprint("trades", __name__)


@bp.route("/")
def list_trades():
    """Trade list."""
    account_id = request.args.get("account_id", type=int)
    instrument_id = request.args.get("instrument_id", type=int)

    trades = TradeService.get_all(
        account_id=account_id,
        instrument_id=instrument_id,
        limit=200,
    )
    accounts = AccountService.get_all()
    instruments = InstrumentService.get_all()

    return render_template(
        "trades/list.html",
        trades=trades,
        accounts=accounts,
        instruments=instruments,
        selected_account_id=account_id,
        selected_instrument_id=instrument_id,
    )


@bp.route("/create", methods=["GET", "POST"])
def create_trade():
    """Manual trade entry."""
    if request.method == "POST":
        try:
            trade_date_str = request.form.get("trade_date", "")
            trade_date = (
                datetime.strptime(trade_date_str, "%Y-%m-%d").date()
                if trade_date_str
                else datetime.now().date()
            )

            data = {
                "account_id": request.form["account_id"],
                "instrument_id": request.form["instrument_id"],
                "trade_date": trade_date,
                "trade_type": request.form["trade_type"],
                "quantity": request.form.get("quantity", 0),
                "price": request.form.get("price", 0),
                "amount": request.form.get("amount", 0),
                "fee": request.form.get("fee", 0),
                "reason_code": request.form.get("reason_code", ""),
                "notes": request.form.get("notes", ""),
            }
        except (ValueError, TypeError, KeyError) as exc:
            flash(f"\u8f93\u5165\u6570\u636e\u683c\u5f0f\u9519\u8bef: {exc}", "error")
            accounts = AccountService.get_all()
            instruments = InstrumentService.get_all()
            return render_template(
                "trades/create.html",
                accounts=accounts,
                instruments=instruments,
            )

        result = TradeService.create(data)
        if isinstance(result, ManualFundOrder):
            flash(
                "\u4ea4\u6613\u5df2\u4fdd\u5b58\uff0c\u5f85\u51c0\u503c\u786e\u8ba4\u540e\u518d\u66f4\u65b0\u6301\u4ed3",
                "info",
            )
        else:
            flash("\u4ea4\u6613\u5f55\u5165\u6210\u529f", "success")
        return redirect(url_for("trades.list_trades"))

    accounts = AccountService.get_all()
    instruments = InstrumentService.get_all()
    return render_template(
        "trades/create.html",
        accounts=accounts,
        instruments=instruments,
    )
