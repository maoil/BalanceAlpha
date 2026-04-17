# 引入反思与自我纠错机制 (Self-Reflection / Critique)

为了提升 AI 分析结果的准确性并减少大模型产生幻觉的概率，计划在 `LangChainSignalAnalyzer` 中引入双步思维链（Two-pass Chain of Thought）机制：即“初稿生成 -> 自我审查修改”流程。

## Proposed Changes

### app/services/ai_prompt_builder.py

- **[MODIFY]** `app/services/ai_prompt_builder.py`: 增加一个新的静态方法 `build_critique_messages(snapshot: dict, draft_json: str) -> tuple[str, str]`。
  - 读取新的外部配置 `critique.md` 作为审核规则。
  - 构建针对“初稿审查”的系统提示词和用户提示词，强制要求模型仔细对比原始 `snapshot` 数据和 `draft_json`，修正逻辑矛盾、幻觉数据，并输出最终的纯 JSON 格式。

### app/services/langchain_signal_analyzer.py

- **[MODIFY]** `app/services/langchain_signal_analyzer.py`: 修改 `analyze` 流程，支持双路调用的串联。
  1. 初次调用 API 获取 `draft_raw_text`（此时容忍一定的幻觉或格式错误，但尽量输出接近目标结构的结果）。
  2. 使用 `AIPromptBuilder.build_critique_messages(snapshot, draft_raw_text)` 构建第二次审查的 Prompts。
  3. 执行第二次 API 调用，获取修正后的最终 `clean_text`。
  4. 使用 Pydantic 解析第二次调用的输出。若解析失败，将增加对应的异常捕获和报错日志，确保错误被记录且不中断主流程。

### 配置文件 (.ai_config/signal_analysis/)

- **[NEW]** `.ai_config/signal_analysis/critique.md`: 新增该文件，存放专门用于第二遍审查的核对清单（Checklist）：
  - 是否编造了输入中不存在的价格/指标？
  - 执行建议是否与最终的观点（stance）矛盾？
  - 务必保证最终输出符合 JSON Schema 规范。

## User Review Required

> [!IMPORTANT]
> 引入自我审查机制意味着**单次信号分析会执行两次 DashScope API 调用**，这将使：
> 1. 单次分析的耗时翻倍（从 2~4 秒可能增加到 5~8 秒左右）。
> 2. Token 的消耗和对应的 API 计费由于附带历史 Context 会由于二次调用的引入增加。
> 
> 请确认是否接受由于准确率提升带来的额外时间和成本开销？如果您批准，我将开始按照此方案落地代码实现。
