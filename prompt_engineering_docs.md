# 提示词工程 (Prompt Engineering) 架构与开发文档

本文档总结了 `ohmo/prompts.py` 中采用的提示词组装策略与模式。该系统采用了高度模块化、动态文件注入以及上下文分层管理的提示词工程架构，非常适合移植到其他需要处理复杂和持久化 AI 上下文的项目中。

## 🎯 核心设计思想：模块化与动态组装 (Modular & Dynamic Assembly)

系统没有将系统提示词（System Prompt）硬编码为一个庞大的字符串，而是利用工厂函数 `build_ohmo_system_prompt`，从多个不同的来源动态拼接提示词。这样做的好处是：
1. **解耦**：人格（Identity）、规则（Soul）、用户偏好（User Profile）可以独立维护和更新。
2. **可配置性**：通过读取本地文本文件，终端用户无需修改代码即可定义 AI 的默认行为，而不必干预底层代码。
3. **高扩展性**：在需要支持新能力（如新增加工具说明或限制）时，直接向构建管道中增加新的 Section 即可。
4. **结构化标记**：采用 Markdown 标题（例如 `# User Profile`）对每个模块进行清晰的定界，方便大语言模型（LLM）准确理解各个维度的信息并正确解析上下文。

## 🧩 提示词层级模块组成 (Prompt Sections)

完整的提示词是按照特定的业务逻辑层级进行纵向拼接的。按照 `ohmo/prompts.py` 的设计，组装流如下：

1. **基础系统提示（Base System Prompt）**：
   - 来源：`get_base_system_prompt()`
   - 作用：定义模型最基础、最核心的引擎能力和通用行为准则。

2. **额外指令（Additional Instructions，可选）**：
   - 来源：运行时传入的 `extra_prompt` 参数。
   - 作用：针对特定任务、会话临时附加的定制化指令。

3. **核心灵魂与原则（Soul，可选）**：
   - 来源：读取本地文件 `soul`
   - 作用：定义不可违背的核心价值观、红线或是必须遵循的基础原则。

4. **具体人格设定（Identity，可选）**：
   - 来源：读取本地文件 `identity`
   - 作用：详尽描述 AI 的身份角色、语气语调、沟通偏好和领域专长。

5. **用户画像系统（User Profile，可选）**：
   - 来源：读取本地文件 `user`
   - 作用：包含关于用户的持久化设定（如技术栈倾向、习惯语言、操作系统型号等），有助于生成高度“懂你”的个性化回复。

6. **首次运行引导（First-Run Bootstrap，可选）**：
   - 来源：读取本地文件 `bootstrap`
   - 作用：如果是在新的环境首次运行，该模块可下发专门的“破冰”任务或初始环境检测指令。

7. **运行环境感知（Workspace Context）**：
   - 来源：代码动态运行时构建
   - 作用：明确告知 AI 它所处的系统环境，如文件系统根目录、数据边界安全隔离规则等。

8. **外部长期记忆（Memory System，可选）**：
   - 来源：`load_ohmo_memory_prompt` 和上下文 `load_project_memory_prompt`
   - 作用：将跨会话或跨项目的结构化长期记忆（Long-term Memory）调取并注入到当前，以保持极强的时间维度任务连贯性。

## 🛠 移植与实现指南 (Implementation Guide for Porting)

当您计划将这套体系移植到新项目时，推荐采用以下代码模式与设计规范：

### 1. 文件树组织规范
在项目的根目录（或专门的 `.config` 隐藏目录），建立独立的文件来承载各个模块的静态文本。可以有效地将业务代码与提示词分离：
```text
.ai_config/
├── identity.md       # "你是一个注重性能优化的资深 Go 开发..."
├── user_profile.md   # "用户偏好全异步设计，系统为 Linux。"
└── core_rules.md     # "永远不要在没有审查的情况下静默覆盖文件..."
```

### 2. 安全的文件读取机制 (Graceful Degradation)
像文件读取这类外部依赖必须容忍缺失（这也是代码中 `_read_text` 的亮眼之处）。部分配置文件不存在时，应静默返回 `None` 而不能引发报错奔溃：
```python
from pathlib import Path
from typing import Optional

def _read_text(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    # 强制采取 UTF-8 并处理解码错误(errors="replace")
    content = path.read_text(encoding="utf-8", errors="replace").strip()
    return content or None
```

### 3. 高效且优雅的字符串拼接
不要到处写 `sectionA + "\n" + sectionB`。应统一初始化一个存储容器（列表），按顺序推入每个逻辑块。最后再借助带有换行缩进的规则统一 `join`。
```python
def build_agent_prompt(workspace_path: Path, extra: str = None) -> str:
    sections = ["这里是顶层的基础 Prompt..."]
    
    # 按照优先级压入块
    if extra:
        sections.extend(["# 附加指令", extra.strip()])
    
    if identity := _read_text(workspace_path / "identity.md"):
        sections.extend(["# Agent 人格角色", identity])
        
    # 其他模块...
        
    # 利用列表推导式过滤无效的空字符串或 None，自动保证段落的间距
    return "\n\n".join(section for section in sections if section and section.strip())
```

### 4. 动态上下文（运行时变量）的强制注入
由于 LLM 本身没有环境感知能力，需要你用代码补全其空间意识：
```python
# 每次构建时都应当反映真实的运行时环境
sections.extend([
    "# 工作空间上下文 (Workspace Context)",
    f"- 当前项目的绝对根路径: {workspace_path.absolute()}",
    "- 边界规则: 请不要尝试操作和推理该路径之外的任何文件和系统目录。"
])
```

## 🚀 总结
这套代码实现了**从“静态提示词工程”向“动态上下文引擎”的跨越**。它通过拆分大篇幅的 Prompt 并分离成外部配置文件，降低了系统演化的维护门槛。此外，结合 Workspace 和 Memory 这两项特性，它能让每一次 AI 推理都自带“全局项目背景”与“用户情感偏好”。
