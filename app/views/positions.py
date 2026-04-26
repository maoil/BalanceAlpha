"""
Position management routes.
"""
import logging
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.services.account_service import AccountService
from app.services.instrument_service import InstrumentService
from app.services.position_service import PositionService

logger = logging.getLogger(__name__)

bp = Blueprint("positions", __name__)


@bp.route("/")
def list_positions():
    """Position list."""
    account_id = request.args.get("account_id", type=int)

    positions = PositionService.get_all(account_id=account_id)
    accounts = AccountService.get_all()
    instruments = InstrumentService.get_all()

    return render_template(
        "positions/list.html",
        positions=positions,
        accounts=accounts,
        instruments=instruments,
        selected_account_id=account_id,
    )


@bp.route("/refresh_api", methods=["POST"])
def refresh_api():
    """Refresh prices asynchronously."""
    try:
        from app.services.fund_data_fetcher import FundDataFetcher

        summary = FundDataFetcher.fetch_all_prices()
        refresh_time = datetime.now()

        positions = PositionService.get_all()
        pos_data = []
        for position in positions:
            pos_data.append(
                {
                    "id": position.id,
                    "symbol": position.instrument.symbol if position.instrument else "",
                    "name": position.instrument.name if position.instrument else "",
                    "quantity": position.quantity,
                    "avg_cost": position.avg_cost,
                    "market_price": position.market_price,
                    "market_value": position.market_value,
                    "unrealized_pnl": position.unrealized_pnl,
                    "unrealized_pnl_pct": position.unrealized_pnl_pct,
                    "weight_in_account": position.weight_in_account,
                }
            )

        return jsonify(
            {
                "success": True,
                "updated": summary["updated"],
                "failed": summary["failed"],
                "dca_created": summary.get("dca_created", 0),
                "dca_confirmed": summary.get("dca_confirmed", 0),
                "positions": pos_data,
                "refresh_time": refresh_time.strftime("%H:%M:%S"),
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/create", methods=["GET", "POST"])
def create_position():
    """Create or correct a manual position snapshot."""
    if request.method == "POST":
        try:
            account_id = int(request.form["account_id"])
            symbol = request.form["symbol"].strip()
            name = request.form.get("name", "").strip()
            quantity = float(request.form.get("quantity", 0))
            market_price = float(request.form.get("market_price", 0))
            unrealized_pnl = float(request.form.get("unrealized_pnl", 0))
        except (ValueError, TypeError) as exc:
            flash(f"输入数据格式错误，请检查数字字段: {exc}", "error")
            accounts = AccountService.get_all()
            return render_template("positions/create.html", accounts=accounts)

        if not symbol:
            flash("产品代码不能为空", "error")
            return redirect(url_for("positions.create_position"))
        if quantity <= 0:
            flash("份额必须大于 0", "error")
            return redirect(url_for("positions.create_position"))

        account = AccountService.get_by_id(account_id)
        if not account:
            flash("账户不存在", "error")
            return redirect(url_for("positions.create_position"))

        market_value = quantity * market_price
        cost_value = market_value - unrealized_pnl
        avg_cost = cost_value / quantity if quantity > 0 else 0
        pnl_pct = unrealized_pnl / cost_value if cost_value > 0 else 0

        instrument = InstrumentService.get_by_symbol(symbol)
        if not instrument:
            instrument_type = request.form.get("instrument_type", "etf")
            trade_mode = (
                "exchange_traded" if instrument_type in ("etf", "lof") else "eod_nav"
            )
            instrument = InstrumentService.create(
                {
                    "symbol": symbol,
                    "name": name or symbol,
                    "instrument_type": instrument_type,
                    "trade_mode": trade_mode,
                    "default_account_type": account.account_type,
                    "status": "active",
                }
            )
            flash(f"产品 {symbol} 自动创建成功", "info")

        PositionService.create_manual(
            account_id=account_id,
            instrument_id=instrument.id,
            quantity=quantity,
            avg_cost=avg_cost,
            market_price=market_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=pnl_pct,
        )

        flash(f"持仓 {symbol} 录入成功（市值 ¥{market_value:,.2f}）", "success")
        return redirect(url_for("positions.list_positions"))

    accounts = AccountService.get_all()
    return render_template("positions/create.html", accounts=accounts)


@bp.route("/<int:position_id>")
def position_detail(position_id: int):
    """Position detail."""
    position = PositionService.get_by_id(position_id)
    if not position:
        flash("持仓不存在", "error")
        return redirect(url_for("positions.list_positions"))
    return render_template("positions/detail.html", position=position)


@bp.route("/<int:position_id>/update", methods=["POST"])
def update_position(position_id: int):
    """Manual position adjustment."""
    data = {
        "quantity": request.form.get("quantity"),
        "avg_cost": request.form.get("avg_cost"),
        "market_price": request.form.get("market_price"),
    }
    data = {key: value for key, value in data.items() if value}

    PositionService.manual_update(position_id, data)
    flash("持仓更新成功", "success")
    return redirect(url_for("positions.list_positions"))


@bp.route("/refresh", methods=["POST"])
def refresh_prices():
    """Refresh latest market prices."""
    count = PositionService.refresh_market_prices()
    flash(f"已刷新 {count} 个持仓的市场价格", "success")
    return redirect(url_for("positions.list_positions"))
