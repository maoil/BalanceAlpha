"""
基于 Python 策略代码生成交易信号

读取产品绑定的策略配置，运行策略逻辑判断买入/卖出信号。
"""
import logging
from datetime import date, timedelta
from typing import Optional, Dict, Any, List

import pandas as pd

from app.extensions import db
from app.models.instrument import Instrument
from app.backtesting.registry import get_config_by_key, BacktestConfig

logger = logging.getLogger(__name__)


class StrategySignalService:
    """基于 Python 策略代码的信号生成服务"""

    @staticmethod
    def _format_index_date(index_value) -> str:
        if hasattr(index_value, "date"):
            return index_value.date().isoformat()
        return str(index_value)

    @staticmethod
    def _next_execution_date(signal_date: str) -> str:
        current = date.fromisoformat(signal_date) + timedelta(days=1)
        while current.weekday() >= 5:
            current += timedelta(days=1)
        return current.isoformat()

    @staticmethod
    def _execution_context(signal_date: str, source_type: str) -> Dict[str, Any]:
        execution_date = StrategySignalService._next_execution_date(signal_date)
        return {
            "signal_date": signal_date,
            "execution_date": execution_date,
            "execution_timing": "T+1 15:00前",
            "execution_price_known": False,
            "execution_price_note": (
                "基金按执行日净值成交，信号生成时执行日净值未知；"
                "建议结合执行日盘中跟踪标的走势控制追高和转弱风险。"
            ),
            "risk_filter": {
                "enabled": True,
                "source": source_type,
                "suggestion": (
                    "买入信号次日若跟踪标的大涨过多、明显转弱或跌破关键均线，"
                    "可降低仓位或取消买入；卖出信号优先执行。"
                ),
            },
        }

    @staticmethod
    def generate_signal_for_instrument(instrument_id: int) -> Dict[str, Any]:
        """
        为单个产品生成策略信号
        
        Args:
            instrument_id: 产品 ID
            
        Returns:
            包含信号信息的字典
        """
        instrument = db.session.get(Instrument, instrument_id)
        if not instrument:
            return {"error": "产品不存在", "instrument_id": instrument_id}
        
        config_key = instrument.backtest_config_key
        if not config_key:
            return {
                "instrument_id": instrument_id,
                "symbol": instrument.symbol,
                "name": instrument.name,
                "signal": "无策略",
                "explanation": "该产品未绑定回测策略",
            }
        
        config = get_config_by_key(config_key)
        if not config:
            return {
                "instrument_id": instrument_id,
                "symbol": instrument.symbol,
                "name": instrument.name,
                "signal": "配置错误",
                "explanation": f"找不到策略配置: {config_key}",
            }
        
        return StrategySignalService._evaluate_strategy(instrument, config)

    @staticmethod
    def _evaluate_strategy(
        instrument: Instrument,
        config: BacktestConfig,
    ) -> Dict[str, Any]:
        """
        运行策略逻辑评估当前信号
        
        对于被动基金，如果配置了追踪指数(tracking_index)，优先使用指数数据生成信号。
        """
        from app.backtesting.providers import sina_etf_daily
        
        try:
            # 获取历史数据
            end_date = date.today().isoformat()
            start_date = (date.today() - timedelta(days=config.warmup_days + 60)).isoformat()
            
            # 检查是否有追踪标的（ETF/指数），优先使用实时数据
            tracking_index = getattr(instrument, 'tracking_index', None)
            data_source = "基金净值"
            source_type = "fund_nav"
            
            if tracking_index:
                try:
                    df = sina_etf_daily(tracking_index, start=start_date, end=end_date)
                    data_source = f"追踪标的 {tracking_index}"
                    source_type = "tracking_index"
                    logger.info(f"使用追踪标的数据: {tracking_index} for {instrument.symbol}")
                except Exception as e:
                    logger.warning(f"获取追踪标的数据失败，回退到基金净值: {e}")
                    df = config.provider(config.provider_symbol, start=start_date, end=end_date)
            else:
                df = config.provider(config.provider_symbol, start=start_date, end=end_date)
            
            if df.empty or len(df) < 20:
                return {
                    "instrument_id": instrument.id,
                    "symbol": instrument.symbol,
                    "name": instrument.name,
                    "strategy": config.name,
                    "signal": "数据不足",
                    "explanation": f"行情数据不足，需要至少 20 条记录，当前 {len(df)} 条",
                }
            
            # 添加指标
            if config.prepare_data:
                df = config.prepare_data(df)
            
            # 获取最新一行数据用于信号判断
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else latest
            signal_date = StrategySignalService._format_index_date(latest.name)
            
            # 根据策略类型判断信号
            signal_result = StrategySignalService._check_signal(
                config, latest, prev, config.default_params
            )
            
            return {
                "instrument_id": instrument.id,
                "symbol": instrument.symbol,
                "name": instrument.name,
                "strategy": config.name,
                **StrategySignalService._execution_context(signal_date, source_type),
                "signal": signal_result["signal"],
                "signal_type": signal_result["type"],
                "explanation": signal_result["explanation"],
                "latest_price": float(latest["Close"]),
                "latest_date": signal_date,
                "data_source": data_source,
                "indicators": signal_result.get("indicators", {}),
            }
            
        except Exception as e:
            logger.exception("策略信号生成失败: %s", instrument.symbol)
            return {
                "instrument_id": instrument.id,
                "symbol": instrument.symbol,
                "name": instrument.name,
                "strategy": config.name,
                "signal": "错误",
                "explanation": f"策略执行失败: {str(e)}",
            }

    @staticmethod
    def _check_signal(
        config: BacktestConfig,
        latest: pd.Series,
        prev: pd.Series,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        根据策略逻辑检查当前信号
        """
        strategy_name = config.strategy_class.__name__
        
        # CS人工智能策略
        if strategy_name == "CSAIMomentumStrategy":
            return StrategySignalService._check_cs_ai_signal(latest, prev, params)
        
        # Donchian Momentum 策略
        if strategy_name == "DonchianMomentumChaser":
            return StrategySignalService._check_donchian_signal(latest, prev, params)
        
        # Fund Momentum Breakout 策略
        if strategy_name == "FundMomentumBreakout":
            return StrategySignalService._check_fund_momentum_signal(latest, prev, params)
        
        return {
            "signal": "未知",
            "type": "unknown",
            "explanation": f"不支持的策略类型: {strategy_name}",
        }

    @staticmethod
    def _check_cs_ai_signal(
        latest: pd.Series,
        prev: pd.Series,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        CS人工智能策略信号检查
        
        买入条件：
        - 价格突破近10日高点
        - 10日涨幅 >= 6%
        - 价格站上20日均线
        
        卖出条件：
        - 价格跌破近10日低点
        - 或跌破20日均线
        """
        price = float(latest["Close"])
        hh10 = float(prev.get("HH10", 0))
        ll10 = float(prev.get("LL10", 0))
        sma20 = float(latest.get("SMA20", 0))
        roc10 = float(latest.get("ROC10", 0))
        min_momentum = params.get("min_momentum", 0.06)
        
        indicators = {
            "price": price,
            "hh10": hh10,
            "ll10": ll10,
            "sma20": sma20,
            "roc10": f"{roc10:.2%}",
            "min_momentum": f"{min_momentum:.0%}",
        }
        
        # 检查买入条件
        breakout = price > hh10 if hh10 > 0 else False
        momentum_ok = roc10 >= min_momentum
        above_ma = price > sma20 if sma20 > 0 else False
        
        if breakout and momentum_ok and above_ma:
            return {
                "signal": "买入",
                "type": "buy",
                "explanation": f"价格 {price:.4f} 突破10日高点 {hh10:.4f}，10日涨幅 {roc10:.2%} >= {min_momentum:.0%}，站上20日均线 {sma20:.4f}",
                "indicators": indicators,
            }
        
        # 检查卖出条件
        break_low = price < ll10 if ll10 > 0 else False
        below_ma = price < sma20 if sma20 > 0 else False
        
        if break_low:
            return {
                "signal": "卖出",
                "type": "sell",
                "explanation": f"价格 {price:.4f} 跌破10日低点 {ll10:.4f}，触发止损",
                "indicators": indicators,
            }
        
        if below_ma:
            return {
                "signal": "卖出",
                "type": "sell",
                "explanation": f"价格 {price:.4f} 跌破20日均线 {sma20:.4f}，趋势转弱",
                "indicators": indicators,
            }
        
        # 观望
        reasons = []
        if not breakout:
            reasons.append(f"未突破10日高点({hh10:.4f})")
        if not momentum_ok:
            reasons.append(f"10日涨幅({roc10:.2%})未达{min_momentum:.0%}")
        if not above_ma:
            reasons.append(f"未站上20日均线({sma20:.4f})")
        
        return {
            "signal": "观望",
            "type": "hold",
            "explanation": "；".join(reasons) if reasons else "等待信号",
            "indicators": indicators,
        }

    @staticmethod
    def _check_donchian_signal(
        latest: pd.Series,
        prev: pd.Series,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Donchian Momentum 策略信号检查"""
        price = float(latest["Close"])
        hh20 = float(prev.get("HH20", 0))
        ll20 = float(prev.get("LL20", 0))
        sma20 = float(latest.get("SMA20", 0))
        roc20 = float(latest.get("ROC20", 0))
        min_momentum = params.get("min_momentum", 0.06)
        
        indicators = {
            "price": price,
            "hh20": hh20,
            "ll20": ll20,
            "sma20": sma20,
            "roc20": f"{roc20:.2%}",
        }
        
        breakout = price > hh20 if hh20 > 0 else False
        momentum_ok = roc20 >= min_momentum
        above_ma = price > sma20 if sma20 > 0 else False
        
        if breakout and momentum_ok and above_ma:
            return {
                "signal": "买入",
                "type": "buy",
                "explanation": f"价格 {price:.4f} 突破20日高点，动量 {roc20:.2%}，站上均线",
                "indicators": indicators,
            }
        
        break_low = price < ll20 if ll20 > 0 else False
        below_ma = price < sma20 if sma20 > 0 else False
        
        if break_low or below_ma:
            return {
                "signal": "卖出",
                "type": "sell",
                "explanation": f"价格跌破{'20日低点' if break_low else '20日均线'}",
                "indicators": indicators,
            }
        
        return {
            "signal": "观望",
            "type": "hold",
            "explanation": "等待突破信号",
            "indicators": indicators,
        }

    @staticmethod
    def _check_fund_momentum_signal(
        latest: pd.Series,
        prev: pd.Series,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fund Momentum Breakout 策略信号检查"""
        price = float(latest["Close"])
        sma3 = float(latest.get("SMA3", 0))
        sma5 = float(latest.get("SMA5", 0))
        roc20 = float(latest.get("ROC20", 0))
        min_momentum = params.get("min_momentum", 0.02)
        
        indicators = {
            "price": price,
            "sma3": sma3,
            "sma5": sma5,
            "roc20": f"{roc20:.2%}",
        }
        
        momentum_ok = roc20 >= min_momentum
        above_entry_ma = price > sma3 if sma3 > 0 else False
        
        if momentum_ok and above_entry_ma:
            return {
                "signal": "买入",
                "type": "buy",
                "explanation": f"动量 {roc20:.2%} >= {min_momentum:.0%}，价格站上3日均线",
                "indicators": indicators,
            }
        
        momentum_negative = roc20 < 0
        below_exit_ma = price < sma5 if sma5 > 0 else False
        
        if momentum_negative or below_exit_ma:
            return {
                "signal": "卖出",
                "type": "sell",
                "explanation": f"{'动量转负' if momentum_negative else '跌破5日均线'}",
                "indicators": indicators,
            }
        
        return {
            "signal": "观望",
            "type": "hold",
            "explanation": "等待买入条件满足",
            "indicators": indicators,
        }

    @staticmethod
    def generate_all_signals() -> List[Dict[str, Any]]:
        """
        为所有绑定了策略的产品生成信号
        """
        instruments = Instrument.query.filter(
            Instrument.backtest_config_key != "",
            Instrument.backtest_config_key.isnot(None),
            Instrument.status == "active",
        ).all()
        
        results = []
        for instrument in instruments:
            result = StrategySignalService.generate_signal_for_instrument(instrument.id)
            results.append(result)
        
        logger.info("策略信号生成完成: %d 个产品", len(results))
        return results
