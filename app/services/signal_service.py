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
        2. 买入后收益率 → 止损/止盈
        3. 持仓高点回撤
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

        stop_loss_pct = config.get("stop_loss_pct", -0.08)
        take_profit_pct_1 = config.get("take_profit_pct_1", 0.15)
        add_confirm_pct = config.get("add_confirm_pct", 0.04)

        if position and position.quantity > 0:
            # === 已持仓 ===
            pnl_pct = position.unrealized_pnl_pct or 0

            # 止损判断（PRD §11.3：回撤 8% 先减半，10% 清仓）
            if pnl_pct <= -0.10:
                return Signal(
                    signal_date=signal_date,
                    account_id=account.id,
                    instrument_id=instrument.id,
                    signal_type=SignalType.STOP_LOSS.value,
                    priority=1,
                    reason_code="tactical_stop_loss",
                    explanation=f"⚠️ 止损！亏损 {pnl_pct:.1%}，超过 -10% 阈值，建议清仓",
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
                    reason_code="tactical_reduce",
                    explanation=f"预警减仓：亏损 {pnl_pct:.1%}，接近止损线 {stop_loss_pct:.0%}，建议减半仓",
                    risk_flag="medium",
                    status=SignalStatus.PENDING.value,
                    batch_id=batch_id,
                    batch_version=batch_version,
                )

            # 止盈（PRD §11.3：15% 止盈1/3，25% 再止盈1/3）
            if pnl_pct >= 0.25:
                return Signal(
                    signal_date=signal_date,
                    account_id=account.id,
                    instrument_id=instrument.id,
                    signal_type=SignalType.TAKE_PROFIT.value,
                    priority=2,
                    reason_code="tactical_take_profit_2",
                    explanation=f"二级止盈：盈利 {pnl_pct:.1%}，超 25%，建议再止盈 1/3",
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
                    priority=3,
                    reason_code="tactical_take_profit_1",
                    explanation=f"一级止盈：盈利 {pnl_pct:.1%}，超 15%，建议止盈 1/3",
                    status=SignalStatus.PENDING.value,
                    batch_id=batch_id,
                    batch_version=batch_version,
                )

            # 确认加仓（PRD §11.3：盈利 4-5% 后可加满计划仓）
            if add_confirm_pct <= pnl_pct < take_profit_pct_1:
                if price > ma20 > 0:
                    return Signal(
                        signal_date=signal_date,
                        account_id=account.id,
                        instrument_id=instrument.id,
                        signal_type=SignalType.ALLOW_ADD.value,
                        priority=4,
                        reason_code="tactical_confirm_add",
                        explanation=f"确认加仓：盈利 {pnl_pct:.1%}，价格在 MA20 上方，可加满计划仓",
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
                priority=5,
                reason_code="tactical_hold",
                explanation=f"持有观察：盈亏 {pnl_pct:.1%}",
                status=SignalStatus.PENDING.value,
                batch_id=batch_id,
                batch_version=batch_version,
            )

        else:
            # === 未持仓 ===
            # 趋势确认买入（PRD §11.3：站上 MA20 且 MA20 向上时可试错）
            if price > 0 and ma20 > 0 and price > ma20:
                # 检查 MA20 是否向上（简单判断：MA20 > MA60）
                ma20_up = ma20 > ma60 if ma60 > 0 else True
                if ma20_up:
                    return Signal(
                        signal_date=signal_date,
                        account_id=account.id,
                        instrument_id=instrument.id,
                        signal_type=SignalType.ALLOW_BUY.value,
                        priority=3,
                        reason_code="tactical_trend_buy",
                        explanation=f"趋势确认：价格 {price:.3f} > MA20 {ma20:.3f}，MA20 向上，可试探买入",
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
                explanation=f"观察等待：价格 {price:.3f}，MA20 {ma20:.3f}，趋势未确认",
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
        获取渐进式调仓建议（占位接口，待完善）

        根据当前信号、持仓、行情、策略绑定，计算分步调仓方案。
        返回结构化的调仓指导信息，包括：
        - 当前状态摘要
        - 目标状态
        - 建议的调仓步骤（分批执行）
        - 风险提示

        TODO: 后续完善以下功能
        1. 根据信号类型生成不同的调仓方案
        2. 分批调仓计划（如3次调仓，每次调整比例）
        3. 具体的买入/卖出金额和份额计算
        4. 考虑交易成本和最小交易单位
        5. 时间窗口建议（如每周调整一次）

        Args:
            signal: 当前信号
            position: 当前持仓（可为空）
            latest_md: 最新行情数据（可为空）
            assignment: 策略绑定（可为空）

        Returns:
            dict: 调仓建议结构
        """
        instrument = signal.instrument

        # 当前状态
        current_weight = position.weight_in_account if position else 0
        current_quantity = position.quantity if position else 0
        current_value = position.market_value if position else 0
        latest_price = None
        if latest_md:
            latest_price = latest_md.close or latest_md.nav or 0

        # 目标状态
        target_lower = assignment.target_weight_lower if assignment else 0
        target_upper = assignment.target_weight_upper if assignment else 0
        target_mid = (target_lower + target_upper) / 2 if (target_lower + target_upper) > 0 else 0

        return {
            "signal_summary": {
                "signal_type": signal.signal_type,
                "explanation": signal.explanation,
                "score": signal.score,
                "priority": signal.priority,
            },
            "current_status": {
                "instrument_name": instrument.name,
                "instrument_symbol": instrument.symbol,
                "current_weight": current_weight,
                "current_quantity": current_quantity,
                "current_value": current_value,
                "latest_price": latest_price,
                "price_date": str(latest_md.trade_date) if latest_md else None,
            },
            "target_status": {
                "target_weight_lower": target_lower,
                "target_weight_upper": target_upper,
                "target_weight_mid": target_mid,
            },
            "rebalance_steps": [
                # TODO: 待完善 - 根据信号类型生成具体的分步调仓计划
                # 示例结构:
                # {
                #     "step": 1,
                #     "action": "buy" / "sell",
                #     "ratio": 0.33,  # 本次调整占总调整量的比例
                #     "description": "第一步：买入目标金额的 1/3",
                #     "suggested_timing": "本周内",
                # },
            ],
            "risk_warnings": [
                # TODO: 待完善 - 根据市场状态生成风险提示
            ],
            "notes": "调仓建议功能开发中，后续将提供详细的分步调仓方案。",
        }

