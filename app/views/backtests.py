"""
回测路由
"""
from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash

from app.models.account import Account
from app.models.instrument import Instrument
from app.models.strategy_assignment import StrategyAssignment
from app.models.strategy_template import StrategyTemplate
from app.services.backtest_service import BacktestService

bp = Blueprint("backtests", __name__)


@bp.route("/")
def list_runs():
    """回测列表"""
    runs = BacktestService.list_runs(limit=100)
    accounts = Account.query.filter_by(status="active").order_by(Account.id.asc()).all()
    active_assignment_rows = StrategyAssignment.query.filter_by(status="active").all()
    instrument_ids = sorted({assignment.instrument_id for assignment in active_assignment_rows})
    template_ids = sorted({assignment.template_id for assignment in active_assignment_rows})

    instruments = []
    if instrument_ids:
        instruments = Instrument.query.filter(
            Instrument.id.in_(instrument_ids)
        ).order_by(Instrument.symbol.asc()).all()

    templates = []
    if template_ids:
        templates = StrategyTemplate.query.filter(
            StrategyTemplate.id.in_(template_ids)
        ).order_by(
            StrategyTemplate.account_type.asc(),
            StrategyTemplate.template_name.asc(),
        ).all()

    instrument_account_scope = defaultdict(set)
    template_account_scope = defaultdict(set)
    for assignment in active_assignment_rows:
        instrument_account_scope[assignment.instrument_id].add(str(assignment.account_id))
        template_account_scope[assignment.template_id].add(str(assignment.account_id))

    instrument_account_scope = {
        instrument_id: ",".join(sorted(account_ids))
        for instrument_id, account_ids in instrument_account_scope.items()
    }
    template_account_scope = {
        template_id: ",".join(sorted(account_ids))
        for template_id, account_ids in template_account_scope.items()
    }
    active_assignments = len(active_assignment_rows)
    default_end = date.today()
    default_start = default_end - timedelta(days=365)

    return render_template(
        "backtests/list.html",
        runs=runs,
        accounts=accounts,
        instruments=instruments,
        templates=templates,
        active_assignments=active_assignments,
        instrument_account_scope=instrument_account_scope,
        template_account_scope=template_account_scope,
        default_start=default_start,
        default_end=default_end,
    )


@bp.route("/create", methods=["POST"])
def create_run():
    """创建回测"""
    try:
        account_id = request.form.get("account_id", type=int)
        instrument_id = request.form.get("instrument_id", type=int)
        template_id = request.form.get("template_id", type=int)
        start_date = request.form.get("start_date", type=lambda value: date.fromisoformat(value))
        end_date = request.form.get("end_date", type=lambda value: date.fromisoformat(value))
        initial_capital = request.form.get("initial_capital", type=float) or 100000.0
        fee_rate = request.form.get("fee_rate", type=float) or 0.001
        run_name = (request.form.get("run_name") or "").strip()

        if not account_id:
            raise ValueError("请选择账户")
        if not start_date or not end_date:
            raise ValueError("请选择有效的回测起止日期")

        if not run_name:
            run_name = f"回测_{account_id}_{start_date}_{end_date}"

        run = BacktestService.run_backtest(
            run_name=run_name,
            account_id=account_id,
            instrument_id=instrument_id,
            template_id=template_id,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
        )
        flash(f"回测已完成：{run.run_name}", "success")
        return redirect(url_for("backtests.detail", run_id=run.id))
    except Exception as exc:
        flash(f"创建回测失败：{exc}", "error")
        return redirect(url_for("backtests.list_runs"))


@bp.route("/<int:run_id>")
def detail(run_id: int):
    """回测详情"""
    run = BacktestService.get_run(run_id)
    if not run:
        flash("回测记录不存在", "error")
        return redirect(url_for("backtests.list_runs"))

    params = BacktestService.parse_params(run)
    result = BacktestService.parse_result(run)
    summary = result.get("summary", {})
    trades = result.get("trades", [])
    positions = result.get("positions", [])
    equity_curve = result.get("equity_curve", [])
    scope = result.get("scope", {})

    return render_template(
        "backtests/detail.html",
        run=run,
        params=params,
        result=result,
        summary=summary,
        trades=trades,
        positions=positions,
        equity_curve=equity_curve,
        scope=scope,
    )
