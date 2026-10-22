














from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...utils import windows_api
from ..base import BaseSkill, SkillContext
from ..decorator import skill

logger = logging.getLogger(__name__)


def _to_skill_error(exc: windows_api.WindowsApiError) -> SkillExecutionError:
    text = exc.message if not exc.detail else f"{exc.message}（{exc.detail}）"
    return SkillExecutionError(text)


class VolumeParams(BaseModel):
    action: Literal["up", "down", "set", "mute"] = Field(
        ...,
        description=(
            "up=调高一点；down=调低一点；"
            "set=设为指定百分比（要同时给 percent；**会同时解除静音**）；"
            "mute=静音或取消静音（用 muted 明确指定想设成哪一边；不传则把当前状态取反）"
        ),
    )
    percent: int | None = Field(
        None, ge=0, le=100, description="action=set 时的目标音量百分比"
    )
    muted: bool | None = Field(
        None,
        description="action=mute 时：true=静音，false=取消静音；不传则把当前状态取反",
    )


class VolumeGetParams(BaseModel):
    pass


@skill(
    name="system_volume_get",
    display_name="读取音量与静音状态",
    description=(
        "读取当前系统音量百分比与**是否处于静音**。"
        "当用户问「现在音量多大」「是不是静音了」，或你想确认状态再决定怎么调时使用。"
        "不要凭猜测回答这类问题 —— 静音状态是猜不出来的。"
    ),
    params_model=VolumeGetParams,
    category="system",
    permission_level="safe",
    tags=["系统控制", "音量", "桌面能力"],
)
class VolumeGetSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        VolumeGetParams(**params)
        try:
            percent, muted = await windows_api.get_volume_state()
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        return {
            "ok": True,
            "percent": percent,
            "muted": muted,
            "message": f"当前音量 {percent}%{'，已静音' if muted else ''}。",
        }


@skill(
    name="system_volume",
    display_name="调节音量",
    description=(
        "调节系统音量：调高、调低、静音/取消静音，或设为指定百分比。"
        "当用户说「声音小一点」「静音」「取消静音」「音量调到 30%」时使用。"
        "调高/调低是按系统的默认步进走，只改一点，不会一下子拉满。"
        "**set 与 mute 都会返回操作后的真实音量与是否静音**（set 还会自动解除静音），"
        "所以不要凭猜测回答「现在静音了吗」—— 要读状态请用 system_volume_get。"
    ),
    params_model=VolumeParams,
    category="system",
    permission_level="confirm",
    tags=["系统控制", "音量", "桌面能力"],
)
class VolumeSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = VolumeParams(**params)
        try:
            if args.action == "set":
                if args.percent is None:
                    raise SkillExecutionError("action=set 时必须给出 percent（0-100）。")
                percent, muted = await windows_api.set_volume_percent(args.percent)
                tail = "（已同时解除静音）。" if not muted else "（仍在静音状态）。"
                return {
                    "ok": True,
                    "action": "set",
                    "percent": percent,
                    "muted": muted,
                    "message": f"音量已设为 {percent}%" + tail,
                }

            if args.action == "mute":
                
                
                target = args.muted
                if target is None:
                    _, current = await windows_api.get_volume_state()
                    target = not current
                percent, muted = await windows_api.set_muted(target)
                return {
                    "ok": True,
                    "action": "mute",
                    "percent": percent,
                    "muted": muted,
                    "message": "已静音。" if muted else "已取消静音。",
                }

            
            
            windows_api.volume_step(args.action)
            action_text = {"up": "调高了一点", "down": "调低了一点"}
            return {
                "ok": True,
                "action": args.action,
                "message": f"音量{action_text.get(args.action, '已调整')}。",
            }
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc


class BrightnessGetParams(BaseModel):
    pass


@skill(
    name="system_brightness_get",
    display_name="读取屏幕亮度",
    description=(
        "读取当前屏幕亮度百分比。当用户问「屏幕现在多亮」或需要先知道当前亮度"
        "再调整时使用。台式机或外接显示器上会明确返回「不支持」，这是硬件限制。"
    ),
    params_model=BrightnessGetParams,
    category="system",
    permission_level="safe",
    tags=["系统控制", "亮度", "桌面能力"],
)
class BrightnessGetSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        BrightnessGetParams(**params)
        try:
            percent = await windows_api.get_brightness()
        except windows_api.WindowsApiError as exc:
            
            return {"supported": False, "message": exc.message}
        return {"supported": True, "percent": percent}


