"""
AI 分析提示词构造
"""
import json


from pathlib import Path
from typing import Optional


class AIPromptBuilder:
    PROMPT_VERSION = "v2"
    CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / ".ai_config" / "signal_analysis"

    # 默认回退的 OUTPUT_SCHEMA
    DEFAULT_OUTPUT_SCHEMA = """
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
    def _read_text(path: Path) -> Optional[str]:
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        return content or None

    @staticmethod
    def build_signal_analysis_messages(snapshot: dict, extra_prompt: Optional[str] = None) -> tuple[str, str]:
        sections = []

        # 1. 基础系统提示
        sections.append("以下是你的基础系统指令：")

        # 2. 附加指令 (Additional Instructions)
        if extra_prompt:
            sections.extend(["# 附加指令 (Extra Instructions)", extra_prompt.strip()])

        # 3. 具体人格设定 (Identity)
        identity_path = AIPromptBuilder.CONFIG_DIR / "identity.md"
        if identity := AIPromptBuilder._read_text(identity_path):
            sections.extend(["# 角色与设定 (Identity)", identity])
        else:
            sections.extend(["# 角色与设定 (Identity)", "你是一个专注、客观且资深的投资组合与量化信号分析助手。"])

        # 4. 核心灵魂与原则 (Core Rules / Soul)
        rules_path = AIPromptBuilder.CONFIG_DIR / "core_rules.md"
        if rules := AIPromptBuilder._read_text(rules_path):
            sections.extend(["# 核心规则与约束 (Core Rules)", rules])
        else:
            sections.extend([
                "# 核心规则与约束 (Core Rules)", 
                "你的任务不是替代规则引擎做交易决策，而是基于给定的结构化信号数据，提供：\n"
                "1. 对规则信号的可解释说明\n"
                "2. 风险提示\n"
                "3. 执行建议\n"
                "4. 置信度判断（0.0-1.0）\n\n"
                "约束：\n"
                "- 不要编造输入中不存在的数据\n"
                "- 不要修改原始规则信号\n"
                "- 语言要简洁、专业、克制\n"
                "- 如果数据不足，明确指出"
            ])

        # 5. 用户画像系统 (User Profile)
        user_path = AIPromptBuilder.CONFIG_DIR / "user_profile.md"
        if user_profile := AIPromptBuilder._read_text(user_path):
            sections.extend(["# 用户画像 (User Profile)", user_profile])

        # 6. 首次运行引导 (Bootstrap)
        bootstrap_path = AIPromptBuilder.CONFIG_DIR / "bootstrap.md"
        if bootstrap := AIPromptBuilder._read_text(bootstrap_path):
            sections.extend(["# 初始引导 (Bootstrap)", bootstrap])

        # 7. 输出格式约束
        output_format_path = AIPromptBuilder.CONFIG_DIR / "output_format.md"
        if output_format := AIPromptBuilder._read_text(output_format_path):
            sections.extend(["# 输出格式约束 (Output Requirements)", output_format])
        else:
            sections.extend([
                "# 输出格式约束 (Output Requirements)", 
                "【重要】你必须严格以纯 JSON 格式输出，不要包含任何 markdown 代码块、解释性文字或多余符号。\n输出格式示例：\n" + AIPromptBuilder.DEFAULT_OUTPUT_SCHEMA
            ])

        # 8. 运行环境感知 (Workspace Environment)
        sections.extend([
            "# 运行环境感知 (Workspace Context)",
            "- 当前工作流: 离线信号批量分析与可解释性聚合",
            "- 数据格式: Python dict 转换的隔离结构化快照",
            "- 解析环境要求: 输出将被 `pydantic` 无缝反序列化，禁止附加多余标记"
        ])

        system_prompt = "\\n\\n".join(section for section in sections if section and section.strip())

        user_prompt = f"""
请基于以下结构化数据，输出策略建议的 AI 分析（必须为纯 JSON，无需其他多余文字）。

输入数据：
{json.dumps(snapshot, ensure_ascii=False, indent=2)}
""".strip()

        return system_prompt, user_prompt

    @staticmethod
    def build_critique_messages(snapshot: dict, draft_text: str) -> tuple[str, str]:
        sections = []
        sections.append("以下是你的二次审查任务指令：")
        
        critique_path = AIPromptBuilder.CONFIG_DIR / "critique.md"
        if critique := AIPromptBuilder._read_text(critique_path):
            sections.extend(["# 审查与修改准则 (Critique Guidelines)", critique])
        else:
            sections.extend([
                "# 审查与修改准则 (Critique Guidelines)", 
                "请仔细核对初稿内容与原始数据，检查是否存在编造属性、逻辑谬误或违背输出格式要求的现象。纠错后输出最终的结构化 JSON。"
            ])
            
        system_prompt = "\\n\\n".join(section for section in sections if section and section.strip())

        user_prompt = f"""
请审视以下由系统生成的初稿，与原始快照数据进行比对，指出并修改所有的幻觉和矛盾，并**重新输出一份修正后的最终 JSON 结果**。

【原始快照输入数据】
{json.dumps(snapshot, ensure_ascii=False, indent=2)}

【模型初稿输出 (Draft Output)】
{draft_text}

请参考上述要求与数据，直接给出最终修订后的 JSON 格式输出：
""".strip()

        return system_prompt, user_prompt
