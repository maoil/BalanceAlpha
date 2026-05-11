"""
回测服务

第一阶段：使用 backtesting.py 原生回测引擎实现单产品回测
"""
import json
import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from app.extensions import db
from app.models.backtest_run import BacktestRun
from app.models.instrument import Instrument
from app.services.log_service import LogService
from app.utils.constants import BacktestStatus

from app.vendor.backtesting import Backtest
from app.backtesting.registry import resolve_config, BacktestConfig
from app.backtesting.result_serializer import (
    serialize_backtest_result,
    create_scope,
)

logger = logging.getLogger(__name__)


class BacktestService:
    """策略回测服务 - 使用 backtesting.py 原生引擎"""

    @staticmethod
    def list_runs(limit: int = 50) -> list[BacktestRun]:
        """列出回测记录"""
        return BacktestRun.query.order_by(
            BacktestRun.created_at.desc(),
            BacktestRun.id.desc(),
        ).limit(limit).all()

    @staticmethod
    def get_run(run_id: int) -> Optional[BacktestRun]:
        """获取回测记录"""
        return db.session.get(BacktestRun, run_id)

    @staticmethod
    def parse_params(run: Optional[BacktestRun]) -> dict:
        """解析回测参数"""
        if not run or not run.params_json:
            return {}
        try:
            return json.loads(run.params_json)
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def parse_result(run: Optional[BacktestRun]) -> dict:
        """解析回测结果"""
        if not run or not run.result_json:
            return {}
        try:
            return json.loads(run.result_json)
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def run_backtest(
        run_name: str,
        instrument_id: int,
        start_date: date,
        end_date: date,
        initial_capital: float,
        commission: Optional[float] = None,
        warmup_start_date: Optional[date] = None,
        strategy_params: Optional[dict] = None,
    ) -> BacktestRun:
        """
        执行回测

        Args:
            run_name: 运行名称
            instrument_id: 产品 ID
            start_date: 正式回测开始日期
            end_date: 回测结束日期
            initial_capital: 初始资金
            commission: 手续费率（可选，覆盖配置默认值）
            warmup_start_date: 预热开始日期（可选，不传则根据配置计算）
            strategy_params: 策略参数（可选，覆盖配置默认值）

        Returns:
            BacktestRun 记录
        """
        if start_date > end_date:
            raise ValueError("开始日期不能晚于结束日期")
        if initial_capital <= 0:
            raise ValueError("初始资金必须大于 0")

        instrument = db.session.get(Instrument, instrument_id)
        if not instrument:
            raise ValueError(f"产品不存在: {instrument_id}")

        config_key, config = resolve_config(
            config_key=instrument.backtest_config_key or None,
            symbol=instrument.symbol,
            market=instrument.market,
        )

        if warmup_start_date is None:
            warmup_start_date = start_date - timedelta(days=int(config.warmup_days * 1.5))

        merged_strategy_params = {**config.default_params}
        if strategy_params:
            merged_strategy_params.update(strategy_params)

        merged_backtest_config = {**config.backtest_config}
        if commission is not None:
            merged_backtest_config["commission"] = commission

        params = {
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "market": instrument.market,
            "name": instrument.name,
            "backtest_config_key": config_key,
            "config_name": config.name,
            "provider": config.provider.__name__,
            "provider_symbol": config.provider_symbol,
            "strategy_class": config.strategy_class.__name__,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "warmup_start_date": str(warmup_start_date),
            "initial_capital": initial_capital,
            "strategy_params": merged_strategy_params,
            "backtest_config": merged_backtest_config,
        }

        run = BacktestRun(
            run_name=run_name,
            instrument_id=instrument.id,
            backtest_config_key=config_key,
            start_date=start_date,
            end_date=end_date,
            warmup_start_date=warmup_start_date,
            params_json=json.dumps(params, ensure_ascii=False),
            result_json="{}",
            status=BacktestStatus.RUNNING.value,
        )
        db.session.add(run)
        db.session.commit()

        try:
            result = BacktestService._execute_backtest(
                config=config,
                config_key=config_key,
                instrument=instrument,
                start_date=start_date,
                end_date=end_date,
                warmup_start_date=warmup_start_date,
                initial_capital=initial_capital,
                strategy_params=merged_strategy_params,
                backtest_config=merged_backtest_config,
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
                    "instrument_id": instrument.id,
                    "config_key": config_key,
                },
            )
        except Exception as exc:
            logger.exception("回测执行失败: run_id=%s", run.id)
            error_result = {"error": str(exc)}
            run.result_json = json.dumps(error_result, ensure_ascii=False)
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
    def _execute_backtest(
        config: BacktestConfig,
        config_key: str,
        instrument: Instrument,
        start_date: date,
        end_date: date,
        warmup_start_date: date,
        initial_capital: float,
        strategy_params: dict,
        backtest_config: dict,
    ) -> dict:
        """
        执行回测核心逻辑

        Returns:
            序列化后的回测结果
        """
        raw_data = config.provider(
            symbol=config.provider_symbol,
            start=str(warmup_start_date),
            end=str(end_date),
        )

        if raw_data.empty:
            raise ValueError("数据源返回空数据")

        BacktestService._validate_ohlcv(raw_data)

        if config.prepare_data:
            prepared_data = config.prepare_data(raw_data)
        else:
            prepared_data = raw_data

        backtest_data = prepared_data.loc[str(start_date):str(end_date)]
        if backtest_data.empty:
            raise ValueError(f"回测日期范围 {start_date} - {end_date} 内没有数据")

        bt = Backtest(
            backtest_data,
            config.strategy_class,
            cash=initial_capital,
            commission=backtest_config.get("commission", 0.0),
            exclusive_orders=backtest_config.get("exclusive_orders", True),
            finalize_trades=backtest_config.get("finalize_trades", True),
        )

        stats = bt.run(**strategy_params)

        scope = create_scope(
            instrument_id=instrument.id,
            symbol=instrument.symbol,
            market=instrument.market,
            name=instrument.name,
            backtest_config_key=config_key,
            config_name=config.name,
            provider=config.provider.__name__,
            provider_symbol=config.provider_symbol,
            strategy_class=config.strategy_class.__name__,
        )

        result = serialize_backtest_result(
            stats=stats,
            scope=scope,
            include_equity_curve=True,
            include_trades=True,
        )

        return result

    @staticmethod
    def _validate_ohlcv(df: pd.DataFrame) -> None:
        """验证 OHLCV DataFrame"""
        required_columns = {"Open", "High", "Low", "Close"}
        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(f"数据缺少必需列: {missing}")

        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("数据索引必须是 DatetimeIndex")

        if not df.index.is_monotonic_increasing:
            raise ValueError("数据索引必须是升序排列")

        if df[["Open", "High", "Low", "Close"]].isnull().values.any():
            raise ValueError("OHLC 列存在空值，请先处理缺失数据")
