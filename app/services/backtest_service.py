"""
回测服务
"""
import json
import logging
from dataclasses import dataclass
from datetime import date
from statistics import mean, pstdev
from typing import Optional

from app.extensions import db
from app.models.account import Account
from app.models.backtest_run import BacktestRun
from app.models.instrument import Instrument
from app.models.market_data import MarketData
from app.models.strategy_assignment import StrategyAssignment
from app.models.strategy_template import StrategyTemplate
from app.services.log_service import LogService
from app.utils.constants import AccountType, BacktestStatus, SignalType

logger = logging.getLogger(__name__)
BACKTEST_WARMUP_TRADING_DAYS = 250


@dataclass
class _PositionState:
    quantity: float = 0.0
    avg_cost: float = 0.0
    market_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    peak_quantity: float = 0.0
    add_executed: bool = False
    take_profit_stage: int = 0
    profit_protect_executed: bool = False
    warn_reduce_executed: bool = False
    major_reduce_executed: bool = False

    def sync_price(self, price: float) -> None:
        self.market_price = price or 0.0
        if self.quantity > 0 and self.market_price > 0:
            self.market_value = self.quantity * self.market_price
            cost_value = self.quantity * self.avg_cost
            self.unrealized_pnl = self.market_value - cost_value
            self.unrealized_pnl_pct = (
                self.unrealized_pnl / cost_value if cost_value > 0 else 0.0
            )
        else:
            self.market_value = 0.0
            self.unrealized_pnl = 0.0
            self.unrealized_pnl_pct = 0.0

    def reset_tactical_cycle(self) -> None:
        self.peak_quantity = self.quantity if self.quantity > 0 else 0.0
        self.add_executed = False
        self.take_profit_stage = 0
        self.profit_protect_executed = False
        self.warn_reduce_executed = False
        self.major_reduce_executed = False

    def register_peak_quantity(self) -> None:
        if self.quantity > self.peak_quantity:
            self.peak_quantity = self.quantity

    def clear_if_empty(self) -> None:
        if self.quantity <= 1e-8:
            self.quantity = 0.0
            self.avg_cost = 0.0
            self.reset_tactical_cycle()


