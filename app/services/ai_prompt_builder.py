"""
AI 分析提示词构造
"""
import json


class AIPromptBuilder:
    PROMPT_VERSION = "v1"

    # 输出 JSON schema（与 SignalAIAnalysisResult 字段对应）
    OUTPUT_SCHEMA = """
{
  "summary": "一句话总结（字符串）",
  "reasoning": ["主要分析依据1", "主要分析依据2"],
  "risks": ["风险提示1", "风险提示2"],
  "action_suggestion": "执行建议（字符串）",
  "confidence": 0.85,
  "stance": "support | neutral | cautious",
  "model_name": ""
}""".strip()

    @staticmethod
    def build_signal_analysis_messages(snapshot: dict) -> tuple[str, str]:
        system_prompt = f"""
你是一个投资分析解释助手。
你的任务不是替代规则引擎做交易决策，而是基于给定的结构化信号数据，提供：
1. 对规则信号的可解释说明
2. 风险提示
3. 执行建议
4. 置信度判断（0.0-1.0）

约束：
- 不要编造输入中不存在的数据
- 不要修改原始规则信号
- 语言要简洁、专业、克制
- 如果数据不足，明确指出

【重要】你必须严格以纯 JSON 格式输出，不要包含任何 markdown 代码块、解释性文字或多余符号。
输出格式示例：
{AIPromptBuilder.OUTPUT_SCHEMA}
""".strip()

        user_prompt = f"""
请基于以下结构化数据，输出策略建议的 AI 分析（纯 JSON）。

输入数据：
{json.dumps(snapshot, ensure_ascii=False, indent=2)}
""".strip()

        return system_prompt, user_prompt
