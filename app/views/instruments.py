"""
产品管理路由
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from app.services.instrument_service import InstrumentService
from app.services.fund_data_fetcher import FundDataFetcher, DEFAULT_HISTORY_DAYS
from app.models.strategy_template import StrategyTemplate
from app.models.account import Account

bp = Blueprint("instruments", __name__)


@bp.route("/search_fund")
def search_fund():
    """API: 搜索基金/ETF（前端 AJAX 调用）"""
    keyword = request.args.get("keyword", "").strip()
    if not keyword or len(keyword) < 2:
        return jsonify([])
    results = FundDataFetcher.search_fund(keyword)
    return jsonify(results)


@bp.route("/fund_info/<fund_code>")
def get_fund_info(fund_code: str):
    """API: 获取基金详细信息"""
    info = FundDataFetcher.get_fund_info(fund_code)
    if info:
        return jsonify(info)
    return jsonify({"error": "未找到基金信息"}), 404


@bp.route("/<int:instrument_id>/fetch_price", methods=["POST"])
def fetch_price(instrument_id: int):
    """获取单个产品最新价格"""
    result = FundDataFetcher.fetch_and_update_price(instrument_id)
    if result:
        flash(f"价格已更新: {result['price']} ({result['source']})", "success")
    else:
        flash("获取价格失败，请检查产品代码", "error")
    return redirect(url_for("instruments.list_instruments"))


@bp.route("/<int:instrument_id>/fetch_history", methods=["POST"])
def fetch_history(instrument_id: int):
    """抓取并导入历史行情数据"""
    days = int(request.form.get("days", DEFAULT_HISTORY_DAYS))
    result = FundDataFetcher.fetch_and_import_history(instrument_id, days=days)
    if "error" in result:
        flash(f"导入失败: {result['error']}", "error")
    else:
        flash(
            f"历史数据导入: 近 {result['days_requested']} 天, 新增 {result['imported']} 条, 跳过 {result['skipped']} 条",
            "success",
        )
    return redirect(url_for("instruments.list_instruments"))


@bp.route("/fetch_all_prices", methods=["POST"])
def fetch_all_prices():
    """批量获取所有产品最新价格"""
    summary = FundDataFetcher.fetch_all_prices()
    flash(f"价格更新完成: 成功 {summary['updated']}, 失败 {summary['failed']}", "success")
    return redirect(url_for("positions.list_positions"))


@bp.route("/")
def list_instruments():
    """产品列表"""
    status_filter = request.args.get("status", "")
    account_filter = request.args.get("account_type", "")

    instruments = InstrumentService.get_all(
        status=status_filter or None,
        account_type=account_filter or None,
    )

    return render_template(
        "instruments/list.html",
        instruments=instruments,
        status_filter=status_filter,
        account_filter=account_filter,
        default_history_days=DEFAULT_HISTORY_DAYS,
        default_history_years=DEFAULT_HISTORY_DAYS // 365,
    )


@bp.route("/create", methods=["GET", "POST"])
def create_instrument():
    """新增产品"""
    if request.method == "POST":
        data = {
            "symbol": request.form["symbol"],
            "name": request.form["name"],
            "instrument_type": request.form["instrument_type"],
            "market": request.form.get("market", ""),
            "trade_mode": request.form.get("trade_mode", "eod_nav"),
            "default_account_type": request.form.get("default_account_type", "core"),
            "default_strategy_template": request.form.get("default_strategy_template", ""),
            "is_dca_eligible": "is_dca_eligible" in request.form,
            "status": request.form.get("status", "active"),
            "notes": request.form.get("notes", ""),
        }

        # 检查重复
        existing = InstrumentService.get_by_symbol(data["symbol"])
        if existing:
            flash(f"产品代码 {data['symbol']} 已存在", "error")
            return redirect(url_for("instruments.create_instrument"))

        InstrumentService.create(data)
        flash(f"产品 {data['symbol']} 创建成功", "success")
        return redirect(url_for("instruments.list_instruments"))

    templates = StrategyTemplate.query.filter_by(status="active").all()
    accounts = Account.query.all()
    return render_template(
        "instruments/create.html",
        templates=templates,
        accounts=accounts,
    )


@bp.route("/<int:instrument_id>/edit", methods=["GET", "POST"])
def edit_instrument(instrument_id: int):
    """编辑产品"""
    instrument = InstrumentService.get_by_id(instrument_id)
    if not instrument:
        flash("产品不存在", "error")
        return redirect(url_for("instruments.list_instruments"))

    if request.method == "POST":
        data = {
            "name": request.form["name"],
            "instrument_type": request.form["instrument_type"],
            "market": request.form.get("market", ""),
            "trade_mode": request.form.get("trade_mode", "eod_nav"),
            "default_account_type": request.form.get("default_account_type", "core"),
            "default_strategy_template": request.form.get("default_strategy_template", ""),
            "is_dca_eligible": "is_dca_eligible" in request.form,
            "status": request.form.get("status", "active"),
            "notes": request.form.get("notes", ""),
        }
        InstrumentService.update(instrument_id, data)
        flash("产品更新成功", "success")
        return redirect(url_for("instruments.list_instruments"))

    templates = StrategyTemplate.query.filter_by(status="active").all()
    accounts = Account.query.all()
    return render_template(
        "instruments/edit.html",
        instrument=instrument,
        templates=templates,
        accounts=accounts,
    )


@bp.route("/<int:instrument_id>/status", methods=["POST"])
def update_status(instrument_id: int):
    """更新产品状态"""
    new_status = request.form.get("status", "active")
    InstrumentService.update_status(instrument_id, new_status)
    flash("状态更新成功", "success")
    return redirect(url_for("instruments.list_instruments"))