class BacktestService:
    """策略回测服务"""

    @staticmethod
    def list_runs(limit: int = 50) -> list[BacktestRun]:
        return BacktestRun.query.order_by(
            BacktestRun.created_at.desc(),
            BacktestRun.id.desc(),
        ).limit(limit).all()

    @staticmethod
    def get_run(run_id: int) -> Optional[BacktestRun]:
        return db.session.get(BacktestRun, run_id)

    @staticmethod
    def parse_params(run: Optional[BacktestRun]) -> dict:
        if not run or not run.params_json:
            return {}
        try:
            return json.loads(run.params_json)
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def parse_result(run: Optional[BacktestRun]) -> dict:
        if not run or not run.result_json:
            return {}
        try:
            return json.loads(run.result_json)
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def run_backtest(
        run_name: str,
        account_id: int,
        start_date: date,
        end_date: date,
        initial_capital: float,
        instrument_id: Optional[int] = None,
        template_id: Optional[int] = None,
        fee_rate: float = 0.001,
    ) -> BacktestRun:
        if start_date > end_date:
            raise ValueError("开始日期不能晚于结束日期")
        if initial_capital <= 0:
            raise ValueError("初始资金必须大于 0")

        account, assignments = BacktestService._resolve_scope(
            account_id=account_id,
            instrument_id=instrument_id,
            template_id=template_id,
        )
        selected_template_id = template_id
        if selected_template_id is None:
            template_ids = {assignment.template_id for assignment in assignments}
            selected_template_id = next(iter(template_ids)) if len(template_ids) == 1 else None

        params = {
            "account_id": account.id,
            "account_name": account.account_name,
            "account_type": account.account_type,
            "instrument_id": instrument_id,
            "template_id": template_id,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "initial_capital": initial_capital,
            "fee_rate": fee_rate,
            "warmup_trading_days": BACKTEST_WARMUP_TRADING_DAYS,
            "assignment_ids": [assignment.id for assignment in assignments],
        }

        run = BacktestRun(
            run_name=run_name,
            template_id=selected_template_id,
            start_date=start_date,
            end_date=end_date,
            params_json=json.dumps(params, ensure_ascii=False),
            result_json="{}",
            status=BacktestStatus.RUNNING.value,
        )
        db.session.add(run)
        db.session.commit()

        try:
            result = BacktestService._simulate_account(
                account=account,
                assignments=assignments,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                fee_rate=fee_rate,
            )
            run.result_json = json.dumps(result, ensure_ascii=False)
            run.status = BacktestStatus.COMPLETED.value
            db.session.commit()

            LogService.log(
                log_type="signal",
                level="info",
                module="backtest_service",
                message=f"回测完成: run_id={run.id}, name={run.run_name}",
                context={
                    "run_id": run.id,
                    "account_id": account.id,
                    "instrument_id": instrument_id,
                    "template_id": template_id,
                },
            )
        except Exception as exc:
            logger.exception("回测执行失败: run_id=%s", run.id)
            run.result_json = json.dumps({"error": str(exc)}, ensure_ascii=False)
            run.status = BacktestStatus.FAILED.value
            db.session.commit()

            LogService.log(
                log_type="error",
                level="error",
                module="backtest_service",
                message=f"回测失败: run_id={run.id}, name={run.run_name}",
                context={"run_id": run.id, "error": str(exc)},
            )
            raise

        return run

    @staticmethod
    def _resolve_scope(
        account_id: int,
        instrument_id: Optional[int],
        template_id: Optional[int],
    ) -> tuple[Account, list[StrategyAssignment]]:
        account = db.session.get(Account, account_id)
        if not account:
            raise ValueError("账户不存在")

        query = StrategyAssignment.query.filter_by(
            account_id=account_id,
            status="active",
        )
        if instrument_id:
            query = query.filter_by(instrument_id=instrument_id)
        if template_id:
            query = query.filter_by(template_id=template_id)

        assignments = query.order_by(StrategyAssignment.instrument_id.asc()).all()
        if not assignments:
            instrument = db.session.get(Instrument, instrument_id) if instrument_id else None
            template = db.session.get(StrategyTemplate, template_id) if template_id else None

            filters = [f"账户：{account.account_name}"]
            if instrument:
                filters.append(f"产品：{instrument.symbol} {instrument.name}")
            if template:
                filters.append(f"模板：{template.template_name}")

            raise ValueError(
                "当前条件下没有可回测的策略绑定。"
                + "；".join(filters)
                + "。通常是选到了其他账户下的产品或模板，或该组合当前没有激活绑定。"
            )

        return account, assignments

    @staticmethod
    def _simulate_account(
        account: Account,
        assignments: list[StrategyAssignment],
        start_date: date,
        end_date: date,
        initial_capital: float,
        fee_rate: float,
    ) -> dict:
        instrument_ids = [assignment.instrument_id for assignment in assignments]
        templates_by_instrument = {
            assignment.instrument_id: assignment.template
            for assignment in assignments
        }
        assignments_by_instrument = {
            assignment.instrument_id: assignment
            for assignment in assignments
        }
        instruments_by_id = {
            instrument.id: instrument
            for instrument in Instrument.query.filter(
                Instrument.id.in_(instrument_ids)
            ).all()
        }
        rows = MarketData.query.filter(
            MarketData.instrument_id.in_(instrument_ids),
            MarketData.trade_date <= end_date,
        ).order_by(
            MarketData.trade_date.asc(),
            MarketData.instrument_id.asc(),
        ).all()
        if not rows:
            raise ValueError("所选范围内没有行情数据，无法回测")

        simulation_rows = [
            row for row in rows
            if start_date <= row.trade_date <= end_date
        ]
        if not simulation_rows:
            raise ValueError("所选范围内没有可用于回测的行情数据")

        rows_by_date: dict[date, list[MarketData]] = {}
        for row in rows:
            rows_by_date.setdefault(row.trade_date, []).append(row)

        all_dates = sorted(rows_by_date.keys())
        latest_rows: dict[int, MarketData] = {}
        positions = {instrument_id: _PositionState() for instrument_id in instrument_ids}
        cash = float(initial_capital)
        peak_equity = float(initial_capital)
        realized_pnl_total = 0.0
        fees_total = 0.0
        profitable_sells = 0
        sell_count = 0
        buy_count = 0
        trades: list[dict] = []
        equity_curve: list[dict] = []

        for current_date in all_dates:
            todays_rows = rows_by_date[current_date]
            for row in todays_rows:
                latest_rows[row.instrument_id] = row

            BacktestService._refresh_positions(positions, latest_rows)
            if current_date < start_date:
                continue
            equity_before = cash + sum(pos.market_value for pos in positions.values())
            if equity_before <= 0:
                equity_before = cash

            decisions = []
            for row in todays_rows:
                instrument_id = row.instrument_id
                instrument = instruments_by_id[instrument_id]
                assignment = assignments_by_instrument[instrument_id]
                template = templates_by_instrument[instrument_id]
                state = positions[instrument_id]
                current_weight = (
                    state.market_value / equity_before if equity_before > 0 else 0.0
                )
                config = BacktestService._load_config(template, assignment)

                if account.account_type == AccountType.CORE.value:
                    signal = BacktestService._evaluate_core_signal(
                        row=row,
                        current_weight=current_weight,
                        target_lower=assignment.target_weight_lower or 0.0,
                        target_upper=assignment.target_weight_upper or 0.0,
                    )
                    order = BacktestService._build_core_order(
                        signal=signal,
                        state=state,
                        equity=equity_before,
                        cash=cash,
                        assignment=assignment,
                        config=config,
                    )
                else:
                    signal = BacktestService._evaluate_tactical_signal(
                        row=row,
                        state=state,
                        config=config,
                    )
                    order = BacktestService._build_tactical_order(
                        signal=signal,
                        state=state,
                        equity=equity_before,
                        cash=cash,
                        assignment=assignment,
                        config=config,
                    )

                if order:
                    order.update({
                        "instrument": instrument,
                        "signal_type": signal["signal_type"],
                        "reason_code": signal["reason_code"],
                        "priority": signal["priority"],
                        "trade_date": current_date,
                    })
                    decisions.append(order)

            decisions.sort(
                key=lambda item: (
                    0 if item["action"] == "sell" else 1,
                    item["priority"],
                )
            )

            for decision in decisions:
                trade = BacktestService._execute_order(
                    decision=decision,
                    positions=positions,
                    cash=cash,
                    fee_rate=fee_rate,
                    latest_rows=latest_rows,
                )
                cash = trade["cash_after"] if trade else cash
                if not trade:
                    continue
                trades.append(trade)
                fees_total += trade["fee"]
                realized_pnl_total += trade["realized_pnl"]
                if trade["action"] == "buy":
                    buy_count += 1
                if trade["action"] == "sell":
                    sell_count += 1
                    if trade["realized_pnl"] > 0:
                        profitable_sells += 1

            BacktestService._refresh_positions(positions, latest_rows)
            position_value = sum(pos.market_value for pos in positions.values())
            equity = cash + position_value
            peak_equity = max(peak_equity, equity)
            drawdown = (equity - peak_equity) / peak_equity if peak_equity > 0 else 0.0

            equity_curve.append({
                "date": str(current_date),
                "equity": round(equity, 2),
                "cash": round(cash, 2),
                "position_value": round(position_value, 2),
                "drawdown": round(drawdown, 4),
            })

        summary = BacktestService._build_summary(
            initial_capital=initial_capital,
            cash=cash,
            positions=positions,
            equity_curve=equity_curve,
            assignments=assignments,
            instruments_by_id=instruments_by_id,
            rows=simulation_rows,
            buy_count=buy_count,
            sell_count=sell_count,
            profitable_sells=profitable_sells,
            fees_total=fees_total,
            realized_pnl_total=realized_pnl_total,
            start_date=start_date,
            end_date=end_date,
        )
        history_coverage = BacktestService._build_history_coverage(
            assignments=assignments,
            instruments_by_id=instruments_by_id,
            rows=rows,
            start_date=start_date,
            end_date=end_date,
        )

        final_positions = []
        final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
        for instrument_id, state in positions.items():
            instrument = instruments_by_id[instrument_id]
            weight = state.market_value / final_equity if final_equity > 0 else 0.0
            final_positions.append({
                "instrument_id": instrument_id,
                "symbol": instrument.symbol,
                "name": instrument.name,
                "quantity": round(state.quantity, 4),
                "avg_cost": round(state.avg_cost, 4),
                "latest_price": round(state.market_price, 4),
                "market_value": round(state.market_value, 2),
                "weight": round(weight, 4),
                "unrealized_pnl_pct": round(state.unrealized_pnl_pct, 4),
            })

        scope = {
            "account_id": account.id,
            "account_name": account.account_name,
            "account_type": account.account_type,
            "instruments": [
                {
                    "instrument_id": instrument.id,
                    "symbol": instrument.symbol,
                    "name": instrument.name,
                }
                for instrument in instruments_by_id.values()
            ],
            "template_names": sorted({
                assignment.template.template_name
                for assignment in assignments
                if assignment.template is not None
            }),
        }

        return {
            "scope": scope,
            "summary": summary,
            "history_coverage": history_coverage,
            "positions": final_positions,
            "trades": trades,
            "equity_curve": equity_curve,
        }

    @staticmethod
    def _build_history_coverage(
        assignments: list[StrategyAssignment],
        instruments_by_id: dict[int, Instrument],
        rows: list[MarketData],
        start_date: date,
        end_date: date,
    ) -> dict:
        rows_by_instrument: dict[int, list[MarketData]] = {}
        for row in rows:
            rows_by_instrument.setdefault(row.instrument_id, []).append(row)

        coverage = []
        has_warnings = False
        pre_start_dates = sorted({
            row.trade_date
            for row in rows
            if row.trade_date < start_date
        })
        if len(pre_start_dates) >= BACKTEST_WARMUP_TRADING_DAYS:
            warmup_start = pre_start_dates[-BACKTEST_WARMUP_TRADING_DAYS]
        else:
            warmup_start = pre_start_dates[0] if pre_start_dates else None

        for assignment in assignments:
            instrument = instruments_by_id[assignment.instrument_id]
            instrument_rows = rows_by_instrument.get(assignment.instrument_id, [])
            pre_start_rows = [
                row for row in instrument_rows
                if row.trade_date < start_date
            ]
            backtest_rows = [
                row for row in instrument_rows
                if start_date <= row.trade_date <= end_date
            ]
            warmup_ready = len(pre_start_rows) >= BACKTEST_WARMUP_TRADING_DAYS
            range_ready = len(backtest_rows) > 0
            warning = (not warmup_ready) or (not range_ready)
            has_warnings = has_warnings or warning

            coverage.append({
                "instrument_id": instrument.id,
                "symbol": instrument.symbol,
                "name": instrument.name,
                "first_trade_date": str(instrument_rows[0].trade_date) if instrument_rows else None,
                "last_trade_date": str(instrument_rows[-1].trade_date) if instrument_rows else None,
                "warmup_days": len(pre_start_rows),
                "warmup_ready": warmup_ready,
                "backtest_days": len(backtest_rows),
                "range_ready": range_ready,
                "warning": warning,
            })

        return {
            "warmup_trading_days": BACKTEST_WARMUP_TRADING_DAYS,
            "warmup_start": str(warmup_start) if warmup_start else None,
            "has_warnings": has_warnings,
            "warning_count": sum(1 for item in coverage if item["warning"]),
            "coverage": coverage,
        }

    @staticmethod
    def _load_config(template: Optional[StrategyTemplate], assignment: StrategyAssignment) -> dict:
        """加载有效策略参数（委托给 model 方法）"""
        return assignment.get_effective_config()

    @staticmethod
    def _refresh_positions(
        positions: dict[int, _PositionState],
        latest_rows: dict[int, MarketData],
    ) -> None:
        for instrument_id, state in positions.items():
            row = latest_rows.get(instrument_id)
            price = BacktestService._price_from_row(row)
            if price > 0:
                state.sync_price(price)

    @staticmethod
    def _price_from_row(row: Optional[MarketData]) -> float:
        if not row:
            return 0.0
        return float(row.close or row.nav or 0.0)

    @staticmethod
    def _evaluate_core_signal(
        row: MarketData,
        current_weight: float,
        target_lower: float,
        target_upper: float,
    ) -> dict:
        target_mid = (
            (target_lower + target_upper) / 2
            if (target_lower + target_upper) > 0 else 0.0
        )
        drawdown = row.drawdown_60d or 0.0
        if drawdown <= -0.20:
            drawdown_score = 40
        elif drawdown <= -0.10:
            drawdown_score = 30
        elif drawdown <= -0.05:
            drawdown_score = 20
        else:
            drawdown_score = 10

        if target_mid > 0 and current_weight < target_lower:
            gap_ratio = (target_mid - current_weight) / target_mid
            config_gap_score = min(20, int(gap_ratio * 40))
        elif target_mid > 0 and current_weight > target_upper:
            config_gap_score = 0
        else:
            config_gap_score = 10

        price = BacktestService._price_from_row(row)
        ma60 = row.ma60 or price
        if price > 0 and ma60 > 0:
            if price > ma60:
                trend_score = 15
            elif price > ma60 * 0.95:
                trend_score = 10
            else:
                trend_score = 5
        else:
            trend_score = 10

        total_score = drawdown_score + config_gap_score + trend_score + 15
        if total_score >= 70:
            signal_type = SignalType.ALLOW_BUY.value
            priority = 2
        elif total_score >= 55:
            signal_type = SignalType.HOLD.value
            priority = 5
        else:
            signal_type = SignalType.SUSPEND_ADD.value
            priority = 7

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

    @staticmethod
    def _evaluate_tactical_signal(
        row: MarketData,
        state: _PositionState,
        config: dict,
    ) -> dict:
        price = BacktestService._price_from_row(row)
        ma20 = row.ma20 or 0.0
        ma60 = row.ma60 or 0.0
        rs20d = row.relative_strength_20d or 0.0

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
        pnl_pct = state.unrealized_pnl_pct or 0.0

        if state.quantity > 0:
            if pnl_pct <= stop_loss_clear_pct:
                return {
                    "signal_type": SignalType.STOP_LOSS.value,
                    "priority": 1,
                    "reason_code": "tactical_stop_loss",
                }
            if pnl_pct <= early_exit_pct and trend_broken:
                return {
                    "signal_type": SignalType.STOP_LOSS.value,
                    "priority": 1,
                    "reason_code": "tactical_early_exit",
                }
            if pnl_pct <= stop_loss_pct:
                if not state.major_reduce_executed:
                    return {
                        "signal_type": SignalType.REDUCE.value,
                        "priority": 2,
                        "reason_code": "tactical_reduce_major",
                    }
            if pnl_pct <= stop_loss_warn_pct and price_below_ma20:
                if not state.warn_reduce_executed:
                    return {
                        "signal_type": SignalType.REDUCE.value,
                        "priority": 3,
                        "reason_code": "tactical_reduce_warn",
                    }
            if state.take_profit_stage == 0 and pnl_pct >= take_profit_pct_1:
                return {
                    "signal_type": SignalType.TAKE_PROFIT.value,
                    "priority": 4,
                    "reason_code": "tactical_take_profit_1",
                }
            if state.take_profit_stage == 1 and pnl_pct >= take_profit_pct_2:
                return {
                    "signal_type": SignalType.TAKE_PROFIT.value,
                    "priority": 3,
                    "reason_code": "tactical_take_profit_2",
                }
            if state.take_profit_stage == 2 and pnl_pct >= take_profit_pct_3:
                return {
                    "signal_type": SignalType.TAKE_PROFIT.value,
                    "priority": 2,
                    "reason_code": "tactical_take_profit_3",
                }
            if pnl_pct >= profit_protect_trigger_pct and price_below_ma20:
                if not state.profit_protect_executed:
                    return {
                        "signal_type": SignalType.REDUCE.value,
                        "priority": 4,
                        "reason_code": "tactical_profit_protect",
                    }
            if add_confirm_pct <= pnl_pct < take_profit_pct_1:
                if (
                    not state.add_executed
                    and price > ma20 > 0
                    and (ma60 <= 0 or ma20 >= ma60)
                ):
                    return {
                        "signal_type": SignalType.ALLOW_ADD.value,
                        "priority": 5,
                        "reason_code": "tactical_confirm_add",
                    }
            return {
                "signal_type": SignalType.HOLD.value,
                "priority": 6,
                "reason_code": "tactical_hold",
            }

        if price > 0 and ma20 > 0 and price > ma20:
            ma20_up = ma20 > ma60 if ma60 > 0 else True
            if ma20_up and rs20d >= entry_rs_threshold:
                return {
                    "signal_type": SignalType.ALLOW_BUY.value,
                    "priority": 3,
                    "reason_code": "tactical_trend_buy",
                }

        return {
            "signal_type": SignalType.OBSERVE.value,
            "priority": 8,
            "reason_code": "tactical_observe",
        }

    @staticmethod
    def _build_core_order(
        signal: dict,
        state: _PositionState,
        equity: float,
        cash: float,
        assignment: StrategyAssignment,
        config: dict,
    ) -> Optional[dict]:
        target_lower = assignment.target_weight_lower or 0.0
        target_upper = assignment.target_weight_upper or 0.0
        target_mid = (
            (target_lower + target_upper) / 2
            if (target_lower + target_upper) > 0 else 0.0
        )
        if target_mid <= 0 or equity <= 0:
            return None

        current_value = state.market_value
        target_value = equity * target_mid
        cash_buffer_lower = config.get("cash_buffer_lower", 0.0)
        signal_type = signal["signal_type"]
        current_weight = current_value / equity if equity > 0 else 0.0

        if signal_type == SignalType.REBALANCE.value:
            if current_weight > target_upper and current_value > target_value:
                return {
                    "action": "sell",
                    "amount": current_value - target_value,
                }
            if current_weight < target_lower and current_value < target_value:
                max_buy = max(0.0, cash - cash_buffer_lower * equity)
                return {
                    "action": "buy",
                    "amount": min(target_value - current_value, max_buy),
                }
        if signal_type == SignalType.ALLOW_BUY.value and current_weight < target_lower:
            max_buy = max(0.0, cash - cash_buffer_lower * equity)
            return {
                "action": "buy",
                "amount": min(target_value - current_value, max_buy),
            }
        return None

    @staticmethod
    def _build_tactical_order(
        signal: dict,
        state: _PositionState,
        equity: float,
        cash: float,
        assignment: StrategyAssignment,
        config: dict,
    ) -> Optional[dict]:
        if equity <= 0:
            return None

        planned_max_weight = assignment.target_weight_upper or assignment.target_weight_lower or 1.0
        planned_max_weight = max(planned_max_weight, 0.10)
        planned_capital = equity * planned_max_weight
        current_value = state.market_value
        signal_type = signal["signal_type"]

        initial_position_pct = config.get("initial_position_pct", 0.40)
        add_position_pct = config.get("add_position_pct", 0.30)
        stop_loss_warn_reduce_ratio = config.get("stop_loss_warn_reduce_ratio", 0.25)
        stop_loss_reduce_ratio = config.get("stop_loss_reduce_ratio", 0.50)
        profit_protect_reduce_ratio = config.get("profit_protect_reduce_ratio", 0.20)
        take_profit_sell_ratio_1 = config.get("take_profit_sell_ratio_1", 0.20)
        take_profit_sell_ratio_2 = config.get("take_profit_sell_ratio_2", 0.30)
        take_profit_sell_ratio_3 = config.get("take_profit_sell_ratio_3", 0.30)

        if signal_type == SignalType.ALLOW_BUY.value:
            target_value = planned_capital * initial_position_pct
            return {
                "action": "buy",
                "amount": min(max(0.0, target_value - current_value), cash),
            }
        if signal_type == SignalType.ALLOW_ADD.value:
            target_value = planned_capital * (initial_position_pct + add_position_pct)
            return {
                "action": "buy",
                "amount": min(max(0.0, target_value - current_value), cash),
            }
        if signal_type == SignalType.REDUCE.value:
            if signal["reason_code"] == "tactical_reduce_major":
                ratio = stop_loss_reduce_ratio
            elif signal["reason_code"] == "tactical_profit_protect":
                ratio = profit_protect_reduce_ratio
            else:
                ratio = stop_loss_warn_reduce_ratio
            return {
                "action": "sell",
                "amount": current_value * ratio,
            }
        if signal_type == SignalType.TAKE_PROFIT.value:
            reference_quantity = state.peak_quantity or state.quantity
            if reference_quantity <= 0 or state.market_price <= 0:
                return None

            if signal["reason_code"] == "tactical_take_profit_3":
                target_remaining_ratio = max(
                    0.0,
                    1.0 - take_profit_sell_ratio_1 - take_profit_sell_ratio_2 - take_profit_sell_ratio_3,
                )
            elif signal["reason_code"] == "tactical_take_profit_2":
                target_remaining_ratio = max(
                    0.0,
                    1.0 - take_profit_sell_ratio_1 - take_profit_sell_ratio_2,
                )
            else:
                target_remaining_ratio = max(0.0, 1.0 - take_profit_sell_ratio_1)

            target_quantity = reference_quantity * target_remaining_ratio
            sell_quantity = max(0.0, state.quantity - target_quantity)
            if sell_quantity <= 0:
                return None
            return {
                "action": "sell",
                "amount": sell_quantity * state.market_price,
            }
        if signal_type == SignalType.STOP_LOSS.value:
            return {
                "action": "sell",
                "amount": current_value,
            }
        return None

    @staticmethod
    def _execute_order(
        decision: dict,
        positions: dict[int, _PositionState],
        cash: float,
        fee_rate: float,
        latest_rows: dict[int, MarketData],
    ) -> Optional[dict]:
        instrument: Instrument = decision["instrument"]
        state = positions[instrument.id]
        row = latest_rows.get(instrument.id)
        price = BacktestService._price_from_row(row)
        amount = max(0.0, decision.get("amount", 0.0))
        if price <= 0 or amount <= 0:
            return None

        if decision["action"] == "buy":
            max_amount = cash / (1 + fee_rate) if fee_rate >= 0 else cash
            amount = min(amount, max_amount)
            if amount <= 0:
                return None
            fee = amount * fee_rate
            quantity = amount / price
            total_cost = state.avg_cost * state.quantity + amount + fee
            state.quantity += quantity
            state.avg_cost = total_cost / state.quantity if state.quantity > 0 else 0.0
            cash_after = cash - amount - fee
            realized_pnl = 0.0
        else:
            max_amount = min(amount, state.quantity * price)
            if max_amount <= 0 or state.quantity <= 0:
                return None
            amount = max_amount
            quantity = amount / price
            quantity = min(quantity, state.quantity)
            fee = amount * fee_rate
            realized_pnl = quantity * (price - state.avg_cost) - fee
            state.quantity = max(0.0, state.quantity - quantity)
            if state.quantity <= 1e-8:
                state.quantity = 0.0
                state.avg_cost = 0.0
            cash_after = cash + amount - fee

        BacktestService._update_tactical_position_state_after_trade(
            decision=decision,
            state=state,
        )
        state.sync_price(price)

        return {
            "date": str(decision["trade_date"]),
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "name": instrument.name,
            "action": decision["action"],
            "signal_type": decision["signal_type"],
            "reason_code": decision["reason_code"],
            "price": round(price, 4),
            "amount": round(amount, 2),
            "quantity": round(quantity, 4),
            "fee": round(fee, 2),
            "cash_after": round(cash_after, 2),
            "position_value_after": round(state.market_value, 2),
            "position_quantity_after": round(state.quantity, 4),
            "realized_pnl": round(realized_pnl, 2),
        }

    @staticmethod
    def _update_tactical_position_state_after_trade(
        decision: dict,
        state: _PositionState,
    ) -> None:
        reason_code = decision.get("reason_code", "")
        action = decision.get("action", "")

        if action == "buy":
            if reason_code == "tactical_trend_buy":
                state.reset_tactical_cycle()
                state.register_peak_quantity()
            elif reason_code == "tactical_confirm_add":
                state.add_executed = True
                state.register_peak_quantity()
            return

        if action != "sell":
            return

        if reason_code == "tactical_take_profit_1":
            state.take_profit_stage = max(state.take_profit_stage, 1)
        elif reason_code == "tactical_take_profit_2":
            state.take_profit_stage = max(state.take_profit_stage, 2)
        elif reason_code == "tactical_take_profit_3":
            state.take_profit_stage = max(state.take_profit_stage, 3)
        elif reason_code == "tactical_profit_protect":
            state.profit_protect_executed = True
        elif reason_code == "tactical_reduce_warn":
            state.warn_reduce_executed = True
        elif reason_code == "tactical_reduce_major":
            state.major_reduce_executed = True

        state.clear_if_empty()

    @staticmethod
    def _build_summary(
        initial_capital: float,
        cash: float,
        positions: dict[int, _PositionState],
        equity_curve: list[dict],
        assignments: list[StrategyAssignment],
        instruments_by_id: dict[int, Instrument],
        rows: list[MarketData],
        buy_count: int,
        sell_count: int,
        profitable_sells: int,
        fees_total: float,
        realized_pnl_total: float,
        start_date: date,
        end_date: date,
    ) -> dict:
        final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
        position_value_end = sum(position.market_value for position in positions.values())
        total_return = (final_equity / initial_capital - 1) if initial_capital > 0 else 0.0
        total_days = max(1, (end_date - start_date).days)
        annualized_return = (
            (final_equity / initial_capital) ** (365 / total_days) - 1
            if initial_capital > 0 and final_equity > 0 and total_days > 0
            else 0.0
        )
        max_drawdown = min((point["drawdown"] for point in equity_curve), default=0.0)
        daily_returns = []
        for previous, current in zip(equity_curve, equity_curve[1:]):
            prev_equity = previous["equity"] or 0.0
            if prev_equity > 0:
                daily_returns.append(current["equity"] / prev_equity - 1)
        daily_volatility = pstdev(daily_returns) if len(daily_returns) >= 2 else 0.0
        sharpe = (
            mean(daily_returns) / daily_volatility * (252 ** 0.5)
            if daily_returns and daily_volatility > 0
            else 0.0
        )

        benchmark_return = BacktestService._compute_equal_weight_benchmark(
            assignments=assignments,
            rows=rows,
        )
        trade_count = buy_count + sell_count

        return {
            "initial_capital": round(initial_capital, 2),
            "final_equity": round(final_equity, 2),
            "cash_end": round(cash, 2),
            "position_value_end": round(position_value_end, 2),
            "total_return": round(total_return, 4),
            "annualized_return": round(annualized_return, 4),
            "max_drawdown": round(max_drawdown, 4),
            "daily_volatility": round(daily_volatility, 4),
            "sharpe": round(sharpe, 4),
            "benchmark_return": round(benchmark_return, 4),
            "excess_return": round(total_return - benchmark_return, 4),
            "trade_count": trade_count,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "win_rate": round((profitable_sells / sell_count) if sell_count > 0 else 0.0, 4),
            "fees_total": round(fees_total, 2),
            "realized_pnl_total": round(realized_pnl_total, 2),
            "trading_days": len({row.trade_date for row in rows}),
            "instrument_count": len(instruments_by_id),
        }

    @staticmethod
    def _compute_equal_weight_benchmark(
        assignments: list[StrategyAssignment],
        rows: list[MarketData],
    ) -> float:
        returns = []
        rows_by_instrument: dict[int, list[MarketData]] = {}
        for row in rows:
            rows_by_instrument.setdefault(row.instrument_id, []).append(row)

        for assignment in assignments:
            instrument_rows = rows_by_instrument.get(assignment.instrument_id, [])
            if len(instrument_rows) < 2:
                continue
            start_price = BacktestService._price_from_row(instrument_rows[0])
            end_price = BacktestService._price_from_row(instrument_rows[-1])
            if start_price > 0 and end_price > 0:
                returns.append(end_price / start_price - 1)

        if not returns:
            return 0.0
        return sum(returns) / len(returns)
