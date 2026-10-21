






























from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from ...errors import SkillExecutionError
from ...utils import windows_api
from ..base import BaseSkill, SkillContext
from ..decorator import skill

logger = logging.getLogger(__name__)



_TAGS = ["电脑操作", "桌面能力"]


def _to_skill_error(exc: windows_api.WindowsApiError) -> SkillExecutionError:
    text = exc.message if not exc.detail else f"{exc.message}（{exc.detail}）"
    return SkillExecutionError(text)





class MouseMoveParams(BaseModel):
    x: int = Field(..., description="目标位置的横坐标（屏幕像素）")
    y: int = Field(..., description="目标位置的纵坐标（屏幕像素）")


@skill(
    name="computer_mouse_move",
    display_name="移动鼠标",
    description=(
        "把鼠标光标移到屏幕上的指定位置（像素坐标）。只移动、不点击。"
        "坐标按**整个虚拟桌面**算：多显示器时第二块屏的 x 可能大于主屏宽度。"
        "**先用 system_screenshot 或 computer_read_screen 看清目标在哪再动** —— "
        "凭猜测给的坐标会点到别的地方。"
    ),
    params_model=MouseMoveParams,
    category="system",
    permission_level="confirm",
    tags=_TAGS,
)
class MouseMoveSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = MouseMoveParams(**params)
        try:
            windows_api.mouse_move(args.x, args.y)
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        return {
            "ok": True,
            "x": args.x,
            "y": args.y,
            "message": f"鼠标已移到 ({args.x}, {args.y})。",
        }


class MouseClickParams(BaseModel):
    x: int = Field(..., description="点击位置的横坐标（屏幕像素）")
    y: int = Field(..., description="点击位置的纵坐标（屏幕像素）")
    button: Literal["left", "right", "middle"] = Field(
        "left", description="鼠标键：left=左键（默认）、right=右键、middle=中键"
    )
    clicks: int = Field(1, ge=1, le=3, description="点几次：1=单击（默认）、2=双击、3=三击")


@skill(
    name="computer_mouse_click",
    display_name="点击鼠标",
    description=(
        "在屏幕指定位置点击鼠标（支持左/右/中键、单击/双击/三击）。"
        "移动与点击在**同一批**里发给系统 —— 中间不会有别的程序把光标挪走。"
        "桌面上要打开某个图标 / 按某个按钮 / 选中某一行，都用它。"
        "坐标来自 computer_read_screen 或 system_screenshot。"
    ),
    params_model=MouseClickParams,
    category="system",
    permission_level="confirm",
    tags=_TAGS,
)
class MouseClickSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = MouseClickParams(**params)
        try:
            windows_api.mouse_click(args.x, args.y, button=args.button, clicks=args.clicks)
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        action = {1: "单击", 2: "双击", 3: "三击"}.get(args.clicks, "连点")
        return {
            "ok": True,
            "x": args.x,
            "y": args.y,
            "message": f"已{action} ({args.x}, {args.y})。",
        }


class MouseScrollParams(BaseModel):
    amount: int = Field(
        ...,
        ge=-20,
        le=20,
        description="滚动格数：正数向上滚、负数向下滚（一格大约三行文字）",
    )


@skill(
    name="computer_mouse_scroll",
    display_name="滚动鼠标滚轮",
    description=(
        "在当前鼠标位置滚动滑轮（正数向上、负数向下）。"
        "用于翻页、看长列表 —— 滚之前先把鼠标移到要滚的区域上（用 computer_mouse_move）。"
    ),
    params_model=MouseScrollParams,
    category="system",
    permission_level="confirm",
    tags=_TAGS,
)
class MouseScrollSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = MouseScrollParams(**params)
        try:
            windows_api.mouse_scroll(args.amount)
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        direction = "上" if args.amount > 0 else "下"
        return {
            "ok": True,
            "message": f"已向{direction}滚动 {abs(args.amount)} 格。",
        }


class MouseDragParams(BaseModel):
    x1: int = Field(..., description="起点横坐标（屏幕像素）")
    y1: int = Field(..., description="起点纵坐标（屏幕像素）")
    x2: int = Field(..., description="终点横坐标（屏幕像素）")
    y2: int = Field(..., description="终点纵坐标（屏幕像素）")
    button: Literal["left", "right", "middle"] = Field(
        "left", description="用哪个键拖：left=左键（默认）、right=右键、middle=中键"
    )


