"""剪贴板技能：读文本、读图片、写文本、写图片。

## 为什么这算"桌面端优势能力"

模型自己既看不见剪贴板也写不进去。没有这两个技能时，用户只能听到
"请你把刚才那段复制一下、再粘到 XX 里" —— 而这恰恰是桌面端最该替用户做的事。

## 权限分级

- 读**文本** safe：不改任何东西；
- 读**图片** confirm：它会把剪贴板里的图片落成产物文件（剪贴板可能含私密截图，
  落盘是"改动"）；
- 写文本 / 写图片 confirm：会覆盖用户当前的剪贴板内容 —— 用户正在复制粘贴的
  东西被顶掉是很烦的事，所以必须让他点一下。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...utils import windows_api
from ..base import BaseSkill, SkillContext
from ..decorator import skill

logger = logging.getLogger(__name__)

# 剪贴板里可能是一整篇文档；这里只做**回显长度**的上报，不截断内容本身
MAX_ECHO_CHARS = 2000


def _to_skill_error(exc: windows_api.WindowsApiError) -> SkillExecutionError:
    """系统能力失败 → 技能错误。

    必须转换：技能层抛别的异常类型会让整轮对话以一个看不懂的 400 收场，
    而用户需要看到的是"这台机器不支持调亮度"这种人话。
    """
    text = exc.message if not exc.detail else f"{exc.message}（{exc.detail}）"
    return SkillExecutionError(text)


class ClipboardReadTextParams(BaseModel):
    """读剪贴板文本不需要参数 —— 保留空模型是为了让装饰器能生成 schema。"""


@skill(
    name="clipboard_read_text",
    display_name="读剪贴板文本",
    description=(
        "读取系统剪贴板里的文本内容。当用户说「把剪贴板里的内容整理一下」"
        "「我复制的那段话你看到了吗」「看看我复制了什么」时使用。"
        "剪贴板里没有文本时返回空内容（不是错误）。"
    ),
    params_model=ClipboardReadTextParams,
    category="system",
    permission_level="safe",
    tags=["剪贴板", "桌面能力"],
)
class ClipboardReadTextSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        ClipboardReadTextParams(**params)
        try:
            text = windows_api.read_clipboard_text()
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc

        if not text:
            return {"text": "", "length": 0, "message": "剪贴板里没有文本内容。"}
        # 日志只记长度：剪贴板里可能是密码、验证码、私聊内容
        logger.info("读取剪贴板文本（%s 字符）", len(text))
        return {
            "text": text,
            "length": len(text),
            "preview": text[:MAX_ECHO_CHARS],
        }


class ClipboardReadImageParams(BaseModel):
    pass


@skill(
    name="clipboard_read_image",
    display_name="读取剪贴板图片",
    description=(
        "把剪贴板里的图片保存成文件（PNG），保存后可在产物区预览，也能继续交给"
        "其它步骤处理。当用户说「把截图给你」「刚截的图存下来」时使用。"
        "剪贴板里没有图片时会如实告知（截图工具通常按 Ctrl+C 才会进剪贴板）。"
    ),
    params_model=ClipboardReadImageParams,
    category="system",
    permission_level="confirm",
    tags=["剪贴板", "截图", "桌面能力"],
)
class ClipboardReadImageSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        ClipboardReadImageParams(**params)
        target = ctx.artifact_output("clipboard-image.png")
        try:
            saved = await windows_api.save_clipboard_image(target)
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc

        if not saved:
            return {
                "saved": False,
                "message": "剪贴板里没有图片。截图后需要在截图工具里点「复制」，图片才会进剪贴板。",
            }

        artifact = await ctx.register_artifact(target, note="来自剪贴板")
        return {
            "saved": True,
            "path": str(target),
            "artifact": artifact,
            "message": "剪贴板里的图片已保存，可在右侧产物区预览。",
        }


class ClipboardWriteParams(BaseModel):
    text: str | None = Field(
        None, description="要放进剪贴板的文本；与 image_path 二选一"
    )
    image_path: str | None = Field(
        None, description="要放进剪贴板的图片路径（需在白名单目录内）；与 text 二选一"
    )


@skill(
    name="clipboard_write",
    display_name="写入剪贴板",
    description=(
        "把一段文本或一张图片放进系统剪贴板，用户可以直接粘贴到别的程序里。"
        "当用户说「把结果放到剪贴板」「这些内容我要粘到邮件里」「把这张图复制给我」时使用。"
        "会覆盖剪贴板原有内容，所以只在用户明确要求时调用。"
    ),
    params_model=ClipboardWriteParams,
    category="system",
    permission_level="confirm",
    tags=["剪贴板", "桌面能力"],
)
class ClipboardWriteSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ClipboardWriteParams(**params)
        if (args.text is None) == (args.image_path is None):
            raise SkillExecutionError("请提供 text（文本）或 image_path（图片路径）中的**一个**。")

        try:
            if args.text is not None:
                windows_api.write_clipboard_text(args.text)
                return {
                    "ok": True,
                    "kind": "text",
                    "length": len(args.text),
                    "message": f"已把 {len(args.text)} 个字符放进剪贴板。",
                }

            source = ctx.resolve_input_file(args.image_path or "")
            await windows_api.set_clipboard_image(source)
            return {
                "ok": True,
                "kind": "image",
                "path": str(source),
                "message": "已把图片放进剪贴板，可以直接粘贴到其它程序。",
            }
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
