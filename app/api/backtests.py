"""
回测 API 端点

第一阶段：单产品 backtesting.py 原生回测
- 移除 account_id、template_id
- 只需要 instrument_id
"""

from datetime import date

from flask import request

from app.api import bp
from app.api.responses import error, success
from app.schemas.serializers import serialize_backtest_run
from app.services.backtest_service import BacktestService


def _parse_date(value: str | None, field_name: str) -> date:
    """解析日期字段"""
    if not value:
        raise ValueError(f"{field_name} is required")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


def _parse_optional_date(value: str | None) -> date | None:
    """解析可选日期字段"""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@bp.get("/backtests")
def list_backtests():
    """获取回测运行列表"""
    limit = request.args.get("limit", default=100, type=int)
    runs = BacktestService.list_runs(limit=limit)
    return success([serialize_backtest_run(run) for run in runs])


@bp.post("/backtests")
def create_backtest():
    """
    创建并运行回测

    请求 payload:
    {
        "run_name": "可选名称",
        "instrument_id": 1,
        "start_date": "2026-02-24",
        "end_date": "2026-05-11",
        "warmup_start_date": "2025-09-01",  // 可选
        "initial_capital": 100000,
        "commission": 0.0003,  // 可选
        "strategy_params": {}  // 可选
    }
    """
    data = request.get_json(silent=True) or {}

    try:
        run_name = (data.get("run_name") or "").strip()
        instrument_id = int(data["instrument_id"])
        start_date = _parse_date(data.get("start_date"), "start_date")
        end_date = _parse_date(data.get("end_date"), "end_date")
        initial_capital = float(data.get("initial_capital", 100000.0))

        warmup_start_date = _parse_optional_date(data.get("warmup_start_date"))

        commission = data.get("commission")
        if commission is not None:
            commission = float(commission)

        strategy_params = data.get("strategy_params")
        if strategy_params is not None and not isinstance(strategy_params, dict):
            raise ValueError("strategy_params must be a JSON object")

    except KeyError as exc:
        return error("validation_error", f"Missing required field: {exc.args[0]}", 400)
    except (TypeError, ValueError) as exc:
        return error("validation_error", str(exc), 400)

    if not run_name:
        run_name = f"backtest_{instrument_id}_{start_date}_{end_date}"

    try:
        run = BacktestService.run_backtest(
            run_name=run_name,
            instrument_id=instrument_id,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            commission=commission,
            warmup_start_date=warmup_start_date,
            strategy_params=strategy_params,
        )
    except ValueError as exc:
        return error("validation_error", str(exc), 400)

    return success(serialize_backtest_run(run), status=201)


@bp.get("/backtests/<int:run_id>")
def get_backtest(run_id: int):
    """获取回测运行详情"""
    run = BacktestService.get_run(run_id)
    if run is None:
        return error("not_found", "Backtest run not found", 404)
    return success(serialize_backtest_run(run))
