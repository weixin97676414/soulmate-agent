"""**永久开启且免批准**的技能名单（后端硬锁）。

## 为什么这几个必须"关不掉"

这份名单现在一共 **13 个**技能（⚠️ 数量以 :data:`ALWAYS_ON_SKILLS` 为准 ——
这里原先写的是"九个"，随名单扩充早就过期了）。前九个是搭子
**长期记忆、自我认知与基础信息获取**的能力：

- `kb_add` / `kb_search` / `kb_stats`（长期记忆的存、取、看）
- `history_search`（检索以前聊过的内容）
- `self_growth`（把踩坑与被纠正沉淀成常识）
- `anti_fraud`（防骗识别）
- `http_request`（发 HTTP 请求 —— 很多能力要靠它拿数据）
- `ai_thinking_mode`（策划前的思路梳理）
- `system_time`（界面上的显示名是「获取当前时间」）
- `xjx_place_lookup` / `xjx_fetch_report`（心鉴学「Soulmate专用」「人际关系运营」
  的配套工具，见 `builtin/xjx.py`）

前九个的共同点是：**被一张确认卡片打断一次，用户失去的不是"一次操作"，
而是搭子的一部分记忆或人格**。的原话是"我希望 AI 能够
获取全部权限，不需要用户批准……没有开关，即默认永久开关，用户无法手动关闭"。

最后两个是另一条理由（同一天的口径）：心鉴学那套技能**按线路自动启用、无开关**，
配套工具必须跟着一起常开 —— 报告取到一半被确认卡片拦住，用户看到的是
"专属技能坏了"。它们同时受**搭子归属**约束（非归属搭子连工具都看不见），
那层隔离不走这份名单，见 `builtin/xjx.py::forbidden_tool_names`。

## 为什么是"后端硬锁"而不是"前端不画开关"

前端不画开关只解决了"界面干净"，任何别的路径（PATCH 接口、MCP 同步、
将来的新入口、手改配置文件）照样能把它关掉或降级 —— 而用户要的是
**关不掉**。所以：

1. 权限直接落在装饰器默认值上（`permission_level="safe"`），不是运行期覆盖：
   内置技能的 enabled / permission **本来就不落盘**（只有 MCP 工具经
   `permission_overrides` 落盘），所以"用户改成免确认、重启又变回需确认"
   正是从这里来的 —— 在默认值上改才真正持久。
2. `SkillManager.set_enabled` / `set_permission` 对名单里的技能**直接拒绝**，
   任何调用路径都绕不过去。
3. `SkillMeta.locked` 随 `to_dict()` 下发给界面，界面据此不渲染开关。

⚠️ **不要**把这份名单改成"配置项"或"可由界面编辑"：它承载的是产品的硬约束，
不是偏好设置。
"""

from __future__ import annotations

# 永久开启 + 免批准的技能名（与 `@skill(name=...)` 一一对应，**不是显示名**）。
# 注意「获取当前时间」的技能名是 `system_time`（见 builtin/system.py），
# 别按显示名猜 —— 名字写错不会报错，只会让这一个静静地没被锁住。
# 增删请连带更新 `core/tests/unit/test_skill_locking.py` 与文档。
ALWAYS_ON_SKILLS: frozenset[str] = frozenset(
    {
        "ai_thinking_mode",
        "system_time",
        "self_growth",
        "history_search",
        "kb_add",
        "kb_search",
        "kb_stats",
        "anti_fraud",
        "http_request",
        # 心鉴学的两个配套工具（名字与 builtin/xjx.py 的常量一致；
        # 同样别按显示名猜 —— 显示名是「地点核对」「报告代取」）
        "xjx_place_lookup",
        "xjx_fetch_report",
        # 向用户求助的两个通道：不确定意图时让他做选择、
        # 需要私钥这类敏感信息时弹输入框。
        #
        # ⚠️ **关不掉是产品明确要求的**："要求的就是关不掉，要不然我怎么不放通用技能呢"
        # —— 所以别看到"这两个技能看起来无害"就把它们挪去通用栏或从这里删掉。
        # 它们的价值正是"每个搭子在任何时候都能停下来问"，可关闭就失去了这个保证：
        # 用户一旦关掉，搭子遇到不确定的情况只会退回"猜"，而猜错的那一轮
        # 是他自己承担代价。
        "ask_choice",
        "request_secret",
    }
)

# 名字占位：这些名字**不允许**被新技能占用（自定义技能、MCP 同步都算）。
# 否则会出现两张同名卡，而其中一张能删、另一张关不掉。
RESERVED_SKILL_NAMES: frozenset[str] = frozenset(
    {"Soulmate专用", "人际关系运营", "地点核对", "报告代取"}
) | ALWAYS_ON_SKILLS


def is_always_on(name: str) -> bool:
    """这个技能是不是被硬锁的（永久开启、免批准）。"""
    return name in ALWAYS_ON_SKILLS


def is_reserved(name: str) -> bool:
    """名字是否被内置技能占住（硬锁技能 + 心鉴学专属技能与配套工具）。

    心鉴学那部分由 ``builtin/xjx.py`` 自己维护（它有一整套 id、显示名与工具名），
    这里只做转发 —— 服务端启动早期就会 import 本模块，把那份表复制过来会多一处
    "改了一边忘了另一边"的隐患。
    """
    if name in RESERVED_SKILL_NAMES:
        return True
    from .builtin import xjx

    return xjx.is_reserved(name)


def locked_message(display_name: str) -> str:
    """给用户看的一句话（界面会原样展示，所以别再包一层"操作失败"的壳）。

    心鉴学那两个的理由和前九个不一样（不是"记忆与人格"，而是"专属技能按线路
    自动启用"），所以交给 ``builtin/xjx.py`` 按名字给更准确的说法 —— 写死一句
    「承载搭子的长期记忆」会让用户以为取报告失败是记忆出了问题。
    """
    from .builtin import xjx

    if xjx.is_reserved(display_name):
        return xjx.locked_message(display_name)
    # 那两个"向用户求助"的技能：理由与"记忆与人格"完全不同，
    # 套下面那句会让用户以为关不掉是因为它在管记忆 —— 他会去别处找原因。
    # ⚠️ 这里认的是**显示名**（调用方传的是 `meta.display_name or name`），
    # 所以 id 与显示名都要认，少一个就会有半边走到通用文案。
    if display_name in {"ask_choice", "request_secret", "请你确认一下", "请你提供密钥"}:
        return (
            f"「{display_name}」是默认永久开启的技能：搭子拿不准你的意思、"
            "或需要你提供密钥时，靠它停下来问你，而不是自己猜。"
            "不提供开关，也不能修改权限。"
        )
    return (
        f"「{display_name}」是默认永久开启的技能：它承载搭子的长期记忆与基础能力，"
        "不提供开关，也不能修改权限。"
    )
