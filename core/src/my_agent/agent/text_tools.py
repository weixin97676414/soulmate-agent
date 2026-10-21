

















from __future__ import annotations

import json
import logging
import uuid

from ..llm.base import ToolCall, ToolSpec

logger = logging.getLogger(__name__)



TOOL_BLOCK_TAG = "tool_call"

_INSTRUCTION = """## 工具调用方式

你**没有**原生函数调用能力，需要按下面的约定用文本发起工具调用。

当你要调用某个工具时，在回复中单独输出一个带 `{tag}` 标签的代码块：

  ```{tag}
  {{"name": "工具名", "arguments": {{"参数名": "参数值"}}}}
  ```

规则：
1. 需要调用多个工具时，输出**多个**代码块，每个块一个调用。
2. 代码块里只放 JSON，不要加注释、不要加解释文字。
3. 除了代码块之外的部分会直接展示给用户，所以正文该写什么写什么。
4. 不需要调用工具时，正常回答，不要输出这个代码块。"""


def render_tools_section(tools: list[ToolSpec]) -> str:

    if not tools:
        return ""

    lines = ["## 可用工具", ""]
    for tool in tools:
        lines.append(f"- **{tool.name}**：{tool.description}")
        params = (tool.parameters or {}).get("properties") or {}
        required = set((tool.parameters or {}).get("required") or [])
        if params:
            rendered = []
            for name, spec in params.items():
                kind = (spec or {}).get("type", "any") if isinstance(spec, dict) else "any"
                mark = "（必填）" if name in required else ""
                desc = (spec or {}).get("description", "") if isinstance(spec, dict) else ""
                rendered.append(f"`{name}`: {kind}{mark} {desc}".strip())
            lines.append(f"  参数：{'；'.join(rendered)}")
        else:
            lines.append("  参数：无")
    lines.append("")
    lines.append(_INSTRUCTION.format(tag=TOOL_BLOCK_TAG))
    return "\n".join(lines)


def extract_text_tool_calls(text: str) -> tuple[str, list[ToolCall]]:






    if not text or TOOL_BLOCK_TAG not in text:
        return text, []

    calls: list[ToolCall] = []
    kept: list[str] = []
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("```") and TOOL_BLOCK_TAG in line:
            
            payload: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                payload.append(lines[index])
                index += 1
            
            index += 1
            call = _parse_block("\n".join(payload))
            if call is None:
                
                
                kept.append("```" + TOOL_BLOCK_TAG)
                kept.extend(payload)
                kept.append("```")
            else:
                calls.append(call)
            continue
        kept.append(line)
        index += 1

    if not calls:
        return text, []

    cleaned = "\n".join(kept).strip()
    return cleaned, calls


def _parse_block(payload: str) -> ToolCall | None:
    payload = payload.strip()
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logger.debug("文本工具调用块不是合法 JSON，按普通文本处理: %s", payload[:200])
        return None
    if not isinstance(data, dict):
        return None

    name = data.get("name") or data.get("tool")
    if not isinstance(name, str) or not name.strip():
        return None

    arguments = data.get("arguments")
    if arguments is None:
        arguments = data.get("params")
    if not isinstance(arguments, dict):
        arguments = {}

    return ToolCall(
        id=f"text_{uuid.uuid4().hex[:8]}",
        name=name.strip(),
        arguments=arguments,
        
        raw_arguments=json.dumps(arguments, ensure_ascii=False),
    )
