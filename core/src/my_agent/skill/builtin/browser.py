"""浏览器自动化技能（读写分级）。

设计遵循两条原则：

1. **读写分级**（与框架的权限模型一致）：打开网页、读正文、看快照、截图、查标签
   都是**只读**，直接执行（safe）；点击/填表/滚动这类会**改变对端真实状态**的动作
   需要用户确认（confirm）。如果连"打开看看"都要弹确认，用户会把确认框当噪声点掉，
   确认机制就失效了。

2. **稳定句柄 + 动作后重快照**（吸收自 openclaw 的 browser-automation 范式）：
   - 标签页用我们自己起的 ``label`` 定位，**不用浏览器内部会变的 tabId**；
   - 快照里的 ``ref`` 只是给模型的编号，真正的定位靠**可见文本/角色**，
     所以导航/弹窗之后让模型重新快照、用新文案定位，就不会有"陈旧引用"问题；
   - 遇到登录/验证码/2FA，结果里会带 ``blocked=True`` —— **停下来告诉用户**，
     而不是循环重试。

所有动作都走 ``browser/session.py`` 的进程级单例：同一份浏览器实例、同一份登录态。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...browser.session import browser
from ...errors import SkillExecutionError
from ...skill.base import BaseSkill, SkillContext
from ...skill.decorator import skill


def _profile_dir(ctx: SkillContext) -> Path:
    """浏览器持久化 profile 的落点（登录态保存在这里）。"""
    if ctx.paths is not None:
        return Path(ctx.paths.data_dir) / "browser-profile"
    return Path.cwd() / "browser-profile"


async def _context(ctx: SkillContext) -> Any:
    return await browser.ensure(_profile_dir(ctx))


async def _blocker(ctx: SkillContext, page: Any) -> dict[str, Any] | None:
    """命中登录/验证码等人工环节时，返回"停下来说明"的提示。"""
    reason = await browser.detect_blocker(page)
    if reason is None:
        return None
    return {
        "blocked": True,
        "reason": reason,
        "hint": "检测到可能需要人工完成的环节（登录、验证码、2FA 等）。"
        "**请停下来、不要反复重试**，向用户说明当前卡在哪一步、需要他做什么。",
    }


class BrowserReadParams(BaseModel):
    url: str = Field(..., description="要打开的网页地址，以 http:// 或 https:// 开头")
    label: str | None = Field(None, description="给这个标签页起的名字，后续操作用它定位（例如「登录页」）")


@skill(
    name="browser_read",
    display_name="打开网页并读取正文",
    description=(
        "用系统浏览器打开一个网页并读回正文文本。"
        "当用户说「打开这个链接」「看看这个页面写了什么」时使用。"
        "只读，不会修改网页；正文会完整返回，不做截断。"
        "若页面停在登录/验证码等需要人工的环节，返回值里 blocked 会为 true，"
        "此时应停下并告知用户，而不是反复重试。"
    ),
    params_model=BrowserReadParams,
    category="system",
    permission_level="safe",
    tags=["浏览器", "网页", "只读"],
)
class BrowserReadSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = BrowserReadParams(**params)
        url = args.url.strip()
        if not url.lower().startswith(("http://", "https://")):
            raise SkillExecutionError("地址必须以 http:// 或 https:// 开头。")

        context = await _context(ctx)
        page = await browser.page(context, args.label)
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        text = await browser.read_text(page)

        result: dict[str, Any] = {
            "url": page.url,
            "title": await page.title(),
            "content": text,
            "chars": len(text),
        }
        blocker = await _blocker(ctx, page)
        if blocker:
            result.update(blocker)
        return result


class BrowserSnapshotParams(BaseModel):
    label: str | None = Field(None, description="要看哪个标签页；留空用当前页")


@skill(
    name="browser_snapshot",
    display_name="查看当前页面有哪些可点击/可输入的元素",
    description=(
        "列出当前页面上可见的按钮、链接、输入框等可交互元素（带 ref 编号）。"
        "在执行点击/填表之前用它看看页面上有什么、准确的文案是什么。"
        "每次导航或提交之后都要**重新快照**，用最新文案来定位。"
        "只读，不会修改网页。"
    ),
    params_model=BrowserSnapshotParams,
    category="system",
    permission_level="safe",
    tags=["浏览器", "快照", "只读"],
)
class BrowserSnapshotSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = BrowserSnapshotParams(**params)
        context = await _context(ctx)
        page = await browser.page(context, args.label)
        result = await browser.snapshot(page)
        blocker = await _blocker(ctx, page)
        if blocker:
            result.update(blocker)
        return result


class BrowserScreenshotParams(BaseModel):
    label: str | None = Field(None, description="要截图的标签页；留空用当前页")


@skill(
    name="browser_screenshot",
    display_name="给当前网页截图",
    description=(
        "对当前网页整页截图，保存为图片产物供用户查看。"
        "当用户说「截个图」「看看长什么样」时使用。只读。"
    ),
    params_model=BrowserScreenshotParams,
    category="system",
    permission_level="safe",
    tags=["浏览器", "截图", "只读"],
)
class BrowserScreenshotSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = BrowserScreenshotParams(**params)
        context = await _context(ctx)
        page = await browser.page(context, args.label)

        name = f"page-{args.label or 'shot'}.png"
        target = ctx.artifact_output(name)
        await browser.screenshot(page, target)
        record = await ctx.register_artifact(target, note="网页截图")
        return {
            "url": page.url,
            "title": await page.title(),
            "artifact": record,
            "path": str(target),
        }


class BrowserTabsParams(BaseModel):
    action: str = Field("list", description="list = 列出所有标签；close = 关闭指定标签")
    label: str | None = Field(None, description="action=close 时要关闭的标签名")


@skill(
    name="browser_tabs",
    display_name="管理浏览器标签页",
    description=(
        "列出当前打开的所有标签页，或关闭某个标签页。"
        "开新标签前先用它看看有没有可复用的，避免开一堆重复窗口。"
        "close 会关闭标签页（这是它唯一会改变状态的动作，但只影响我们自己的浏览器）。"
    ),
    params_model=BrowserTabsParams,
    category="system",
    permission_level="safe",
    tags=["浏览器", "标签页"],
)
class BrowserTabsSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = BrowserTabsParams(**params)
        context = await _context(ctx)
        if args.action == "list":
            return {"tabs": await browser.list_tabs(context)}
        if args.action == "close":
            await browser.close_tab(context, args.label)
            return {"closed": args.label, "tabs": await browser.list_tabs(context)}
        raise SkillExecutionError(f"不支持的动作「{args.action}」。可用：list / close。")


class BrowserActParams(BaseModel):
    action: str = Field(..., description="动作：goto / back / click / fill / type / press / scroll")
    target: str | None = Field(None, description="click 要点的文案、fill/type 要填的输入框、goto 要跳的地址")
    value: str | None = Field(None, description="fill 要填的内容、press 要按的键（如 Enter）、scroll 方向（down/up）")
    label: str | None = Field(None, description="在哪个标签页操作；留空用当前页")


@skill(
    name="browser_act",
    display_name="在网页上执行操作（点击/填表/滚动）",
    description=(
        "在网页上执行一个操作：点击按钮或链接、往输入框填内容、按键、滚动、跳转、后退。"
        "click 用元素的**可见文案**定位（先 browser_snapshot 看准确文案），"
        "fill/type 用输入框的标签或占位文字定位。"
        "会**改变网页的真实状态**，执行前会请用户确认。"
        "导航/提交之后页面会变化，下一步请重新 browser_snapshot。"
    ),
    params_model=BrowserActParams,
    category="system",
    # confirm：点击/填表会改对端真实状态
    permission_level="confirm",
    tags=["浏览器", "交互", "写入"],
)
class BrowserActSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = BrowserActParams(**params)
        context = await _context(ctx)
        page = await browser.page(context, args.label)
        result = await browser.act(
            page, action=args.action, target=args.target, value=args.value
        )
        blocker = await _blocker(ctx, page)
        if blocker:
            result.update(blocker)
        return result
