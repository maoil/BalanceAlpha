"""
策略信号服务

根据 PRD §7.7 / §11 实现：
- 核心账户：配置优先，基于权重偏离 + 评分 + 回撤
- 战术账户：趋势优先，基于均线 + 止损 + 止盈
"""
import json
import logging
from typing import Optional
from datetime import date
from uuid import uuid4

from app.extensions import db
from app.models.signal import Signal
from app.models.position import Position
from app.models.instrument import Instrument
from app.models.market_data import MarketData
from app.models.account import Account
from app.models.strategy_assignment import StrategyAssignment
from app.models.strategy_template import StrategyTemplate
from app.utils.constants import (
    SignalType, SignalStatus, AccountType,
    InstrumentStatus, PositionStatus,
)

logger = logging.getLogger(__name__)


class SignalService:
    """策略信号计算服务"""

    @staticmethod
    def get_latest_batch_version(
        account_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> Optional[int]:
        """获取当前最新的生成版本号"""
        query = db.session.query(db.func.max(Signal.batch_version))
        if account_id:
            query = query.filter(Signal.account_id == account_id)
        if status:
            query = query.filter(Signal.status == status)
        return query.scalar()

    @staticmethod
    def get_latest_signals(
        account_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> list[Signal]:
        """仅获取最新版本的信号"""
        latest_batch_version = SignalService.get_latest_batch_version(
            account_id=account_id,
        )
        if latest_batch_version is None:
            return []

        query = Signal.query.filter_by(batch_version=latest_batch_version)
        if account_id:
            query = query.filter_by(account_id=account_id)
        if status:
            query = query.filter_by(status=status)
        return query.order_by(
            Signal.priority.asc(),
            Signal.account_id.asc(),
            Signal.instrument_id.asc(),
        ).all()

    @staticmethod
    def get_pending_signals() -> list[Signal]:
        """获取待处理信号"""
        return Signal.query.filter_by(
            status=SignalStatus.PENDING.value
        ).order_by(Signal.priority, Signal.signal_date.desc()).all()

    @staticmethod
    def get_history(limit: int = 100) -> list[Signal]:
        """获取信号历史"""
        return Signal.query.order_by(
            Signal.batch_version.desc(),
            Signal.priority.asc(),
            Signal.id.desc(),
        ).limit(limit).all()

    @staticmethod
    def get_instrument_history(
        instrument_id: int,
        account_id: Optional[int] = None,
        limit: int = 20,
    ) -> list[Signal]:
        """获取某个产品在指定账户下的历史版本"""
        query = Signal.query.filter_by(instrument_id=instrument_id)
        if account_id:
            query = query.filter_by(account_id=account_id)
        return query.order_by(
            Signal.batch_version.desc(),
            Signal.id.desc(),
        ).limit(limit).all()

    @staticmethod
    def generate_signals(signal_date: Optional[date] = None) -> list[Signal]:
        """
        为所有活跃产品生成信号

        这是信号生成的入口函数。
        先将当日旧信号标记为过期，然后针对每个活跃持仓生成新信号。

        Returns:
            本次生成的信号列表
        """
        if signal_date is None:
            signal_date = date.today()

        latest_batch_version = SignalService.get_latest_batch_version() or 0
        next_batch_version = latest_batch_version + 1
        batch_id = uuid4().hex

        # 一旦生成新版本，旧的待处理信号统一标记为过期
        Signal.query.filter(
            Signal.status == SignalStatus.PENDING.value,
        ).update({"status": SignalStatus.EXPIRED.value})
        db.session.commit()

        generated = []
        accounts = Account.query.filter_by(status="active").all()

        for account in accounts:
            # 获取该账户下所有活跃的策略绑定
            assignments = StrategyAssignment.query.filter_by(
                account_id=account.id,
                status="active",
            ).all()

            for assignment in assignments:
                instrument = db.session.get(Instrument, assignment.instrument_id)
                if not instrument or instrument.status != InstrumentStatus.ACTIVE.value:
                    continue

                try:
                    if account.account_type == AccountType.CORE.value:
                        signal = SignalService._generate_core_signal(
                            signal_date,
                            account,
                            instrument,
                            assignment,
                            batch_id=batch_id,
                            batch_version=next_batch_version,
                        )
                    else:
                        signal = SignalService._generate_tactical_signal(
                            signal_date,
                            account,
                            instrument,
                            assignment,
                            batch_id=batch_id,
                            batch_version=next_batch_version,
                        )

                    if signal:
                        db.session.add(signal)
                        generated.append(signal)

                except Exception as e:
                    # PRD 规则：若数据缺失，输出"无法评估"而非静默失败
                    logger.error("信号生成失败: %s: %s", instrument.symbol, e)
                    signal = Signal(
                        signal_date=signal_date,
                        account_id=account.id,
                        instrument_id=instrument.id,
                        signal_type=SignalType.OBSERVE.value,
                        priority=9,
                        reason_code="data_error",
                        explanation=f"无法评估：{str(e)}",
                        status=SignalStatus.PENDING.value,
                        batch_id=batch_id,
                        batch_version=next_batch_version,
                    )
                    db.session.add(signal)
                    generated.append(signal)

        db.session.commit()
        logger.info(
            "信号生成完成: 日期=%s, 版本=v%s, 数量=%s",
            signal_date, next_batch_version, len(generated),
        )

        from app.services.log_service import LogService
        LogService.log(
            log_type="signal",
            level="info",
            module="signal_service",
            message=f"生成 v{next_batch_version} 版本的 {len(generated)} 个信号",
            context={"date": str(signal_date), "batch_version": next_batch_version},
        )

        return generated

    @staticmethod
    def _generate_core_signal(
        signal_date: date,
        account: Account,
        instrument: Instrument,
        assignment: StrategyAssignment,
        batch_id: str,
        batch_version: int,
    ) -> Optional[Signal]:
        """
        核心账户信号逻辑（PRD §7.7.3 / §11.1）

        决策依据：
        1. 当前权重 vs 目标权重 → 是否需要再平衡
        2. 回撤区间 → 是否处于价值洼地
        3. 趋势状态 → MA 方向

        评分维度（PRD §7.8）：
        - 回撤分 40 分
        - 配置缺口分 20 分
        - 趋势分 20 分
        - 产品质量分 20 分（V1 默认满分）
        """
        # 获取最新行情
        latest_md = MarketData.query.filter_by(
            instrument_id=instrument.id
        ).order_by(MarketData.trade_date.desc()).first()

        if not latest_md:
            return Signal(
                signal_date=signal_date,
                account_id=account.id,
                instrument_id=instrument.id,
                signal_type=SignalType.OBSERVE.value,
                priority=9,
                reason_code="no_data",
                explanation="无行情数据，无法评估",
                status=SignalStatus.PENDING.value,
                batch_id=batch_id,
                batch_version=batch_version,
            )

        # 获取持仓
        position = Position.query.filter_by(
            account_id=account.id,
            instrument_id=instrument.id,
            position_status=PositionStatus.OPEN.value,
        ).first()

        current_weight = position.weight_in_account if position else 0
        target_lower = assignment.target_weight_lower or 0
        target_upper = assignment.target_weight_upper or 0

        # 使用共享评分引擎
        from app.services.signal_scoring import evaluate_core_signal

        price = latest_md.close or latest_md.nav or 0
        drawdown = latest_md.drawdown_60d or 0
        ma60 = latest_md.ma60 or price

        result = evaluate_core_signal(
            drawdown=drawdown,
            current_weight=current_weight,
            target_lower=target_lower,
            target_upper=target_upper,
            price=price,
            ma60=ma60,
        )

        signal_type = result["signal_type"]
        priority = result["priority"]
        total_score = result["score"]

        target_mid = (target_lower + target_upper) / 2 if (target_lower + target_upper) > 0 else 0

        # 生成人类可读的解释
        if signal_type == SignalType.REBALANCE.value:
            deviation = abs(current_weight - target_mid) / target_mid if target_mid > 0 else 0
            explanation = f"配置偏离 {deviation:.1%}，建议再平衡。当前权重={current_weight:.1%}，目标={target_mid:.1%}"
        elif signal_type == SignalType.ALLOW_BUY.value:
            explanation = f"评分 {total_score} 分，建议新增资金配置。回撤={drawdown:.1%}，权重={current_weight:.1%}"
        elif signal_type == SignalType.HOLD.value:
            explanation = f"评分 {total_score} 分，建议持有观察。回撤={drawdown:.1%}，权重={current_weight:.1%}"
        else:
            explanation = f"评分 {total_score} 分，建议暂停新增。回撤={drawdown:.1%}，权重={current_weight:.1%}"

        return Signal(
            signal_date=signal_date,
            account_id=account.id,
            instrument_id=instrument.id,
            signal_type=signal_type,
            priority=priority,
            reason_code=result["reason_code"],
            explanation=explanation,
            score=total_score,
            status=SignalStatus.PENDING.value,
            batch_id=batch_id,
            batch_version=batch_version,
        )

    @staticmethod
    def _generate_tactical_signal(
        signal_date: date,
        account: Account,
        instrument: Instrument,
        assignment: StrategyAssignment,
        batch_id: str,
        batch_version: int,
    ) -> Optional[Signal]:
        """
        战术账户信号逻辑（PRD §7.7.4 / §11.2）

        决策依据：
        1. MA20 / MA60 趋势确认
        2. 买入后收益率 → 分层止损 / 分层止盈
        3. 盈利保护与趋势破坏退出
        """
        latest_md = MarketData.query.filter_by(
            instrument_id=instrument.id
        ).order_by(MarketData.trade_date.desc()).first()

        if not latest_md:
            return Signal(
                signal_date=signal_date,
                account_id=account.id,
                instrument_id=instrument.id,
                signal_type=SignalType.OBSERVE.value,
                priority=9,
                reason_code="no_data",
                explanation="无行情数据，无法评估",
                status=SignalStatus.PENDING.value,
                batch_id=batch_id,
                batch_version=batch_version,
            )

        price = latest_md.close or latest_md.nav or 0
        ma20 = latest_md.ma20 or 0
        ma60 = latest_md.ma60 or 0
        rs20d = latest_md.relative_strength_20d or 0

        # 获取持仓
        position = Position.query.filter_by(
            account_id=account.id,
            instrument_id=instrument.id,
            position_status=PositionStatus.OPEN.value,
        ).first()

        # 读取策略参数（支持产品级覆盖）
        config = assignment.get_effective_config()

        stop_loss_warn_pct = config.get("stop_loss_warn_pct", -0.05)
        stop_loss_warn_reduce_ratio = config.get("stop_loss_warn_reduce_ratio", 0.25)
        stop_loss_pct = config.get("stop_loss_pct", -0.08)
        stop_loss_reduce_ratio = config.get("stop_loss_reduce_ratio", 0.50)
        stop_loss_clear_pct = config.get("stop_loss_clear_pct", -0.10)
        early_exit_pct = config.get("early_exit_pct", -0.06)
        profit_protect_trigger_pct = config.get("profit_protect_trigger_pct", 0.09)
        profit_protect_reduce_ratio = config.get("profit_protect_reduce_ratio", 0.20)
        take_profit_pct_1 = config.get("take_profit_pct_1", 0.12)
        take_profit_pct_2 = config.get("take_profit_pct_2", 0.18)
        take_profit_pct_3 = config.get("take_profit_pct_3", 0.25)
        take_profit_sell_ratio_1 = config.get("take_profit_sell_ratio_1", 0.20)
        take_profit_sell_ratio_2 = config.get("take_profit_sell_ratio_2", 0.30)
        take_profit_sell_ratio_3 = config.get("take_profit_sell_ratio_3", 0.30)
        add_confirm_pct = config.get("add_confirm_pct", 0.05)
        add_position_pct = config.get("add_position_pct", 0.30)
        entry_rs_threshold = config.get("entry_rs_threshold", 0.00)

        price_below_ma20 = price > 0 and ma20 > 0 and price < ma20
        trend_broken = price_below_ma20 and ma20 > 0 and ma60 > 0 and ma20 < ma60

        if position and position.quantity > 0:
            # === 已持仓 ===
            pnl_pct = position.unrealized_pnl_pct or 0

            # 止损判断：预警减仓 -> 半仓防守 -> 强制清仓
            if pnl_pct <= stop_loss_clear_pct:
                return Signal(
                    signal_date=signal_date,
                    account_id=account.id,
                    instrument_id=instrument.id,
                    signal_type=SignalType.STOP_LOSS.value,
                    priority=1,
                    reason_code="tactical_stop_loss",
                    explanation=f"强制止损：亏损 {pnl_pct:.1%}，跌破 {stop_loss_clear_pct:.0%} 阈值，建议清仓",
                    risk_flag="high",
                    status=SignalStatus.PENDING.value,
                    batch_id=batch_id,
                    batch_version=batch_version,
                )
            elif pnl_pct <= early_exit_pct and trend_broken:
                return Signal(
                    signal_date=signal_date,
                    account_id=account.id,
                    instrument_id=instrument.id,
                    signal_type=SignalType.STOP_LOSS.value,
                    priority=1,
                    reason_code="tactical_early_exit",
                    explanation=f"抢跑止损：亏损 {pnl_pct:.1%}，且 price < MA20 < MA60，趋势结构破坏，建议提前清仓",
                    risk_flag="high",
                    status=SignalStatus.PENDING.value,
                    batch_id=batch_id,
                    batch_version=batch_version,
                )
            elif pnl_pct <= stop_loss_pct:
                return Signal(
                    signal_date=signal_date,
                    account_id=account.id,
                    instrument_id=instrument.id,
                    signal_type=SignalType.REDUCE.value,
                    priority=2,
                    reason_code="tactical_reduce_major",
                    explanation=(
                        f"二级止损：亏损 {pnl_pct:.1%}，跌破 {stop_loss_pct:.0%} 阈值，"
                        f"建议减仓 {stop_loss_reduce_ratio:.0%}"
                    ),
                    risk_flag="medium",
                    status=SignalStatus.PENDING.value,
                    batch_id=batch_id,
                    batch_version=batch_version,
                )
            elif pnl_pct <= stop_loss_warn_pct and price_below_ma20:
                return Signal(
                    signal_date=signal_date,
                    account_id=account.id,
                    instrument_id=instrument.id,
                    signal_type=SignalType.REDUCE.value,
                    priority=3,
                    reason_code="tactical_reduce_warn",
                    explanation=(
                        f"一级止损预警：亏损 {pnl_pct:.1%}，且价格跌破 MA20，"
                        f"建议先减仓 {stop_loss_warn_reduce_ratio:.0%}"
                    ),
                    risk_flag="medium",
                    status=SignalStatus.PENDING.value,
                    batch_id=batch_id,
                    batch_version=batch_version,
                )

            # 止盈：分三级兑现利润
            if pnl_pct >= take_profit_pct_3:
                return Signal(
                    signal_date=signal_date,
                    account_id=account.id,
                    instrument_id=instrument.id,
                    signal_type=SignalType.TAKE_PROFIT.value,
                    priority=2,
                    reason_code="tactical_take_profit_3",
                    explanation=(
                        f"三级止盈：盈利 {pnl_pct:.1%}，超过 {take_profit_pct_3:.0%}，"
                        f"建议止盈 {take_profit_sell_ratio_3:.0%}"
                    ),
                    status=SignalStatus.PENDING.value,
                    batch_id=batch_id,
                    batch_version=batch_version,
                )
            elif pnl_pct >= take_profit_pct_2:
                return Signal(
                    signal_date=signal_date,
                    account_id=account.id,
                    instrument_id=instrument.id,
                    signal_type=SignalType.TAKE_PROFIT.value,
                    priority=3,
                    reason_code="tactical_take_profit_2",
                    explanation=(
                        f"二级止盈：盈利 {pnl_pct:.1%}，超过 {take_profit_pct_2:.0%}，"
                        f"建议止盈 {take_profit_sell_ratio_2:.0%}"
                    ),
                    status=SignalStatus.PENDING.value,
                    batch_id=batch_id,
                    batch_version=batch_version,
                )
            elif pnl_pct >= take_profit_pct_1:
                return Signal(
                    signal_date=signal_date,
                    account_id=account.id,
                    instrument_id=instrument.id,
                    signal_type=SignalType.TAKE_PROFIT.value,
                    priority=4,
                    reason_code="tactical_take_profit_1",
                    explanation=(
                        f"一级止盈：盈利 {pnl_pct:.1%}，超过 {take_profit_pct_1:.0%}，"
                        f"建议止盈 {take_profit_sell_ratio_1:.0%}"
                    ),
                    status=SignalStatus.PENDING.value,
                    batch_id=batch_id,
                    batch_version=batch_version,
                )

            # 盈利保护：盈利已形成，但趋势转弱时先锁部分利润
            if pnl_pct >= profit_protect_trigger_pct and price_below_ma20:
                return Signal(
                    signal_date=signal_date,
                    account_id=account.id,
                    instrument_id=instrument.id,
                    signal_type=SignalType.REDUCE.value,
                    priority=4,
                    reason_code="tactical_profit_protect",
                    explanation=(
                        f"盈利保护：当前盈利 {pnl_pct:.1%}，但价格跌破 MA20，"
                        f"建议减仓 {profit_protect_reduce_ratio:.0%} 锁定利润"
                    ),
                    status=SignalStatus.PENDING.value,
                    batch_id=batch_id,
                    batch_version=batch_version,
                )

            # 确认加仓：只对盈利单、且趋势仍然完好的仓位加仓
            if add_confirm_pct <= pnl_pct < take_profit_pct_1:
                if price > ma20 > 0 and (ma60 <= 0 or ma20 >= ma60):
                    return Signal(
                        signal_date=signal_date,
                        account_id=account.id,
                        instrument_id=instrument.id,
                        signal_type=SignalType.ALLOW_ADD.value,
                        priority=5,
                        reason_code="tactical_confirm_add",
                        explanation=(
                            f"确认加仓：盈利 {pnl_pct:.1%}，价格维持在 MA20 上方，"
                            f"可追加约 {add_position_pct:.0%} 计划仓位"
                        ),
                        status=SignalStatus.PENDING.value,
                        batch_id=batch_id,
                        batch_version=batch_version,
                    )

            # 默认持有
            return Signal(
                signal_date=signal_date,
                account_id=account.id,
                instrument_id=instrument.id,
                signal_type=SignalType.HOLD.value,
                priority=6,
                reason_code="tactical_hold",
                explanation=f"持有观察：盈亏 {pnl_pct:.1%}，趋势未触发新的止损或止盈动作",
                status=SignalStatus.PENDING.value,
                batch_id=batch_id,
                batch_version=batch_version,
            )

        else:
            # === 未持仓 ===
            # 趋势确认买入：站上 MA20，且 MA20 > MA60，并要求相对强弱转正
            if price > 0 and ma20 > 0 and price > ma20:
                ma20_up = ma20 > ma60 if ma60 > 0 else True
                if ma20_up and rs20d >= entry_rs_threshold:
                    return Signal(
                        signal_date=signal_date,
                        account_id=account.id,
                        instrument_id=instrument.id,
                        signal_type=SignalType.ALLOW_BUY.value,
                        priority=3,
                        reason_code="tactical_trend_buy",
                        explanation=(
                            f"趋势确认：价格 {price:.3f} > MA20 {ma20:.3f}，MA20 上穿并走强，"
                            f"20日相对强弱 {rs20d:.1%}，可试探建立底仓"
                        ),
                        status=SignalStatus.PENDING.value,
                        batch_id=batch_id,
                        batch_version=batch_version,
                    )

            # 默认观察
            return Signal(
                signal_date=signal_date,
                account_id=account.id,
                instrument_id=instrument.id,
                signal_type=SignalType.OBSERVE.value,
                priority=8,
                reason_code="tactical_observe",
                explanation=f"观察等待：价格 {price:.3f}，MA20 {ma20:.3f}，MA60 {ma60:.3f}，趋势未确认",
                status=SignalStatus.PENDING.value,
                batch_id=batch_id,
                batch_version=batch_version,
            )

    @staticmethod
    def get_rebalance_guidance(
        signal: "Signal",
        position: Optional["Position"],
        latest_md: Optional["MarketData"],
        assignment: Optional["StrategyAssignment"],
    ) -> dict:
        """
        生成可执行的调仓建议。

        委托给 RebalanceGuidanceService 处理，此处保留方法签名以兼容现有调用方。
        """
        from app.services.rebalance_guidance_service import RebalanceGuidanceService
        return RebalanceGuidanceService.get_rebalance_guidance(
            signal=signal,
            position=position,
            latest_md=latest_md,
            assignment=assignment,
        )

