"""浏览器自动化会话（Playwright，**用系统浏览器、不打包 Chromium**）。

## 为什么是"系统浏览器"

Edge 是 Windows 10/11 自带，Chrome 也常见。用系统浏览器能省掉约 300MB 的
Chromium 下载与随包分发（见 ``build/agent-core.spec`` 里 Playwright 那段说明）。
代价是"依赖用户机器上有 Edge/Chrome"—— 这对目标环境（Windows 桌面）是可接受的，
真没有时这里会给出明确报错，而不是静默失败。

## 冻结运行时的一个 shim（重要，别删）

PyInstaller 用 ``noarchive=False`` 时，``playwright/__init__.py`` 会被塞进 PYZ
压缩归档，于是 playwright 驱动路径解析里那句
``Path(inspect.getfile(playwright)).parent / "driver"`` 拿不到真实目录。
但驱动数据文件**确实**被 ``collect_all`` 放到了 ``_MEIPASS/playwright/driver/``。

所以这里在**任何 ``async_playwright()`` 之前**，把 ``playwright.__file__`` 指到
``_MEIPASS/playwright/__init__.py`` —— ``inspect.getfile`` 优先读 ``__file__``，
指过去之后 ``.parent / "driver"`` 就落到数据目录上了。

## 关于"遇登录/验证码就停下来"

这是从 openclaw 的 browser-automation 范式里吸收的最重要一条：遇到需要人工的
环节（登录、验证码、2FA、授权弹窗）**不要循环重试，而是明确告知用户**。
这里用轻量启发式（URL/标题/正文里的关键词）做一层检测，命中时在结果里返回
``blocked=True``，让模型停下来说明，而不是对着验证码连点几十次。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from ..errors import SkillExecutionError

logger = logging.getLogger(__name__)

# 命中即视为"需要人工"的页面特征（启发式，够用即可，不必穷举）
_BLOCKER_HINTS = (
    "login", "sign in", "signin", "log in", "captcha", "verification",
    "verify", "2fa", "two-factor", "authenticate",
    "登录", "验证码", "验证", "扫码", "身份验证",
)

# 已知浏览器可执行文件的标准位置（Windows）
_EDGE_PATHS = (
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
)
_CHROME_PATHS = (Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),)


def _apply_frozen_shim() -> None:
    """冻结运行时把 playwright 的驱动定位指到数据目录（见模块说明）。"""
    if not getattr(sys, "frozen", False):
        return
    import playwright  # 必须在设置 __file__ 前 import 出这个模块对象

    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return
    driver_dir = Path(meipass) / "playwright" / "driver"
    if (driver_dir / "node.exe").exists():
        # inspect.getfile(playwright) 优先返回 __file__；指过去之后
        # `.parent / "driver"` 就正好落在 collect_all 放数据的地方。
        playwright.__file__ = str(Path(meipass) / "playwright" / "__init__.py")
    # 永远不要尝试联网下载浏览器：我们只用系统浏览器
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")


def _detect_channel() -> str | None:
    """探测系统里可用的浏览器，返回 playwright 的 channel 名或 None。"""
    for candidate in _EDGE_PATHS:
        if candidate.exists():
            return "msedge"
    for candidate in _CHROME_PATHS:
        if candidate.exists():
            return "chrome"
    # shutil.which 兜底：有些机器把浏览器加进了 PATH
    if shutil.which("msedge") or shutil.which("microsoft-edge"):
        return "msedge"
    if shutil.which("chrome") or shutil.which("google-chrome"):
        return "chrome"
    return None


class BrowserSession:
    """进程级单例的浏览器会话。

    - **惰性启动**：第一次用到时才拉起来，不用就不占资源；
    - **持久化 profile**：登录态留在磁盘上，下次复用（用户不用每次重新登录）；
    - **有头模式**：用户可能需要亲眼看到页面、或手动过登录/验证码；
    - 所有入口用一个 ``asyncio.Lock`` 串行化 —— 浏览器对象不是为并发设计的，
      多个会话同时动它会互相踩。
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pw = None
        self._context = None
        self._pages: dict[str, Any] = {}
        self._profile_dir: Path | None = None

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    async def ensure(self, profile_dir: Path) -> Any:
        """确保浏览器已启动，返回持久化 context。

        ⚠️ **必须能自愈**（用户反馈：「用户关闭浏览器后，AI 无法再自己拉起浏览器，
        导致任务失败」）。

        以前这里只判断 ``self._context is not None``，而 ``_context`` 只在 ``close()``
        里置空（那是应用退出才走的路径）。于是用户**手动关掉浏览器窗口**之后，
        这里会把一个**已经失效的 context 对象**当成可用的返回，后面所有页面操作
        都在死对象上失败。

        现在两道保险：
        1. **事件驱动**：启动时监听 context 的 ``close`` 事件，一旦关闭就立刻清空引用；
        2. **每次进来探活**：即使事件因故没到（例如驱动进程被杀），也能发现并重启。
        """
        async with self._lock:
            if self._context is not None and not self._is_alive(self._context):
                logger.info("浏览器已不可用（被关闭或进程退出），引用已清空，准备重新拉起")
                self._context = None
                self._pages.clear()
            if self._context is not None:
                return self._context

            _apply_frozen_shim()
            channel = _detect_channel()
            if channel is None:
                raise SkillExecutionError(
                    "没有检测到系统里的 Edge 或 Chrome 浏览器，无法使用浏览器能力。"
                    "请安装 Microsoft Edge 或 Google Chrome 后重试。"
                )

            from playwright.async_api import async_playwright

            self._profile_dir = profile_dir
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            self._pw = await async_playwright().start()
            try:
                self._context = await self._pw.chromium.launch_persistent_context(
                    user_data_dir=str(self._profile_dir),
                    channel=channel,
                    headless=False,
                    # 桌面窗口：不设 viewport，让窗口尺寸跟随系统
                    no_viewport=True,
                )
            except Exception as exc:
                # 启动失败要连 driver 一起收掉，避免留下半个状态
                await self._pw.stop()
                self._pw = None
                raise SkillExecutionError(
                    f"浏览器启动失败（channel={channel}）：{exc}。"
                    "请确认 Edge/Chrome 未被其他进程占用或损坏。"
                ) from exc

            # 事件驱动的那道保险：用户手动关窗时立刻清空引用，下次自动重启。
            self._context.on("close", self._on_context_closed)
            self._pages = {page: page for page in self._context.pages}
            logger.info("浏览器已启动（channel=%s，profile=%s）", channel, profile_dir)
            return self._context

    def _on_context_closed(self) -> None:
        """浏览器被关掉（用户手动关窗、或进程退出）时清空引用。

        **不清空的话，下次会拿到一个死对象** —— 那正是"用户关掉浏览器后 AI 再也
        拉不起来"的原因。清空之后，下一次 ``ensure()`` 会重新走一遍启动流程。
        """
        self._context = None
        self._pages.clear()
        logger.info("浏览器已被关闭，引用已清空；下次使用时会自动重新拉起")

    @staticmethod
    def _is_alive(context: Any) -> bool:
        """探活：对已关闭的 context 访问页面集合会抛错。"""
        try:
            _ = context.pages
            return True
        except Exception:  # noqa: BLE001 - 任何异常都按"不可用"处理，宁可多启一次
            return False

    @staticmethod
    def looks_closed(exc: BaseException) -> bool:
        """判断一个异常是否表示"浏览器/页面已经被关掉了"。

        命中时调用方应当 ``close()`` 清干净后重新 ``ensure()`` 并重试一次 ——
        这是最后一道自愈保险（事件与探活都没能提前发现的情况）。
        """
        text = str(exc).lower()
        return any(
            hint in text
            for hint in (
                "has been closed",
                "target closed",
                "browser has been closed",
                "context has been closed",
                "closed",
            )
        )

    async def close(self) -> None:
        """关掉浏览器与驱动（应用退出时调用）。"""
        async with self._lock:
            self._pages.clear()
            if self._context is not None:
                try:
                    await self._context.close()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("关闭浏览器 context 失败：%s", exc)
                self._context = None
            if self._pw is not None:
                try:
                    await self._pw.stop()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("停止 playwright 驱动失败：%s", exc)
                self._pw = None

    # ------------------------------------------------------------------ #
    # 标签页
    # ------------------------------------------------------------------ #
    async def page(self, context: Any, label: str | None) -> Any:
        """取指定标签页；``label`` 为空时用当前页（或新建一个）。

        ⚠️ 缓存的标签页可能**已经被用户手动关掉** —— 直接返回它等于把死对象
        交给后续操作。这里先确认它还活着，不活就忘掉它、重新开一个。
        （"用户关掉浏览器/标签页后 AI 自己拉不起来"的第二种情况。）
        """
        if label and label in self._pages:
            cached = self._pages[label]
            if not self._is_page_alive(cached):
                logger.info("标签页「%s」已被关闭，重新打开一个", label)
                self._pages.pop(label, None)
            else:
                return cached
        if context.pages:
            live = [item for item in context.pages if self._is_page_alive(item)]
            if live:
                page = live[-1]
                if label:
                    self._pages[label] = page
                return page
        page = await context.new_page()
        if label:
            self._pages[label] = page
        return page

    @staticmethod
    def _is_page_alive(page: Any) -> bool:
        try:
            return not page.is_closed()
        except Exception:  # noqa: BLE001 - 取不到状态就按"不可用"处理
            return False

    async def open(self, context: Any, url: str, label: str | None) -> dict[str, Any]:
        if label and label in self._pages:
            page = self._pages[label]
        else:
            page = await context.new_page()
            if label:
                self._pages[label] = page
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        return {"url": page.url, "title": await page.title(), "label": label}

    async def list_tabs(self, context: Any) -> list[dict[str, Any]]:
        tabs = []
        for page in context.pages:
            try:
                title = await page.title()
            except Exception:  # noqa: BLE001
                title = ""
            tabs.append({"url": page.url, "title": title})
        return tabs

    async def close_tab(self, context: Any, label: str | None) -> None:
        page = await self.page(context, label)
        await page.close()
        if label:
            self._pages.pop(label, None)

    # ------------------------------------------------------------------ #
    # 读 / 快照 / 截图
    # ------------------------------------------------------------------ #
    async def read_text(self, page: Any) -> str:
        """读正文：``article`` → ``main`` → ``body`` 回退链（openclaw 范式）。"""
        for selector in ("article", "main", "body"):
            loc = page.locator(selector).first
            try:
                text = (await loc.inner_text(timeout=3000)).strip()
            except Exception:  # noqa: BLE001
                continue
            if text:
                return text
        return ""

    async def snapshot(self, page: Any) -> dict[str, Any]:
        """返回页面标题 + 可交互元素列表（带 ref 编号，供模型引用）。

        刻意**不做数量上限**：元素是"有哪些可点的东西"，不是"正文内容"，
        少给一个都可能让模型漏掉它要找的入口。
        """
        elements: list[dict[str, Any]] = []
        for role in (
            "button", "link", "textbox", "combobox", "checkbox",
            "radio", "tab", "menuitem", "heading",
        ):
            locs = page.get_by_role(role)
            count = await locs.count()
            for index in range(count):
                loc = locs.nth(index)
                try:
                    if not await loc.is_visible():
                        continue
                    name = (
                        (await loc.get_attribute("aria-label"))
                        or (await loc.inner_text())
                        or (await loc.get_attribute("placeholder"))
                        or (await loc.get_attribute("name"))
                        or ""
                    )
                except Exception:  # noqa: BLE001
                    name = ""
                name = " ".join(str(name).strip().split())
                if not name:
                    continue
                elements.append(
                    {"ref": len(elements) + 1, "role": role, "name": name[:160]}
                )
        return {
            "url": page.url,
            "title": await page.title(),
            "element_count": len(elements),
            "elements": elements,
        }

    async def screenshot(self, page: Any, target: Path) -> None:
        await page.screenshot(path=str(target), full_page=True, type="png")

    # ------------------------------------------------------------------ #
    # 动作
    # ------------------------------------------------------------------ #
    async def act(
        self, page: Any, *, action: str, target: str | None, value: str | None
    ) -> dict[str, Any]:
        """执行一个动作。可能改变页面状态（导航/提交），调用方应随后重新快照。"""
        if action == "goto":
            await page.goto(target or "", wait_until="domcontentloaded", timeout=45_000)
            return {"url": page.url}
        if action == "back":
            await page.go_back()
            return {"url": page.url}
        if action == "press":
            await page.keyboard.press(value or "Enter")
            return {"pressed": value or "Enter"}
        if action == "scroll":
            delta = 800 if (value or "down") == "down" else -800
            await page.mouse.wheel(0, delta)
            return {"scrolled": value or "down"}

        if action == "click":
            loc = await self._locate(page, target or "")
            if loc is None:
                raise SkillExecutionError(
                    f"页面上没找到可点击的「{target}」。可能页面已经变化，"
                    "请先调用 browser_snapshot 看看当前有哪些元素。"
                )
            await loc.click(timeout=10_000)
        elif action == "fill":
            loc = await self._locate_input(page, target or "")
            if loc is None:
                raise SkillExecutionError(
                    f"页面上没找到输入框「{target}」。可能页面已经变化，"
                    "请先调用 browser_snapshot 看看当前有哪些元素。"
                )
            await loc.fill(value or "", timeout=10_000)
        elif action == "type":
            loc = await self._locate_input(page, target or "") if target else None
            if loc is not None:
                await loc.click(timeout=5_000)
            await page.keyboard.type(value or "")
        else:
            raise SkillExecutionError(
                f"不支持的动作「{action}」。可用：goto / back / click / fill / type / press / scroll。"
            )

        return {"url": page.url, "title": await page.title()}

    # ------------------------------------------------------------------ #
    # 定位与阻塞检测
    # ------------------------------------------------------------------ #
    @staticmethod
    async def _locate(page: Any, target: str) -> Any:
        # 优先级：按钮 > 链接 > 精确文本 > 模糊文本
        for role in ("button", "link"):
            loc = page.get_by_role(role, name=target)
            try:
                if await loc.count():
                    return loc.first
            except Exception:  # noqa: BLE001
                continue
        for exact in (True, False):
            loc = page.get_by_text(target, exact=exact)
            try:
                if await loc.count():
                    return loc.first
            except Exception:  # noqa: BLE001
                continue
        return None

    @staticmethod
    async def _locate_input(page: Any, target: str) -> Any:
        makers = (
            lambda: page.get_by_label(target),
            lambda: page.get_by_placeholder(target),
            lambda: page.get_by_role("textbox", name=target),
        )
        for maker in makers:
            loc = maker()
            try:
                if await loc.count():
                    return loc.first
            except Exception:  # noqa: BLE001
                continue
        return None

    @staticmethod
    async def detect_blocker(page: Any) -> str | None:
        """判断当前页面是否停在"需要人工"的环节（登录/验证码/2FA）。

        返回命中原因（供模型停下来说明），没命中返回 None。
        纯启发式：宁可漏报（用户再手动说一句），也不要误报（模型该做不做）。
        """
        url = (page.url or "").lower()
        try:
            title = (await page.title() or "").lower()
        except Exception:  # noqa: BLE001
            title = ""
        for hint in _BLOCKER_HINTS:
            if hint in url or hint in title:
                return f"页面疑似需要人工处理（命中关键词「{hint}」）：{page.url}"
        return None


# 进程级单例：浏览器只有一个实例，多会话共享同一份 profile 与标签页
browser = BrowserSession()
