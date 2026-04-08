"""
交易记录路由
"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash

from app.services.trade_service import TradeService
from app.services.account_service import AccountService
from app.services.instrument_service import InstrumentService

bp = Blueprint("trades", __name__)


@bp.route("/")
def list_trades():
    """交易列表"""
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
    """录入交易"""
    if request.method == "POST":
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

        TradeService.create(data)
        flash("交易录入成功", "success")
        return redirect(url_for("trades.list_trades"))

    accounts = AccountService.get_all()
    instruments = InstrumentService.get_all()
    return render_template(
        "trades/create.html",
        accounts=accounts,
        instruments=instruments,
    )
