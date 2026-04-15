"""
AI 分析结果结构定义
"""
from typing import Literal

from pydantic import BaseModel, Field


class SignalAIAnalysisResult(BaseModel):
    summary: str = Field(..., description="一句话总结")
    reasoning: list[str] = Field(default_factory=list, description="主要分析依据")
    risks: list[str] = Field(default_factory=list, description="风险提示")
    action_suggestion: str = Field(..., description="执行建议")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    stance: Literal["support", "neutral", "cautious"] = Field(
        ...,
        description="AI态度",
    )
    model_name: str = Field(default="", description="模型名称")
