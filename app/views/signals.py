"""
策略建议路由
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from app.services.signal_service import SignalService
from app.services.account_service import AccountService
from app.models.signal import Signal
from app.models.account import Account
from app.models.instrument import Instrument
from app.models.position import Position
from app.models.market_data import MarketData
from app.models.strategy_assignment import StrategyAssignment
from app.utils.constants import PositionStatus

bp = Blueprint("signals", __name__)


@bp.route("/")
def list_signals():
    """当前建议列表"""
    account_id = request.args.get("account_id", type=int)
    show_all = request.args.get("show_all", "0") == "1"
    current_batch_version = SignalService.get_latest_batch_version(
        account_id=account_id,
    )

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
        current_batch_version=current_batch_version,
    )


@bp.route("/generate", methods=["POST"])
def generate_signals():
    """手动触发信号生成"""
    signals = SignalService.generate_signals()
    if signals:
        flash(f"已生成 v{signals[0].batch_version} 版本的 {len(signals)} 个策略信号", "success")
    else:
        flash("本次未生成新的策略信号", "warning")
    return redirect(url_for("signals.list_signals"))


@bp.route("/history")
def signal_history():
    """信号历史"""
    instrument_id = request.args.get("instrument_id", type=int)
    account_id = request.args.get("account_id", type=int)

    instrument = Instrument.query.get(instrument_id) if instrument_id else None
    account = Account.query.get(account_id) if account_id else None

    if instrument_id:
        signals = SignalService.get_instrument_history(
            instrument_id=instrument_id,
            account_id=account_id,
            limit=50,
        )
    else:
        signals = SignalService.get_history(limit=200)

    return render_template(
        "signals/history.html",
        signals=signals,
        instrument=instrument,
        account=account,
    )


@bp.route("/detail/<int:signal_id>")
def rebalance_detail(signal_id):
    """
    查询调仓详情 - 提供渐进式调仓建议

    根据信号关联的产品、持仓、行情数据，计算具体的调仓步骤。
    """
    signal = Signal.query.get_or_404(signal_id)
    instrument = signal.instrument
    account = signal.account

    # 获取当前持仓
    position = Position.query.filter_by(
        account_id=account.id,
        instrument_id=instrument.id,
        position_status=PositionStatus.OPEN.value,
    ).first()

    # 获取最新行情
    latest_md = MarketData.query.filter_by(
        instrument_id=instrument.id,
    ).order_by(MarketData.trade_date.desc()).first()

    # 获取策略绑定
    assignment = StrategyAssignment.query.filter_by(
        account_id=account.id,
        instrument_id=instrument.id,
        status="active",
    ).first()

    # 调用调仓建议服务（占位，待完善）
    rebalance_guide = SignalService.get_rebalance_guidance(
        signal=signal,
        position=position,
        latest_md=latest_md,
        assignment=assignment,
    )
    version_history = SignalService.get_instrument_history(
        instrument_id=instrument.id,
        account_id=account.id,
        limit=10,
    )

    return render_template(
        "signals/detail.html",
        signal=signal,
        instrument=instrument,
        account=account,
        position=position,
        latest_md=latest_md,
        assignment=assignment,
        rebalance_guide=rebalance_guide,
        version_history=version_history,
    )


@bp.route("/api/rebalance-guidance/<int:signal_id>")
def api_rebalance_guidance(signal_id):
    """
    调仓建议 API（JSON 接口）

    返回渐进式调仓计划，供前端或其他服务调用。
    后续可扩展为更详细的分步调仓方案。
    """
    signal = Signal.query.get_or_404(signal_id)
    instrument = signal.instrument
    account = signal.account

    position = Position.query.filter_by(
        account_id=account.id,
        instrument_id=instrument.id,
        position_status=PositionStatus.OPEN.value,
    ).first()

    latest_md = MarketData.query.filter_by(
        instrument_id=instrument.id,
    ).order_by(MarketData.trade_date.desc()).first()

    assignment = StrategyAssignment.query.filter_by(
        account_id=account.id,
        instrument_id=instrument.id,
        status="active",
    ).first()

    guidance = SignalService.get_rebalance_guidance(
        signal=signal,
        position=position,
        latest_md=latest_md,
        assignment=assignment,
    )

    return jsonify({
        "signal_id": signal.id,
        "batch_version": signal.batch_version,
        "instrument": {
            "symbol": instrument.symbol,
            "name": instrument.name,
        },
        "account": {
            "id": account.id,
            "name": account.account_name,
            "type": account.account_type,
        },
        "guidance": guidance,
    })

