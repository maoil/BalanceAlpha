"""
共享信号评分引擎

提供核心账户和战术账户的纯评分逻辑，
供 SignalService（实盘信号生成）和 BacktestService（回测模拟）共用，
避免评分算法在两处代码中重复维护。
"""
from app.utils.constants import SignalType


def evaluate_core_signal(
    drawdown: float,
    current_weight: float,
    target_lower: float,
    target_upper: float,
    price: float,
    ma60: float,
) -> dict:
    """
    核心账户评分逻辑（PRD §7.7.3 / §7.8）

    评分维度：
    - 回撤分 40 分：回撤越深分越高（买入机会）
    - 配置缺口分 20 分：低于目标权重越多分越高
    - 趋势分 20 分：价格 vs MA60
    - 产品质量分 20 分（V1 默认 15 分）

    Returns:
        dict: signal_type, priority, score, reason_code
    """
    target_mid = (
        (target_lower + target_upper) / 2
        if (target_lower + target_upper) > 0 else 0.0
    )

    # 回撤分（40分）
    if drawdown <= -0.20:
        drawdown_score = 40
    elif drawdown <= -0.10:
        drawdown_score = 30
    elif drawdown <= -0.05:
        drawdown_score = 20
    else:
        drawdown_score = 10

    # 配置缺口分（20分）
    if target_mid > 0 and current_weight < target_lower:
        gap_ratio = (target_mid - current_weight) / target_mid
        config_gap_score = min(20, int(gap_ratio * 40))
    elif target_mid > 0 and current_weight > target_upper:
        config_gap_score = 0
    else:
        config_gap_score = 10

    # 趋势分（20分）
    _ma60 = ma60 if ma60 > 0 else price
    if price > 0 and _ma60 > 0:
        if price > _ma60:
            trend_score = 15
        elif price > _ma60 * 0.95:
            trend_score = 10
        else:
            trend_score = 5
    else:
        trend_score = 10

    # 产品质量分（20分，V1 默认 15）
    quality_score = 15

    total_score = drawdown_score + config_gap_score + trend_score + quality_score

    # 信号分级
    if total_score >= 70:
        signal_type = SignalType.ALLOW_BUY.value
        priority = 2
    elif total_score >= 55:
        signal_type = SignalType.HOLD.value
        priority = 5
    else:
        signal_type = SignalType.SUSPEND_ADD.value
        priority = 7

    # 再平衡检查：偏离超过 20%
    if target_mid > 0 and current_weight > 0:
        deviation = abs(current_weight - target_mid) / target_mid
        if deviation > 0.20:
            signal_type = SignalType.REBALANCE.value
            priority = 1

    return {
        "signal_type": signal_type,
        "priority": priority,
        "score": total_score,
        "reason_code": f"core_score_{total_score}",
    }


def evaluate_tactical_signal(
    price: float,
    ma20: float,
    ma60: float,
    rs20d: float,
    pnl_pct: float,
    has_position: bool,
    config: dict,
) -> dict:
    """
    战术账户纯评分逻辑（PRD §7.7.4 / §11.2）

    Returns:
        dict: signal_type, priority, reason_code
    """
    stop_loss_warn_pct = config.get("stop_loss_warn_pct", -0.05)
    stop_loss_pct = config.get("stop_loss_pct", -0.08)
    stop_loss_clear_pct = config.get("stop_loss_clear_pct", -0.10)
    early_exit_pct = config.get("early_exit_pct", -0.06)
    profit_protect_trigger_pct = config.get("profit_protect_trigger_pct", 0.09)
    take_profit_pct_1 = config.get("take_profit_pct_1", 0.12)
    take_profit_pct_2 = config.get("take_profit_pct_2", 0.18)
    take_profit_pct_3 = config.get("take_profit_pct_3", 0.25)
    add_confirm_pct = config.get("add_confirm_pct", 0.05)
    entry_rs_threshold = config.get("entry_rs_threshold", 0.00)

    price_below_ma20 = price > 0 and ma20 > 0 and price < ma20
    trend_broken = price_below_ma20 and ma20 > 0 and ma60 > 0 and ma20 < ma60

    if has_position:
        # 止损逻辑
        if pnl_pct <= stop_loss_clear_pct:
            return {"signal_type": SignalType.STOP_LOSS.value, "priority": 1, "reason_code": "tactical_stop_loss"}
        if pnl_pct <= early_exit_pct and trend_broken:
            return {"signal_type": SignalType.STOP_LOSS.value, "priority": 1, "reason_code": "tactical_early_exit"}
        if pnl_pct <= stop_loss_pct:
            return {"signal_type": SignalType.REDUCE.value, "priority": 2, "reason_code": "tactical_reduce_major"}
        if pnl_pct <= stop_loss_warn_pct and price_below_ma20:
            return {"signal_type": SignalType.REDUCE.value, "priority": 3, "reason_code": "tactical_reduce_warn"}

        # 止盈逻辑
        if pnl_pct >= take_profit_pct_3:
            return {"signal_type": SignalType.TAKE_PROFIT.value, "priority": 2, "reason_code": "tactical_take_profit_3"}
        if pnl_pct >= take_profit_pct_2:
            return {"signal_type": SignalType.TAKE_PROFIT.value, "priority": 3, "reason_code": "tactical_take_profit_2"}
        if pnl_pct >= take_profit_pct_1:
            return {"signal_type": SignalType.TAKE_PROFIT.value, "priority": 4, "reason_code": "tactical_take_profit_1"}

        # 盈利保护
        if pnl_pct >= profit_protect_trigger_pct and price_below_ma20:
            return {"signal_type": SignalType.REDUCE.value, "priority": 4, "reason_code": "tactical_profit_protect"}

        # 确认加仓
        if add_confirm_pct <= pnl_pct < take_profit_pct_1:
            if price > ma20 > 0 and (ma60 <= 0 or ma20 >= ma60):
                return {"signal_type": SignalType.ALLOW_ADD.value, "priority": 5, "reason_code": "tactical_confirm_add"}

        return {"signal_type": SignalType.HOLD.value, "priority": 6, "reason_code": "tactical_hold"}

    # 未持仓 — 趋势买入检查
    if price > 0 and ma20 > 0 and price > ma20:
        ma20_up = ma20 > ma60 if ma60 > 0 else True
        if ma20_up and rs20d >= entry_rs_threshold:
            return {"signal_type": SignalType.ALLOW_BUY.value, "priority": 3, "reason_code": "tactical_trend_buy"}

    return {"signal_type": SignalType.OBSERVE.value, "priority": 8, "reason_code": "tactical_observe"}