class BrightnessSetParams(BaseModel):
    percent: int | None = Field(
        None, ge=0, le=100, description="直接设置的目标亮度百分比"
    )
    delta: int | None = Field(
        None, ge=-80, le=80, description="相对调整：正数调亮、负数调暗，单位是百分点"
    )


@skill(
    name="system_brightness_set",
    display_name="调节屏幕亮度",
    description=(
        "调节屏幕亮度：给 percent 直接设成指定值，或给 delta 相对调亮/调暗。"
        "当用户说「屏幕太亮了」「调暗一点」「亮度调到 50%」时使用。"
        "仅在笔记本内置屏幕上可用；台式机与外接显示器会如实告知不支持。"
    ),
    params_model=BrightnessSetParams,
    category="system",
    permission_level="confirm",
    tags=["系统控制", "亮度", "桌面能力"],
)
class BrightnessSetSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = BrightnessSetParams(**params)
        if args.percent is None and args.delta is None:
            raise SkillExecutionError("请给出 percent（目标值）或 delta（相对调整量）。")

        try:
            target = args.percent
            if target is None:
                
                current = await windows_api.get_brightness()
                target = max(0, min(100, current + int(args.delta or 0)))
            applied = await windows_api.set_brightness(int(target))
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc

        return {
            "ok": True,
            "percent": applied,
            "message": f"屏幕亮度已调到 {applied}%。",
        }


class LockScreenParams(BaseModel):
    pass


@skill(
    name="system_lock_screen",
    display_name="锁定屏幕",
    description=(
        "立刻锁定 Windows 会话（等同按 Win+L）。当用户说「我要离开了，锁一下屏」"
        "「把电脑锁上」时使用。锁屏后需要重新登录才能继续，属于有意为之的操作。"
    ),
    params_model=LockScreenParams,
    category="system",
    permission_level="confirm",
    tags=["系统控制", "锁屏", "桌面能力"],
)
class LockScreenSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        LockScreenParams(**params)
        try:
            windows_api.lock_workstation()
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        return {"ok": True, "message": "屏幕已锁定。"}


class ScreenshotParams(BaseModel):
    x: int | None = Field(None, description="区域截图：左上角横坐标（整屏截图不用填）")
    y: int | None = Field(None, description="区域截图：左上角纵坐标")
    width: int | None = Field(None, gt=0, description="区域截图：宽度像素")
    height: int | None = Field(None, gt=0, description="区域截图：高度像素")
    also_copy_to_clipboard: bool = Field(
        False, description="截完是否顺手放进剪贴板（用户要「截了直接粘」时用）"
    )
    output_name: str | None = Field(None, description="产物文件名，留空自动生成")


@skill(
    name="system_screenshot",
    display_name="屏幕截图",
    description=(
        "截取屏幕并保存成图片。不填区域时截**所有显示器拼起来的整个桌面**；"
        "填了 x/y/width/height 就只截那一块。当用户说「截个屏」「把屏幕截下来」"
        "「截取左上角那块区域」时使用。截图会出现在右侧产物区，可直接预览。"
    ),
    params_model=ScreenshotParams,
    category="system",
    permission_level="confirm",
    tags=["系统控制", "截图", "桌面能力"],
)
class ScreenshotSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ScreenshotParams(**params)
        region = None
        provided = [args.x, args.y, args.width, args.height]
        if any(item is not None for item in provided):
            if not all(item is not None for item in provided):
                raise SkillExecutionError(
                    "区域截图需要同时给出 x、y、width、height 四个值；整屏截图则都不要填。"
                )
            region = (int(args.x or 0), int(args.y or 0), int(args.width or 0), int(args.height or 0))

        target = ctx.artifact_output(args.output_name or "screenshot.png")
        if target.suffix.lower() != ".png":
            target = target.with_suffix(".png")

        try:
            await windows_api.capture_screen(target, region=region)
            copied = False
            if args.also_copy_to_clipboard:
                try:
                    await windows_api.set_clipboard_image(target)
                    copied = True
                except windows_api.WindowsApiError as exc:
                    
                    logger.warning("截图已保存但复制到剪贴板失败：%s", exc.message)
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc

        artifact = await ctx.register_artifact(target, note="屏幕截图")
        return {
            "path": str(target),
            "artifact": artifact,
            "region": None if region is None else list(region),
            "copied_to_clipboard": copied,
            "message": "截图已保存，可在右侧产物区预览。"
            + ("也已放进剪贴板。" if copied else ""),
        }