@skill(
    name="computer_mouse_drag",
    display_name="拖拽鼠标",
    description=(
        "按住鼠标从起点拖到终点（选中文字、拖动文件、拉滑块都用它）。"
        "整段拖拽在**一次调用内**完成，中途不会留下「鼠标一直按着」的状态。"
    ),
    params_model=MouseDragParams,
    category="system",
    permission_level="confirm",
    tags=_TAGS,
)
class MouseDragSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = MouseDragParams(**params)
        try:
            await windows_api.mouse_drag(
                args.x1, args.y1, args.x2, args.y2, button=args.button
            )
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        return {
            "ok": True,
            "message": (
                f"已从 ({args.x1}, {args.y1}) 拖到 ({args.x2}, {args.y2})。"
            ),
        }





class TypeTextParams(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="要输入的文字（中文、英文、emoji 都可以）",
    )


@skill(
    name="computer_type_text",
    display_name="输入文字",
    description=(
        "把一段文字打到**当前焦点所在**的输入框里。"
        "⚠️ 它不会自己找输入框 —— 先用 computer_mouse_click 把光标点进那个输入框，"
        "再调它；否则字会打到别处（包括聊天框、搜索框）。"
        "中文与 emoji 都能输入（走系统 Unicode 注入，不受输入法影响）。"
    ),
    params_model=TypeTextParams,
    category="system",
    permission_level="confirm",
    tags=_TAGS,
)
class TypeTextSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = TypeTextParams(**params)
        try:
            await windows_api.type_text(args.text)
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        
        return {
            "ok": True,
            "length": len(args.text),
            "message": f"已输入 {len(args.text)} 个字符。",
        }


class PressKeysParams(BaseModel):
    keys: list[str] = Field(
        ...,
        min_length=1,
        max_length=4,
        description=(
            '要按的键；组合键按顺序给，例如 ["ctrl", "s"]、["alt", "tab"]、["enter"]。'
            "可用键：字母数字、enter / tab / esc / space / backspace / delete / "
            "方向键(up/down/left/right) / home / end / pageup / pagedown / f1-f12 / "
            "ctrl / alt / shift / win"
        ),
    )


@skill(
    name="computer_press_keys",
    display_name="按键",
    description=(
        "按下并松开一组键（组合键）。用来按快捷键（Ctrl+S 保存、Alt+Tab 切窗口）、"
        "或敲回车确认。组合键把修饰键写在前面：[\"ctrl\", \"s\"]。"
    ),
    params_model=PressKeysParams,
    category="system",
    permission_level="confirm",
    tags=_TAGS,
)
class PressKeysSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = PressKeysParams(**params)
        try:
            windows_api.press_keys(args.keys)
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        return {
            "ok": True,
            "message": "已按下 " + " + ".join(args.keys) + "。",
        }





class ListWindowsParams(BaseModel):
    pass


@skill(
    name="computer_list_windows",
    display_name="列出窗口",
    description=(
        "列出当前所有**可见且有标题**的窗口（标题、句柄、是否在前台、位置与尺寸）。"
        "要操作某个程序之前先用它确认那个窗口在不在、叫什么名字 —— "
        "拿它返回的 handle 交给 computer_activate_window 就能把窗口切到前台。"
    ),
    params_model=ListWindowsParams,
    category="system",
    permission_level="confirm",
    tags=_TAGS,
)
class ListWindowsSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        ListWindowsParams(**params)
        try:
            windows = windows_api.list_windows()
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        return {
            "ok": True,
            "count": len(windows),
            "windows": windows,
            "message": f"当前有 {len(windows)} 个可见窗口。",
        }


class ActivateWindowParams(BaseModel):
    handle: int | None = Field(None, description="窗口句柄（来自 computer_list_windows）")
    title: str | None = Field(
        None,
        description="窗口标题（按包含匹配；与 handle 二选一，handle 优先）",
    )


