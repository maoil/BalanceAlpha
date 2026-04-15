"""
AI 分析服务
"""
import json
import time
from typing import Optional

from app.extensions import db
from app.models.signal import Signal
from app.models.position import Position
from app.models.market_data import MarketData
from app.models.strategy_assignment import StrategyAssignment
from app.models.signal_ai_analysis import SignalAIAnalysis
from app.services.ai_prompt_builder import AIPromptBuilder
from app.services.log_service import LogService
from app.utils.constants import PositionStatus


class AIAnalysisService:
    @staticmethod
    def build_signal_snapshot(signal: Signal) -> dict:
        instrument = signal.instrument
        account = signal.account

        position = Position.query.filter_by(
            account_id=signal.account_id,
            instrument_id=signal.instrument_id,
            position_status=PositionStatus.OPEN.value,
        ).first()

        latest_md = MarketData.query.filter_by(
            instrument_id=signal.instrument_id,
        ).order_by(MarketData.trade_date.desc()).first()

        assignment = StrategyAssignment.query.filter_by(
            account_id=signal.account_id,
            instrument_id=signal.instrument_id,
            status="active",
        ).first()

        return {
            "signal": {
                "id": signal.id,
                "batch_version": signal.batch_version,
                "signal_date": str(signal.signal_date),
                "signal_type": signal.signal_type,
                "priority": signal.priority,
                "reason_code": signal.reason_code,
                "explanation": signal.explanation,
                "score": signal.score,
                "risk_flag": signal.risk_flag,
                "status": signal.status,
            },
            "instrument": {
                "id": instrument.id if instrument else None,
                "symbol": instrument.symbol if instrument else "",
                "name": instrument.name if instrument else "",
                "instrument_type": instrument.instrument_type if instrument else "",
            },
            "account": {
                "id": account.id if account else None,
                "name": account.account_name if account else "",
                "account_type": account.account_type if account else "",
            },
            "position": {
                "quantity": position.quantity if position else 0,
                "avg_cost": position.avg_cost if position else 0,
                "market_price": position.market_price if position else 0,
                "market_value": position.market_value if position else 0,
                "unrealized_pnl": position.unrealized_pnl if position else 0,
                "unrealized_pnl_pct": position.unrealized_pnl_pct if position else 0,
                "weight_in_account": position.weight_in_account if position else 0,
            },
            "market_data": {
                "trade_date": str(latest_md.trade_date) if latest_md else None,
                "close": latest_md.close if latest_md else None,
                "nav": latest_md.nav if latest_md else None,
                "ma20": latest_md.ma20 if latest_md else None,
                "ma60": latest_md.ma60 if latest_md else None,
                "ma120": latest_md.ma120 if latest_md else None,
                "drawdown_60d": latest_md.drawdown_60d if latest_md else None,
                "relative_strength_20d": latest_md.relative_strength_20d if latest_md else None,
            },
            "assignment": {
                "target_weight_lower": assignment.target_weight_lower if assignment else None,
                "target_weight_upper": assignment.target_weight_upper if assignment else None,
                "allow_dca": assignment.allow_dca if assignment else None,
                "allow_rebalance": assignment.allow_rebalance if assignment else None,
            },
        }

    @staticmethod
    def parse_output(analysis: Optional[SignalAIAnalysis]) -> Optional[dict]:
        if not analysis or not analysis.output_json:
            return None
        try:
            return json.loads(analysis.output_json)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def create_analysis(signal_id: int) -> SignalAIAnalysis:
        signal = db.session.get(Signal, signal_id)
        if not signal:
            raise ValueError("signal not found")

        snapshot = AIAnalysisService.build_signal_snapshot(signal)
        started_at = time.time()

        try:
            from app.services.langchain_signal_analyzer import LangChainSignalAnalyzer

            result = LangChainSignalAnalyzer.analyze(snapshot)
            output_payload = result.model_dump()

            record = SignalAIAnalysis(
                signal_id=signal.id,
                analysis_type="signal_explanation",
                provider="langchain_openai",
                model_name=result.model_name,
                prompt_version=AIPromptBuilder.PROMPT_VERSION,
                input_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
                output_json=json.dumps(output_payload, ensure_ascii=False),
                summary=result.summary,
                confidence=result.confidence,
                status="success",
            )
            db.session.add(record)
            db.session.commit()

            LogService.log(
                log_type="signal",
                level="info",
                module="ai_analysis_service",
                message=f"signal_id={signal.id} AI 分析生成成功",
                context={
                    "signal_id": signal.id,
                    "analysis_id": record.id,
                    "model_name": result.model_name,
                    "prompt_version": AIPromptBuilder.PROMPT_VERSION,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                },
            )
            return record
        except Exception as e:
            record = SignalAIAnalysis(
                signal_id=signal.id,
                analysis_type="signal_explanation",
                provider="langchain_openai",
                model_name="",
                prompt_version=AIPromptBuilder.PROMPT_VERSION,
                input_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
                output_json="{}",
                summary="",
                confidence=0.0,
                status="error",
                error_message=str(e),
            )
            db.session.add(record)
            db.session.commit()

            LogService.log(
                log_type="error",
                level="error",
                module="ai_analysis_service",
                message=f"signal_id={signal.id} AI 分析生成失败",
                context={
                    "signal_id": signal.id,
                    "error": str(e),
                    "prompt_version": AIPromptBuilder.PROMPT_VERSION,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                },
            )
            return record

    @staticmethod
    def get_latest_analysis(signal_id: int) -> Optional[SignalAIAnalysis]:
        return SignalAIAnalysis.query.filter_by(
            signal_id=signal_id,
            analysis_type="signal_explanation",
        ).order_by(SignalAIAnalysis.created_at.desc()).first()

    @staticmethod
    def get_latest_analysis_map(signal_ids: list[int]) -> dict[int, SignalAIAnalysis]:
        if not signal_ids:
            return {}

        analyses = SignalAIAnalysis.query.filter(
            SignalAIAnalysis.signal_id.in_(signal_ids),
            SignalAIAnalysis.analysis_type == "signal_explanation",
        ).order_by(
            SignalAIAnalysis.signal_id.asc(),
            SignalAIAnalysis.created_at.desc(),
        ).all()

        latest_map: dict[int, SignalAIAnalysis] = {}
        for analysis in analyses:
            if analysis.signal_id not in latest_map:
                latest_map[analysis.signal_id] = analysis
        return latest_map

    @staticmethod
    def create_batch_analysis(signals: list[Signal]) -> dict:
        results = {
            "total": len(signals),
            "success": 0,
            "error": 0,
            "analysis_ids": [],
        }

        for signal in signals:
            analysis = AIAnalysisService.create_analysis(signal.id)
            results["analysis_ids"].append(analysis.id)
            if analysis.status == "success":
                results["success"] += 1
            else:
                results["error"] += 1

        return results
