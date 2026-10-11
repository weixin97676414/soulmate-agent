"""不支持 Function Calling 的模型的「文本工具」协议。

对应《智能体框架开发文档》4.1 / 4.3.3：模型能力分级要能**驱动行为**，
``supports_tools=false`` 时不该只是把工具禁用掉（那等于砍掉一半功能），
而应降级成"用提示词描述工具 + 解析模型的文本回复"。

## 为什么要约定成 fenced block

纯靠"让模型输出 JSON"是不可靠的：它会夹在解释性文字里、会缺大括号、
会在 JSON 前后加中文说明。用一个**带标签的围栏代码块**当界标，
解析器就能稳定定位，也不会把模型正常回答里的 JSON 误当成工具调用。

## 解析失败怎么办

按普通文本处理，**不报错**。用户看到的就是模型的一段正常回复——
比因为格式不规范而整轮失败要好得多。
"""

from __future__ import annotations

import json
import logging
import uuid

from ..llm.base import ToolCall, ToolSpec

logger = logging.getLogger(__name__)

# 围栏标签。刻意用反引号 + 标签名，而不是只靠 ```：模型经常在回答里
# 放普通代码块（示例代码、JSON 示例），只认三反引号会把它们全当成工具调用。
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
    """把工具清单渲染成注入 system 的说明文本。"""
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
    """从模型的文本回复里抽出工具调用。

    Returns:
        ``(去掉代码块后的正文, 解析出的调用列表)``。
        正文要清掉代码块——否则用户会在气泡里看到一大段原始 JSON。
    """
    if not text or TOOL_BLOCK_TAG not in text:
        return text, []

    calls: list[ToolCall] = []
    kept: list[str] = []
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("```") and TOOL_BLOCK_TAG in line:
            # 找到围栏起点，收集到闭合围栏为止
            payload: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                payload.append(lines[index])
                index += 1
            # 跳过闭合围栏本身
            index += 1
            call = _parse_block("\n".join(payload))
            if call is None:
                # 解析不出来就**原样保留**：宁可让用户看到一段没被识别的文本，
                # 也好过静默吞掉模型实际想调用的内容
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
        # 保留原始串：回填给厂商的格式要与它自己给出的一致
        raw_arguments=json.dumps(arguments, ensure_ascii=False),
    )
