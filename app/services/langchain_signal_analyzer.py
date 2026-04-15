"""
LangChain 信号分析子层
模型提供商：阿里云 DashScope（OpenAI 兼容模式）
适用于 Qwen3 系列模型（qwen3.6-plus 等）
"""
import json
import logging
import os
import re
import traceback

from langchain_openai import ChatOpenAI

from app.services.ai_analysis_schema import SignalAIAnalysisResult
from app.services.ai_prompt_builder import AIPromptBuilder

logger = logging.getLogger(__name__)

# DashScope OpenAI 兼容端点（Qwen3 系列必须走此端点）
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class LangChainSignalAnalyzer:
    @staticmethod
    def get_model() -> ChatOpenAI:
        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        model_name = os.getenv("AI_MODEL_NAME", "qwen-plus")

        logger.info(
            "[LangChainSignalAnalyzer] get_model: model=%s, api_key_present=%s, api_key_prefix=%s",
            model_name,
            bool(api_key),
            api_key[:8] + "..." if len(api_key) > 8 else "(empty)",
        )

        if not api_key:
            raise ValueError("缺少 DASHSCOPE_API_KEY，无法生成 AI 分析")

        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=DASHSCOPE_BASE_URL,
            temperature=0.2,
        )

    @staticmethod
    def analyze(snapshot: dict) -> SignalAIAnalysisResult:
        signal_id = snapshot.get("signal", {}).get("id", "unknown")
        logger.info("[LangChainSignalAnalyzer] analyze start: signal_id=%s", signal_id)

        # ── Step 1: 构建 Prompt ──────────────────────────────────────────────
        try:
            system_prompt, user_prompt = AIPromptBuilder.build_signal_analysis_messages(snapshot)
            logger.debug(
                "[LangChainSignalAnalyzer] prompt built: system_len=%d, user_len=%d",
                len(system_prompt),
                len(user_prompt),
            )
        except Exception:
            logger.error("[LangChainSignalAnalyzer] 构建 Prompt 失败:\n%s", traceback.format_exc())
            raise

        # ── Step 2: 初始化模型 ───────────────────────────────────────────────
        try:
            model = LangChainSignalAnalyzer.get_model()
            logger.info(
                "[LangChainSignalAnalyzer] 模型初始化成功: model=%s, base_url=%s",
                model.model_name,
                DASHSCOPE_BASE_URL,
            )
        except Exception:
            logger.error("[LangChainSignalAnalyzer] 模型初始化失败:\n%s", traceback.format_exc())
            raise

        # ── Step 3: 调用 API ─────────────────────────────────────────────────
        try:
            logger.info("[LangChainSignalAnalyzer] 调用 DashScope API (OpenAI 兼容模式)...")
            response = model.invoke([
                ("system", system_prompt),
                ("human", user_prompt),
            ])
            logger.info(
                "[LangChainSignalAnalyzer] API 调用成功: response_type=%s",
                type(response).__name__,
            )
        except Exception:
            logger.error("[LangChainSignalAnalyzer] API 调用失败:\n%s", traceback.format_exc())
            raise

        # ── Step 4: 提取原始文本 ─────────────────────────────────────────────
        try:
            raw_text = response.content.strip()
            logger.info(
                "[LangChainSignalAnalyzer] 原始响应(前500字符): %s",
                raw_text[:500],
            )
        except Exception:
            logger.error("[LangChainSignalAnalyzer] 读取 response.content 失败:\n%s", traceback.format_exc())
            raise

        # ── Step 5: 清理 Markdown 代码块 ─────────────────────────────────────
        clean_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        clean_text = re.sub(r"\s*```$", "", clean_text).strip()
        if clean_text != raw_text:
            logger.info("[LangChainSignalAnalyzer] 已去除 markdown 代码块包裹")
        logger.debug("[LangChainSignalAnalyzer] 清理后文本: %s", clean_text[:500])

        # ── Step 6: Pydantic 解析 ────────────────────────────────────────────
        try:
            result = SignalAIAnalysisResult.model_validate_json(clean_text)
            logger.info(
                "[LangChainSignalAnalyzer] Pydantic 解析成功: summary=%s, confidence=%s, stance=%s",
                result.summary[:50] if result.summary else "",
                result.confidence,
                result.stance,
            )
        except Exception:
            logger.error(
                "[LangChainSignalAnalyzer] Pydantic 解析失败，原始文本:\n%s\n\ntraceback:\n%s",
                clean_text,
                traceback.format_exc(),
            )
            raise

        # ── Step 7: 填充 model_name ──────────────────────────────────────────
        if not result.model_name:
            result.model_name = model.model_name or os.getenv("AI_MODEL_NAME", "qwen-plus")

        logger.info(
            "[LangChainSignalAnalyzer] analyze done: signal_id=%s, model_name=%s",
            signal_id,
            result.model_name,
        )
        return result
