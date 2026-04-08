"""
持仓管理路由
"""
import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from app.services.position_service import PositionService
from app.services.account_service import AccountService
from app.services.instrument_service import InstrumentService

logger = logging.getLogger(__name__)

bp = Blueprint("positions", __name__)

# 记录上次刷新时间
_last_refresh_time = None


@bp.route("/")
def list_positions():
    """持仓列表"""
    global _last_refresh_time
    account_id = request.args.get("account_id", type=int)
    auto_refresh = request.args.get("auto", "1")  # 默认自动刷新

    refresh_result = None

    # 自动刷新：每次打开页面时拉取最新报价
    if auto_refresh == "1":
        try:
            from app.services.fund_data_fetcher import FundDataFetcher
            summary = FundDataFetcher.fetch_all_prices()
            _last_refresh_time = datetime.now()
            refresh_result = summary
            if summary["updated"] > 0:
                logger.info(f"自动刷新报价: 成功 {summary['updated']}, 失败 {summary['failed']}")
        except Exception as e:
            logger.error(f"自动刷新报价失败: {e}")
            refresh_result = {"updated": 0, "failed": 0, "error": str(e)}

    positions = PositionService.get_all(account_id=account_id)
    accounts = AccountService.get_all()
    instruments = InstrumentService.get_all()

    return render_template(
        "positions/list.html",
        positions=positions,
        accounts=accounts,
        instruments=instruments,
        selected_account_id=account_id,
        refresh_result=refresh_result,
        last_refresh_time=_last_refresh_time,
    )


@bp.route("/refresh_api", methods=["POST"])
def refresh_api():
    """API: AJAX 刷新报价（不刷新页面）"""
    global _last_refresh_time
    try:
        from app.services.fund_data_fetcher import FundDataFetcher
        summary = FundDataFetcher.fetch_all_prices()
        _last_refresh_time = datetime.now()

        # 返回更新后的持仓数据
        positions = PositionService.get_all()
        pos_data = []
        for p in positions:
            pos_data.append({
                "id": p.id,
                "symbol": p.instrument.symbol if p.instrument else "",
                "name": p.instrument.name if p.instrument else "",
                "quantity": p.quantity,
                "avg_cost": p.avg_cost,
                "market_price": p.market_price,
                "market_value": p.market_value,
                "unrealized_pnl": p.unrealized_pnl,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "weight_in_account": p.weight_in_account,
            })

        return jsonify({
            "success": True,
            "updated": summary["updated"],
            "failed": summary["failed"],
            "positions": pos_data,
            "refresh_time": _last_refresh_time.strftime("%H:%M:%S"),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/create", methods=["GET", "POST"])
def create_position():
    """
    手动录入持仓

    用户输入：账户、产品代码、产品名称、份额、现价、浮盈浮亏
    系统自动计算：成本价、市值、盈亏百分比、权重
    如果产品不存在，自动创建
    """
    if request.method == "POST":
        account_id = int(request.form["account_id"])
        symbol = request.form["symbol"].strip()
        name = request.form.get("name", "").strip()
        quantity = float(request.form.get("quantity", 0))
        market_price = float(request.form.get("market_price", 0))
        unrealized_pnl = float(request.form.get("unrealized_pnl", 0))

        if not symbol:
            flash("产品代码不能为空", "error")
            return redirect(url_for("positions.create_position"))
        if quantity <= 0:
            flash("份额必须大于0", "error")
            return redirect(url_for("positions.create_position"))

        # 自动计算
        market_value = quantity * market_price
        cost_value = market_value - unrealized_pnl
        avg_cost = cost_value / quantity if quantity > 0 else 0
        pnl_pct = unrealized_pnl / cost_value if cost_value > 0 else 0

        # 如果产品不存在，自动创建
        instrument = InstrumentService.get_by_symbol(symbol)
        if not instrument:
            inst_type = request.form.get("instrument_type", "etf")
            trade_mode = "exchange_traded" if inst_type in ("etf", "lof") else "eod_nav"
            instrument = InstrumentService.create({
                "symbol": symbol,
                "name": name or symbol,
                "instrument_type": inst_type,
                "trade_mode": trade_mode,
                "default_account_type": "core",
                "status": "active",
            })
            flash(f"产品 {symbol} 自动创建成功", "info")

        # 创建或更新持仓
        position = PositionService.create_manual(
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
    """持仓详情"""
    position = PositionService.get_by_id(position_id)
    if not position:
        flash("持仓不存在", "error")
        return redirect(url_for("positions.list_positions"))
    return render_template("positions/detail.html", position=position)


@bp.route("/<int:position_id>/update", methods=["POST"])
def update_position(position_id: int):
    """手工修正持仓"""
    data = {
        "quantity": request.form.get("quantity"),
        "avg_cost": request.form.get("avg_cost"),
        "market_price": request.form.get("market_price"),
    }
    data = {k: v for k, v in data.items() if v}

    PositionService.manual_update(position_id, data)
    flash("持仓更新成功", "success")
    return redirect(url_for("positions.list_positions"))


@bp.route("/refresh", methods=["POST"])
def refresh_prices():
    """刷新市场价格"""
    count = PositionService.refresh_market_prices()
    flash(f"已刷新 {count} 个持仓的市场价格", "success")
    return redirect(url_for("positions.list_positions"))
