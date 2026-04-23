"""
Instrument management routes.
"""
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.models.account import Account
from app.models.strategy_template import StrategyTemplate
from app.services.fund_data_fetcher import DEFAULT_HISTORY_DAYS, FundDataFetcher
from app.services.instrument_service import InstrumentService

bp = Blueprint("instruments", __name__)


@bp.route("/search_fund")
def search_fund():
    keyword = request.args.get("keyword", "").strip()
    if not keyword or len(keyword) < 2:
        return jsonify([])
    return jsonify(FundDataFetcher.search_fund(keyword))


@bp.route("/fund_info/<fund_code>")
def get_fund_info(fund_code: str):
    info = FundDataFetcher.get_fund_info(fund_code)
    if info:
        return jsonify(info)
    return jsonify({"error": "未找到基金信息"}), 404


@bp.route("/<int:instrument_id>/fetch_price", methods=["POST"])
def fetch_price(instrument_id: int):
    result = FundDataFetcher.fetch_and_update_price(instrument_id)
    if result:
        flash(f"价格已更新: {result['price']} ({result['source']})", "success")
    else:
        flash("获取价格失败，请检查产品代码", "error")
    return redirect(url_for("instruments.list_instruments"))


@bp.route("/<int:instrument_id>/fetch_history", methods=["POST"])
def fetch_history(instrument_id: int):
    days = int(request.form.get("days", DEFAULT_HISTORY_DAYS))
    result = FundDataFetcher.fetch_and_import_history(instrument_id, days=days)
    if "error" in result:
        flash(f"导入失败: {result['error']}", "error")
    else:
        flash(
            f"历史数据导入完成: 请求 {result['days_requested']} 天, 新增 {result['imported']} 条, 跳过 {result['skipped']} 条",
            "success",
        )
    return redirect(url_for("instruments.list_instruments"))


@bp.route("/fetch_all_prices", methods=["POST"])
def fetch_all_prices():
    summary = FundDataFetcher.fetch_all_prices()
    flash(
        "报价刷新完成: 成功 {updated}, 失败 {failed}, 新建待确认定投 {dca_created}, 确认入账 {dca_confirmed}".format(
            updated=summary["updated"],
            failed=summary["failed"],
            dca_created=summary.get("dca_created", 0),
            dca_confirmed=summary.get("dca_confirmed", 0),
        ),
        "success",
    )
    return redirect(url_for("positions.list_positions"))


@bp.route("/")
def list_instruments():
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


def _build_instrument_form_data(form) -> dict:
    return {
        "symbol": form.get("symbol", "").strip(),
        "name": form.get("name", "").strip(),
        "instrument_type": form.get("instrument_type", "fund"),
        "market": form.get("market", ""),
        "trade_mode": form.get("trade_mode", "eod_nav"),
        "default_account_type": form.get("default_account_type", "core"),
        "default_strategy_template": form.get("default_strategy_template", ""),
        "is_dca_eligible": "is_dca_eligible" in form,
        "dca_confirm_cycle": int(form.get("dca_confirm_cycle", 1) or 1),
        "dca_amount": form.get("dca_amount", "").strip(),
        "dca_schedule_day": form.get("dca_schedule_day", "").strip(),
        "status": form.get("status", "active"),
        "notes": form.get("notes", ""),
    }


@bp.route("/create", methods=["GET", "POST"])
def create_instrument():
    if request.method == "POST":
        data = _build_instrument_form_data(request.form)
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
    instrument = InstrumentService.get_by_id(instrument_id)
    if not instrument:
        flash("产品不存在", "error")
        return redirect(url_for("instruments.list_instruments"))

    if request.method == "POST":
        data = _build_instrument_form_data(request.form)
        data.pop("symbol", None)
        InstrumentService.update(instrument_id, data)
        flash("产品更新成功", "success")
        return redirect(url_for("instruments.list_instruments"))

    templates = StrategyTemplate.query.filter_by(status="active").all()
    accounts = Account.query.all()
    dca_plan = instrument.dca_plans.filter_by(status="active").first() or instrument.dca_plans.first()
    return render_template(
        "instruments/edit.html",
        instrument=instrument,
        templates=templates,
        accounts=accounts,
        dca_plan=dca_plan,
    )


@bp.route("/<int:instrument_id>/status", methods=["POST"])
def update_status(instrument_id: int):
    new_status = request.form.get("status", "active")
    InstrumentService.update_status(instrument_id, new_status)
    flash("状态更新成功", "success")
    return redirect(url_for("instruments.list_instruments"))
