"""
LangChain 信号分析子层
"""
import os

from langchain_openai import ChatOpenAI

from app.services.ai_analysis_schema import SignalAIAnalysisResult
from app.services.ai_prompt_builder import AIPromptBuilder


class LangChainSignalAnalyzer:
    @staticmethod
    def get_model() -> ChatOpenAI:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("缺少 OPENAI_API_KEY，无法生成 AI 分析")

        kwargs = {
            "model": os.getenv("AI_MODEL_NAME", "gpt-4o-mini"),
            "api_key": api_key,
            "temperature": 0.2,
        }
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        if base_url:
            kwargs["base_url"] = base_url

        return ChatOpenAI(**kwargs)

    @staticmethod
    def analyze(snapshot: dict) -> SignalAIAnalysisResult:
        system_prompt, user_prompt = AIPromptBuilder.build_signal_analysis_messages(
            snapshot
        )

        model = LangChainSignalAnalyzer.get_model()
        structured_llm = model.with_structured_output(SignalAIAnalysisResult)
        result = structured_llm.invoke([
            ("system", system_prompt),
            ("human", user_prompt),
        ])

        if not result.model_name:
            result.model_name = model.model_name

        return result