@skill(
    name="computer_activate_window",
    display_name="切换到窗口",
    description=(
        "把指定窗口切到前台。给 handle（最准，来自 computer_list_windows 或 "
        "computer_read_screen）或给 title（按包含匹配）。"
        "切过去之后再对它做鼠标键盘操作。"
        "⚠️ Windows 有前台锁，可能被系统拒绝 —— 那时结果里 ok=false，"
        "请如实告诉用户「系统没允许自动切换，请手动点一下那个窗口」，不要假装切好了。"
    ),
    params_model=ActivateWindowParams,
    category="system",
    permission_level="confirm",
    tags=_TAGS,
)
class ActivateWindowSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ActivateWindowParams(**params)
        wanted = (args.title or "").strip()
        if args.handle is None and not wanted:
            raise SkillExecutionError("请给出窗口句柄（handle）或窗口标题（title）。")

        handle = args.handle
        try:
            if handle is None:
                windows = windows_api.list_windows()
                needle = wanted.lower()
                matches = [item for item in windows if needle in item["title"].lower()]
                if not matches:
                    titles = "、".join(item["title"] for item in windows[:10])
                    
                    
                    raise SkillExecutionError(
                        f"没找到标题包含「{args.title}」的窗口。"
                        f"当前可见窗口有：{titles or '（没有）'}"
                    )
                handle = matches[0]["handle"]
            activated = windows_api.activate_window(handle)
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc

        if not activated:
            return {
                "ok": False,
                "handle": handle,
                "message": (
                    "系统不允许自动把窗口切到前台（Windows 的前台锁）。"
                    "请让用户手动点一下那个窗口，然后再继续。"
                ),
            }
        return {"ok": True, "handle": handle, "message": "已把该窗口切到前台。"}


class LaunchParams(BaseModel):
    target: str = Field(
        ...,
        min_length=1,
        description=(
            "要打开的程序、文件或网址。例如 notepad、C:\\Windows\\notepad.exe、"
            "https://example.com、D:\\报告.docx（走系统默认关联）"
        ),
    )


@skill(
    name="computer_launch",
    display_name="启动程序或打开文件",
    description=(
        "启动一个程序，或用系统默认程序打开一个文件 / 网址"
        "（给网址就开浏览器、给 .docx 就开 Word、给文件夹就开资源管理器）。"
        "打开之后通常要等它几秒，再 computer_activate_window 把它切到前台才好在上面操作。"
    ),
    params_model=LaunchParams,
    category="system",
    permission_level="confirm",
    tags=_TAGS,
)
class LaunchSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = LaunchParams(**params)
        target = args.target.strip()
        if not target:
            raise SkillExecutionError("要打开的对象不能为空。")
        try:
            windows_api.launch(target)
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        return {
            "ok": True,
            "target": target,
            "message": f"已请求系统打开：{target}",
        }





class ReadScreenParams(BaseModel):
    window_handle: int | None = Field(
        None,
        description="要读哪个窗口（句柄来自 computer_list_windows）；不填就读当前前台窗口",
    )
    max_items: int = Field(
        60, ge=1, le=200, description="最多返回多少个元素（太多会读不完）"
    )


@skill(
    name="computer_read_screen",
    display_name="读取界面元素",
    description=(
        "读出界面上有哪些元素：每个元素的**名称、控件类型（Button/Edit/MenuItem 等）、"
        "位置与尺寸、是否可用、能否聚焦**。比截图更进一步 —— 截图上要靠眼睛找，"
        "这里直接给出可点的东西和它们的准确坐标。"
        "返回的 left/top 就是屏幕像素坐标，可以直接交给 computer_mouse_click。"
        "默认读当前前台窗口；要读别的窗口先 computer_activate_window。"
        "⚠️ 元素可能很多，只看和当前任务相关的那几个；界面变化后要重新读一次。"
    ),
    params_model=ReadScreenParams,
    category="system",
    permission_level="confirm",
    tags=_TAGS,
    
    timeout=60.0,
)
class ReadScreenSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ReadScreenParams(**params)
        try:
            elements = await windows_api.read_ui_elements(
                window_handle=int(args.window_handle or 0),
                max_items=args.max_items,
            )
        except windows_api.WindowsApiError as exc:
            raise _to_skill_error(exc) from exc
        return {
            "ok": True,
            "count": len(elements),
            "elements": elements,
            "hint": (
                "name 是元素上显示的文字、type 是控件类型、left/top 可直接用于 "
                "computer_mouse_click。depth 表示嵌套层级（越大约靠里）。"
            ),
            "message": f"读到 {len(elements)} 个可见元素。",
        }
