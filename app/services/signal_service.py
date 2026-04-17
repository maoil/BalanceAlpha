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
                    logger.error(f"信号生成失败: {instrument.symbol}: {e}")
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
            f"信号生成完成: 日期={signal_date}, 版本=v{next_batch_version}, 数量={len(generated)}"
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
        target_mid = (target_lower + target_upper) / 2 if (target_lower + target_upper) > 0 else 0

        # ---- 计算评分 ----
        # 回撤分（40分）：回撤越深，分越高（假设是买入机会）
        drawdown = latest_md.drawdown_60d or 0
        if drawdown <= -0.20:
            drawdown_score = 40
        elif drawdown <= -0.10:
            drawdown_score = 30
        elif drawdown <= -0.05:
            drawdown_score = 20
        else:
            drawdown_score = 10

        # 配置缺口分（20分）：低于目标权重越多，分越高
        if target_mid > 0 and current_weight < target_lower:
            gap_ratio = (target_mid - current_weight) / target_mid
            config_gap_score = min(20, int(gap_ratio * 40))
        elif target_mid > 0 and current_weight > target_upper:
            config_gap_score = 0  # 超配不加分
        else:
            config_gap_score = 10  # 正常范围

        # 趋势分（20分）：价格在MA60上方为正，下方为负
        price = latest_md.close or latest_md.nav or 0
        ma60 = latest_md.ma60 or price
        if price > 0 and ma60 > 0:
            if price > ma60:
                trend_score = 15
            elif price > ma60 * 0.95:
                trend_score = 10
            else:
                trend_score = 5
        else:
            trend_score = 10

        # 产品质量分（20分）：V1 默认给 15 分
        quality_score = 15

        total_score = drawdown_score + config_gap_score + trend_score + quality_score

        # ---- 生成信号 ----
        # PRD §7.8.4 评分分级
        if total_score >= 70:
            signal_type = SignalType.ALLOW_BUY.value
            explanation = f"评分 {total_score} 分，建议新增资金配置。回撤={drawdown:.1%}，权重={current_weight:.1%}"
            priority = 2
        elif total_score >= 55:
            signal_type = SignalType.HOLD.value
            explanation = f"评分 {total_score} 分，建议持有观察。回撤={drawdown:.1%}，权重={current_weight:.1%}"
            priority = 5
        else:
            signal_type = SignalType.SUSPEND_ADD.value
            explanation = f"评分 {total_score} 分，建议暂停新增。回撤={drawdown:.1%}，权重={current_weight:.1%}"
            priority = 7

        # 再平衡检查（PRD §7.9）：偏离超过 20%
        if target_mid > 0 and current_weight > 0:
            deviation = abs(current_weight - target_mid) / target_mid
            if deviation > 0.20:
                signal_type = SignalType.REBALANCE.value
                explanation = f"配置偏离 {deviation:.1%}，建议再平衡。当前权重={current_weight:.1%}，目标={target_mid:.1%}"
                priority = 1

        return Signal(
            signal_date=signal_date,
            account_id=account.id,
            instrument_id=instrument.id,
            signal_type=signal_type,
            priority=priority,
            reason_code=f"core_score_{total_score}",
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
        template = db.session.get(StrategyTemplate, assignment.template_id)
        config = json.loads(template.config_json) if template else {}
        custom_config = json.loads(assignment.custom_config_json) if assignment.custom_config_json else {}
        config.update(custom_config)

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

        返回值会尽量落到“买/卖多少金额、对应多少份额、分几步做、
        资金从哪里来、完成后大致回到什么仓位”这个粒度，供详情页和 API 直接使用。

        Args:
            signal: 当前信号
            position: 当前持仓（可为空）
            latest_md: 最新行情数据（可为空）
            assignment: 策略绑定（可为空）

        Returns:
            dict: 调仓建议结构
        """
        instrument = signal.instrument
        account = signal.account

        def _round_amount(value: float) -> float:
            return round(value or 0, 2)

        def _round_qty(value: float) -> float:
            return round(value or 0, 4)

        def _safe_div(numerator: float, denominator: float) -> float:
            if not denominator:
                return 0.0
            return numerator / denominator

        def _parse_config() -> dict:
            if not assignment:
                return {}

            template = db.session.get(StrategyTemplate, assignment.template_id)
            config = json.loads(template.config_json) if template and template.config_json else {}
            custom_config = (
                json.loads(assignment.custom_config_json)
                if assignment.custom_config_json else {}
            )
            config.update(custom_config)
            return config

        def _get_step_ratios(total_amount: float, is_tactical: bool) -> list[float]:
            if total_amount <= 0:
                return []
            if is_tactical:
                return [1.0]
            if total_amount >= max(account_total_value * 0.03, 1000):
                return [0.6, 0.4]
            return [1.0]

        def _build_split_steps(
            action: str,
            total_amount: float,
            total_quantity: float,
            description_prefix: str,
            suggested_timing: str,
            base_weight: float,
            base_value: float,
            funding_source: str = "",
            destination: str = "",
            condition: str = "",
            rationale: str = "",
            is_tactical: bool = False,
        ) -> list[dict]:
            ratios = _get_step_ratios(total_amount, is_tactical=is_tactical)
            steps = []
            cumulative_amount = 0.0
            cumulative_quantity = 0.0

            for idx, ratio in enumerate(ratios, start=1):
                if idx == len(ratios):
                    amount = total_amount - cumulative_amount
                    quantity = total_quantity - cumulative_quantity
                else:
                    amount = _round_amount(total_amount * ratio)
                    quantity = _round_qty(total_quantity * ratio)

                cumulative_amount += amount
                cumulative_quantity += quantity

                value_after = (
                    base_value + cumulative_amount
                    if action == "buy"
                    else max(0.0, base_value - cumulative_amount)
                )
                weight_after = _safe_div(value_after, account_total_value)

                if len(ratios) == 1:
                    description = description_prefix
                else:
                    description = f"{description_prefix}（第 {idx}/{len(ratios)} 步）"

                steps.append({
                    "step": len(steps) + 1,
                    "action": action,
                    "ratio": ratio,
                    "description": description,
                    "suggested_timing": suggested_timing if idx == 1 else "确认前一笔成交后再执行",
                    "amount": _round_amount(amount),
                    "quantity": _round_qty(quantity),
                    "price_reference": _round_amount(latest_price),
                    "target_value_after": _round_amount(value_after),
                    "target_weight_after": weight_after,
                    "funding_source": funding_source,
                    "destination": destination,
                    "condition": condition,
                    "rationale": rationale,
                })
            return steps

        def _build_info_step(
            description: str,
            suggested_timing: str = "",
            condition: str = "",
            rationale: str = "",
        ) -> dict:
            return {
                "step": 0,
                "action": "",
                "ratio": 0,
                "description": description,
                "suggested_timing": suggested_timing,
                "amount": 0.0,
                "quantity": 0.0,
                "price_reference": _round_amount(latest_price),
                "target_value_after": _round_amount(current_value),
                "target_weight_after": current_weight,
                "funding_source": "",
                "destination": "",
                "condition": condition,
                "rationale": rationale,
            }

        account_positions = Position.query.filter_by(
            account_id=signal.account_id,
            position_status=PositionStatus.OPEN.value,
        ).all()
        account_total_value = sum(p.market_value or 0 for p in account_positions)
        cash_positions = [
            pos for pos in account_positions
            if pos.instrument and pos.instrument.instrument_type == "cash"
        ]
        cash_value = sum(pos.market_value or 0 for pos in cash_positions)
        cash_weight = _safe_div(cash_value, account_total_value)

        assignment_map = {
            item.instrument_id: item
            for item in StrategyAssignment.query.filter_by(
                account_id=signal.account_id,
                status="active",
            ).all()
        }
        config = _parse_config()

        # 当前状态
        current_weight = position.weight_in_account if position else 0
        current_quantity = position.quantity if position else 0
        current_value = position.market_value if position else 0
        latest_price = position.market_price if position else 0
        if latest_md:
            latest_price = latest_md.close or latest_md.nav or latest_price or 0

        # 目标状态
        target_lower = assignment.target_weight_lower if assignment else 0
        target_upper = assignment.target_weight_upper if assignment else 0
        target_mid = (target_lower + target_upper) / 2 if (target_lower + target_upper) > 0 else 0
        target_value_lower = account_total_value * target_lower if account_total_value > 0 else 0
        target_value_upper = account_total_value * target_upper if account_total_value > 0 else 0
        target_value_mid = account_total_value * target_mid if account_total_value > 0 else 0
        gap_value_to_mid = target_value_mid - current_value
        gap_quantity_to_mid = _safe_div(gap_value_to_mid, latest_price)
        current_deviation = current_weight - target_mid if target_mid > 0 else 0

        trade_mode = instrument.trade_mode or ""
        risk_warnings: list[str] = []
        rebalance_steps: list[dict] = []

        if not account_total_value:
            risk_warnings.append("账户当前总市值为 0，无法据此计算目标金额，请先刷新持仓或补录现金仓。")
        if not latest_price:
            risk_warnings.append("缺少最新价格，无法准确换算建议份额。")
        if latest_md and signal.signal_date and latest_md.trade_date and latest_md.trade_date < signal.signal_date:
            risk_warnings.append(
                f"价格日期停留在 {latest_md.trade_date}，请先更新行情再执行调仓。"
            )
        if trade_mode == "exchange_traded":
            risk_warnings.append("场内产品请按交易所最小交易单位手动修正份额，系统当前按连续份额估算。")
        if assignment is None:
            risk_warnings.append("当前产品没有有效策略绑定，建议先检查策略模板和目标仓位区间。")
        if account.account_type == AccountType.CORE.value and not cash_positions:
            risk_warnings.append("核心账户未单独记录现金/货基仓位，买入建议默认按当前持仓总市值估算。")
        if abs(current_deviation) >= 0.05:
            risk_warnings.append(
                f"当前仓位偏离中位目标 {current_deviation:+.2%}，建议优先处理该偏离。"
            )

        overweight_sources = []
        underweight_targets = []
        for pos in account_positions:
            if pos.instrument_id == instrument.id:
                continue
            if not pos.instrument or pos.instrument.instrument_type == "cash":
                continue

            other_assignment = assignment_map.get(pos.instrument_id)
            if not other_assignment or not other_assignment.allow_rebalance:
                continue

            other_lower = other_assignment.target_weight_lower or 0
            other_upper = other_assignment.target_weight_upper or 0
            other_mid = (
                (other_lower + other_upper) / 2
                if (other_lower + other_upper) > 0 else 0
            )
            if other_mid <= 0:
                continue

            other_value_mid = account_total_value * other_mid
            if (pos.weight_in_account or 0) > other_upper:
                overweight_sources.append({
                    "name": pos.instrument.name,
                    "amount": max(0.0, (pos.market_value or 0) - other_value_mid),
                })
            elif (pos.weight_in_account or 0) < other_lower:
                underweight_targets.append({
                    "name": pos.instrument.name,
                    "amount": max(0.0, other_value_mid - (pos.market_value or 0)),
                })

        overweight_sources.sort(key=lambda item: item["amount"], reverse=True)
        underweight_targets.sort(key=lambda item: item["amount"], reverse=True)

        cash_buffer_lower = config.get("cash_buffer_lower", 0.0)
        cash_buffer_upper = config.get("cash_buffer_upper", 0.0)
        is_tactical = account.account_type == AccountType.TACTICAL.value

        def _buy_funding_source() -> str:
            if cash_value > 0:
                return "优先使用现金/货基仓位。"
            if overweight_sources:
                names = "、".join(item["name"] for item in overweight_sources[:2])
                return f"可先从超配品种 {names} 释放资金。"
            return "当前未识别可用现金仓位，需结合新增资金执行。"

        def _sell_destination() -> str:
            if is_tactical:
                return "回流到现金/货基，等待下一次有效信号。"
            if underweight_targets:
                names = "、".join(item["name"] for item in underweight_targets[:2])
                return f"优先回流至现金/货基，再补低配品种 {names}。"
            return "优先回流到现金/货基。"

        if latest_price > 0 and account_total_value > 0:
            signal_type = signal.signal_type

            if is_tactical:
                planned_max_weight = target_upper if target_upper > 0 else max(target_mid, 0.30)
                initial_position_pct = config.get("initial_position_pct", 0.40)
                add_position_pct = config.get("add_position_pct", 0.30)
                stop_loss_warn_reduce_ratio = config.get("stop_loss_warn_reduce_ratio", 0.25)
                stop_loss_reduce_ratio = config.get("stop_loss_reduce_ratio", 0.50)
                profit_protect_reduce_ratio = config.get("profit_protect_reduce_ratio", 0.20)
                take_profit_sell_ratio_1 = config.get("take_profit_sell_ratio_1", 0.20)
                take_profit_sell_ratio_2 = config.get("take_profit_sell_ratio_2", 0.30)
                take_profit_sell_ratio_3 = config.get("take_profit_sell_ratio_3", 0.30)

                if signal_type == SignalType.ALLOW_BUY.value:
                    buy_weight = planned_max_weight * initial_position_pct
                    buy_value = min(account_total_value * buy_weight, account_total_value)
                    buy_qty = _safe_div(buy_value, latest_price)
                    rebalance_steps.extend(
                        _build_split_steps(
                            action="buy",
                            total_amount=buy_value,
                            total_quantity=buy_qty,
                            description_prefix="按战术底仓计划建立首笔仓位",
                            suggested_timing="优先在 14:50 以后、趋势未走坏时执行",
                            base_weight=current_weight,
                            base_value=current_value,
                            funding_source=_buy_funding_source(),
                            condition="仅在价格仍位于 MA20 上方、且 MA20 不弱于 MA60 时执行。",
                            rationale="首笔底仓只占计划仓位的一部分，先验证趋势，再决定是否扩仓。",
                            is_tactical=True,
                        )
                    )
                    rebalance_steps.append(
                        _build_info_step(
                            description="若后续浮盈达到加仓阈值，再追加右侧仓位",
                            suggested_timing="后续信号出现时再执行",
                            condition="浮盈 >= 5%，且价格继续位于 MA20 上方。",
                            rationale="战术账户只对盈利单加仓，避免逆势摊低成本。",
                        )
                    )
                elif signal_type == SignalType.ALLOW_ADD.value:
                    add_weight = min(planned_max_weight, current_weight + planned_max_weight * add_position_pct) - current_weight
                    add_weight = max(0.0, add_weight)
                    add_value = account_total_value * add_weight
                    add_qty = _safe_div(add_value, latest_price)
                    rebalance_steps.extend(
                        _build_split_steps(
                            action="buy",
                            total_amount=add_value,
                            total_quantity=add_qty,
                            description_prefix="按右侧确认信号追加仓位",
                            suggested_timing="优先在收盘前完成，避免盘中追高",
                            base_weight=current_weight,
                            base_value=current_value,
                            funding_source=_buy_funding_source(),
                            condition="若价格重新跌破 MA20，则放弃本次加仓。",
                            rationale="只在已有盈利和趋势完好的情况下增加风险敞口。",
                            is_tactical=True,
                        )
                    )
                elif signal_type == SignalType.REDUCE.value:
                    reduce_ratio = stop_loss_warn_reduce_ratio
                    description = "先减仓控制回撤"
                    rationale = "优先降低风险敞口，保留观察仓位。"
                    if signal.reason_code == "tactical_reduce_major":
                        reduce_ratio = stop_loss_reduce_ratio
                        description = "将仓位降到防守状态"
                        rationale = "跌破二级止损阈值后，不再维持进攻仓位。"
                    elif signal.reason_code == "tactical_profit_protect":
                        reduce_ratio = profit_protect_reduce_ratio
                        description = "先锁定一部分利润"
                        rationale = "盈利单转弱时，优先兑现部分收益，避免盈利回吐。"

                    sell_value = current_value * reduce_ratio
                    sell_qty = current_quantity * reduce_ratio
                    rebalance_steps.extend(
                        _build_split_steps(
                            action="sell",
                            total_amount=sell_value,
                            total_quantity=sell_qty,
                            description_prefix=description,
                            suggested_timing="下一个交易窗口尽快执行",
                            base_weight=current_weight,
                            base_value=current_value,
                            destination=_sell_destination(),
                            condition="执行后继续观察 MA20/MA60 结构，若再次恶化再处理剩余仓位。",
                            rationale=rationale,
                            is_tactical=True,
                        )
                    )
                elif signal_type == SignalType.TAKE_PROFIT.value:
                    take_ratio = take_profit_sell_ratio_1
                    description = "兑现第一档利润"
                    if signal.reason_code == "tactical_take_profit_2":
                        take_ratio = take_profit_sell_ratio_2
                        description = "兑现第二档利润"
                    elif signal.reason_code == "tactical_take_profit_3":
                        take_ratio = take_profit_sell_ratio_3
                        description = "兑现第三档利润"

                    sell_value = current_value * take_ratio
                    sell_qty = current_quantity * take_ratio
                    rebalance_steps.extend(
                        _build_split_steps(
                            action="sell",
                            total_amount=sell_value,
                            total_quantity=sell_qty,
                            description_prefix=description,
                            suggested_timing="优先在强势日分批成交，避免一次性砸出尾仓",
                            base_weight=current_weight,
                            base_value=current_value,
                            destination=_sell_destination(),
                            condition="剩余仓位若继续站稳 MA20，可继续持有；跌破 MA20 时转入利润保护。",
                            rationale="分层止盈后保留尾仓，兼顾兑现收益和趋势延续。",
                            is_tactical=True,
                        )
                    )
                elif signal_type == SignalType.STOP_LOSS.value:
                    rebalance_steps.extend(
                        _build_split_steps(
                            action="sell",
                            total_amount=current_value,
                            total_quantity=current_quantity,
                            description_prefix="执行清仓止损",
                            suggested_timing="下一个可交易窗口立即执行",
                            base_weight=current_weight,
                            base_value=current_value,
                            destination=_sell_destination(),
                            condition="执行后至少等待新的趋势确认信号，不做情绪化回补。",
                            rationale="止损信号的核心是切断亏损，不与趋势对抗。",
                            is_tactical=True,
                        )
                    )
                else:
                    if current_weight > 0:
                        rebalance_steps.append(
                            _build_info_step(
                                description="当前无需主动调仓，继续按战术规则跟踪",
                                suggested_timing="日/周度复核",
                                condition="重点跟踪 MA20、MA60 与持仓盈亏分层阈值。",
                                rationale="尚未触发新的加仓、减仓、止盈或止损动作。",
                            )
                        )
            else:
                if signal.signal_type in (SignalType.ALLOW_BUY.value, SignalType.REBALANCE.value):
                    if gap_value_to_mid > 0 and (
                        current_weight < target_lower or signal.signal_type == SignalType.ALLOW_BUY.value
                    ):
                        rebalance_steps.extend(
                            _build_split_steps(
                                action="buy",
                                total_amount=gap_value_to_mid,
                                total_quantity=gap_quantity_to_mid,
                                description_prefix="补仓至目标中位仓位附近",
                                suggested_timing="本周内分批完成，优先用新增资金修正低配",
                                base_weight=current_weight,
                                base_value=current_value,
                                funding_source=_buy_funding_source(),
                                condition="若补仓后账户现金仓低于下限，暂停继续加仓。",
                                rationale="核心账户以区间回归为主，不追求一次性打满。",
                                is_tactical=False,
                            )
                        )
                    elif gap_value_to_mid < 0 and current_weight > target_upper:
                        rebalance_steps.extend(
                            _build_split_steps(
                                action="sell",
                                total_amount=abs(gap_value_to_mid),
                                total_quantity=abs(gap_quantity_to_mid),
                                description_prefix="减仓回到目标中位仓位附近",
                                suggested_timing="本周内完成，优先处理超配仓位",
                                base_weight=current_weight,
                                base_value=current_value,
                                destination=_sell_destination(),
                                condition="完成后复核账户总仓位和现金缓冲区间。",
                                rationale="核心账户超配时优先做回归，避免单一资产主导组合。",
                                is_tactical=False,
                            )
                        )
                elif signal.signal_type == SignalType.HOLD.value:
                    rebalance_steps.append(
                        _build_info_step(
                            description="当前仓位基本处于目标区间内，无需主动调仓",
                            suggested_timing="按月度例行检查即可",
                            condition="若权重再次越过上下限，再启动回归动作。",
                            rationale="核心账户以区间管理为主，区间内默认保持不动。",
                        )
                    )
                elif signal.signal_type == SignalType.SUSPEND_ADD.value:
                    rebalance_steps.append(
                        _build_info_step(
                            description="暂停新增资金配置，等待评分和趋势修复",
                            suggested_timing="下一个月度检查窗口再评估",
                            condition="评分重新回到允许买入区间后再恢复新增资金。",
                            rationale="当前不是扩仓窗口，先保留现金缓冲更稳妥。",
                        )
                    )

        if cash_buffer_lower > 0 and cash_weight < cash_buffer_lower and signal.signal_type in (
            SignalType.ALLOW_BUY.value,
            SignalType.ALLOW_ADD.value,
        ):
            risk_warnings.append(
                f"当前现金/货基占比约 {cash_weight:.2%}，低于模板下限 {cash_buffer_lower:.0%}，执行买入前请先确认可用资金。"
            )
        if cash_buffer_upper > 0 and cash_weight > cash_buffer_upper and signal.signal_type in (
            SignalType.HOLD.value,
            SignalType.SUSPEND_ADD.value,
        ):
            risk_warnings.append(
                f"当前现金/货基占比约 {cash_weight:.2%}，高于模板上限 {cash_buffer_upper:.0%}，可关注后续低配资产补仓机会。"
            )
        if signal.signal_type in (
            SignalType.REDUCE.value,
            SignalType.STOP_LOSS.value,
            SignalType.TAKE_PROFIT.value,
        ) and position and (position.unrealized_pnl_pct or 0) < 0:
            risk_warnings.append("本次卖出会锁定部分亏损，请结合成交滑点和执行纪律一起考虑。")

        notes = "已生成可执行调仓建议。"
        if rebalance_steps:
            notes = "建议按顺序执行每一步，完成后重新刷新持仓与信号，再决定是否继续下一步。"
        elif signal.signal_type in (SignalType.HOLD.value, SignalType.OBSERVE.value, SignalType.SUSPEND_ADD.value):
            notes = "当前以观察为主，暂不需要真实买卖动作。"

        return {
            "signal_summary": {
                "signal_type": signal.signal_type,
                "explanation": signal.explanation,
                "score": signal.score,
                "priority": signal.priority,
                "reason_code": signal.reason_code,
            },
            "current_status": {
                "instrument_name": instrument.name,
                "instrument_symbol": instrument.symbol,
                "current_weight": current_weight,
                "current_quantity": current_quantity,
                "current_value": current_value,
                "latest_price": latest_price,
                "price_date": str(latest_md.trade_date) if latest_md else None,
                "avg_cost": position.avg_cost if position else 0,
                "unrealized_pnl_pct": position.unrealized_pnl_pct if position else 0,
                "account_total_value": account_total_value,
                "cash_value": cash_value,
                "cash_weight": cash_weight,
                "current_deviation": current_deviation,
            },
            "target_status": {
                "target_weight_lower": target_lower,
                "target_weight_upper": target_upper,
                "target_weight_mid": target_mid,
                "target_value_lower": _round_amount(target_value_lower),
                "target_value_upper": _round_amount(target_value_upper),
                "target_value_mid": _round_amount(target_value_mid),
                "gap_value_to_mid": _round_amount(gap_value_to_mid),
                "gap_quantity_to_mid": _round_qty(gap_quantity_to_mid),
                "cash_buffer_lower": cash_buffer_lower,
                "cash_buffer_upper": cash_buffer_upper,
            },
            "rebalance_steps": rebalance_steps,
            "risk_warnings": risk_warnings,
            "notes": notes,
        }
