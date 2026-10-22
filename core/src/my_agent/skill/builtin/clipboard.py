















from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...utils import windows_api
from ..base import BaseSkill, SkillContext
from ..decorator import skill

logger = logging.getLogger(__name__)


MAX_ECHO_CHARS = 2000


def _to_skill_error(exc: windows_api.WindowsApiError) -> SkillExecutionError:





    text = exc.message if not exc.detail else f"{exc.message}（{exc.detail}）"
    return SkillExecutionError(text)


class ClipboardReadTextParams(BaseModel):
    pass


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
