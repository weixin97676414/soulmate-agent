"""搭子总管「新建搭子」这条链到底还能不能用（第 95 批）。

的原话：「我们的管家搭子的专属技能里有创建搭子，语音配置里也有
新建搭子，现在是不能用了吗？如果不能用了，及时修复，包括现存的新建按钮」。

排查结论：**三条路径都在**，本文件给的是「技能」这条的**执行证据**。

| 路径 | 接线 | 证据 |
|---|---|---|
| 专属技能 `team_create_assistant` | `skill/builtin/orchestrate.py` → `ctx.service("team")` → `Orchestrator.create_assistant` → 落 `assistants.json` + 写 IDENTITY / RULES / SOUL + 推 `assistants_changed` | **本文件** |
| 语音 `buddy.new` | `services/voiceCommands.ts` → `AssistantRail.tsx` 的 `setNewOpen(true)` | 读代码（前端还没有测试底座） |
| 搭子栏「New Buddy」按钮 | `AssistantRail.tsx` → `NewBuddyFlow`（手动 / 导入搭子 / 导入搭子群） | 读代码（同上） |

⚠️ 为什么要专门补这一条：`test_p4_assistants.py` 覆盖的是**搭子 CRUD 的 HTTP 路径**
（`POST / PUT / DELETE /v1/assistants`），而"AI 自己调技能建搭子"走的是**另一条路**
（技能 → 门面 → 落盘），在这之前**一条用例都没有** —— 于是"它是不是还活着"只能靠
读代码判断。而这类链路的坏法恰恰是**静默的**：技能没注册、门面没注入、写盘失败被吞……
界面上都只表现为"它说建好了，但搭子栏里没出现"。
"""

from __future__ import annotations

import pytest

from my_agent.assistants import library as library_mod
from my_agent.assistants.persona import IDENTITY_FILE, RULES_FILE, SOUL_FILE, assistant_dir
from my_agent.assistants.transfer import TransferError
from my_agent.llm.base import LLMResponse

from .conftest import (
    FakeLLM,
    install_fake_model,
    make_client,
    read_sse,
    read_sse_auto_approve,
    tool_call,
)


def _store(paths, **kwargs):
    """测试用：带**内置搭子数据源**的 `ConfigStore`。

    ⚠️ 生产路径里这一步由组合根 `AppRuntime` 做（审计 M-20：`config` 不许 import
    `assistants`，内置搭子的数据由上层注入）。测试直接构造 `ConfigStore` 而不注入，
    就只剩"读文件 + 校验" —— 内置搭子既不会播种也不会迁移，断言它们存在的用例会红。
    走这个 helper 才与生产同口径。

    （两个 import 放在函数里：有的测试文件是在**函数内** import `ConfigStore` 的，
    写成模块级会去动它们的 import 块 —— 上一版就是这么把括号插坏的。）
    """
    from my_agent.assistants.bootstrap import BuiltinAssistants
    from my_agent.config.loader import ConfigStore

    return ConfigStore(paths, builtin=BuiltinAssistants(), **kwargs)


@pytest.fixture
async def http(base_url):
    async with make_client(base_url) as client:
        yield client


def _call(name: str, arguments: dict | None = None) -> LLMResponse:
    """让假模型"调一次工具"。"""
    return LLMResponse(
        content="",
        tool_calls=[tool_call(name, arguments)],
        finish_reason="tool_calls",
    )


async def test_buddy_manager_can_see_the_create_buddy_skill(runtime, http):
    """搭子总管的工具表里**必须**有「建搭子」这条技能。

    用户说的是"管家搭子的专属技能里有创建搭子" —— 这条钉的就是那句。工具表来自
    `skill/groups.py` 的归属过滤（`team_` / `buddy_` / `computer_` 前缀 + 精确名单），
    所以它同时也在钉"专属技能真的按搭子装配"这件事。
    """
    llm = FakeLLM(["好的"])
    install_fake_model(runtime, llm)

    await read_sse(http, {"message": "你好", "model_id": "fake", "assistant_id": "BuddyManager"})

    tools = {spec.name for spec in llm.tools_seen[0]}
    # 搭子团队这批（`team_` 前缀）：建 / 查 / 改 / 删搭子都在
    assert {"team_list_assistants", "team_create_assistant", "team_update_assistant"} <= tools
    # 官网搭子库：产品定的流程是"建之前先看官网有没有现成的"，那条路要用它
    assert {"buddy_library_list", "buddy_import"} <= tools
    # 通用技能不在：内置搭子不能再添加技能（产品约定）
    assert "excel_read" not in tools


async def test_buddy_manager_really_creates_a_buddy(runtime, http, monkeypatch):
    """真跑一遍完整流程：查官网（失败）→ 建搭子 → 落到盘上、出现在搭子清单里。

    ⚠️ 刻意让官网**读不到**（把 `_fetch` 换成抛 `TransferError`），有两个原因：

    1. 用例不能联网（测试机可能没网 / 官网可能改版）；
    2. 这恰好是"查不到也**允许**继续建"那条分支 —— 用户要求的是"只要求**查过**，
       不要求**查到**"。把这条分支钉住，可以防止将来有人把闸门改成"查不到就不许建"
       （那会让离线用户彻底建不了搭子）。
    """

    def _offline(url: str) -> bytes:
        raise TransferError("测试环境不联网")

    monkeypatch.setattr(library_mod, "_fetch", _offline)

    install_fake_model(
        runtime,
        FakeLLM(
            [
                # ① 先查官网（闸门要求：建之前必须查过）
                _call("buddy_library_list"),
                # ② 建
                _call(
                    "team_create_assistant",
                    {
                        "name": "资料整理助手",
                        "description": "整理资料、归档与检索",
                        "identity": "负责把用户散落的资料整理成可检索的档案。",
                        "abilities": "1. 归档；2. 按关键词检索；3. 定期清理重复项。",
                        "rules": "先问清存放位置再动手；拿不准时先列方案给用户选。",
                        "tone": "像交付清单一样简洁，每条给依据，不寒暄。",
                        "emoji": "📚",
                    },
                ),
                "官网没有合适的，我已经自己建了一个。",
            ]
        ),
    )

    events = await read_sse_auto_approve(
        http,
        {
            "message": "帮我建一个整理资料的搭子",
            "model_id": "fake",
            "assistant_id": "BuddyManager",
        },
    )

    results = [data for name, data in events if name == "tool_result"]
    assert results, f"一次工具都没执行成功（事件：{[name for name, _ in events]}）"

    # ① 查官网**确实发生了**，而且失败原因被如实带回（不是假装查过）
    listed = " ".join(str(item.get("result", "")) for item in results)
    assert "读取官网搭子库失败" in listed, "第一轮那次官网查询没有留下痕迹"

    # ② 搭子真的建出来了
    profile = next(
        (item for item in runtime.assistants.sorted() if item.name == "资料整理助手"),
        None,
    )
    assert profile is not None, "技能回报建好了，但搭子清单里没有它"
    assert profile.builtin is False, "AI 建的搭子不该被当成内置（否则会被写死回厂值）"
    assert profile.description == "整理资料、归档与检索"

    # ③ 设定的正文真的写进了人格文件（产品明确要求过：不能只写一句"你是 X"）
    folder = assistant_dir(runtime.paths, profile.id)
    identity = (folder / IDENTITY_FILE).read_text(encoding="utf-8")
    rules = (folder / RULES_FILE).read_text(encoding="utf-8")
    soul = (folder / SOUL_FILE).read_text(encoding="utf-8")
    assert "整理成可检索的档案" in identity, "IDENTITY.md 没写进去"
    assert "先问清存放位置" in rules, "RULES.md 没写进去"
    assert "不寒暄" in soul, "SOUL.md 没写进去"

    # ④ 界面上看得见：列表接口里有它（搭子栏读的就是这个接口）
    payload = (await http.get("/v1/assistants")).json()
    assert profile.id in {item["id"] for item in payload["assistants"]}

    # ⑤ 重启后还在（落盘是真落盘，不是只改了内存里那份）

    reloaded = _store(runtime.paths).load().assistants
    assert reloaded.get(profile.id) is not None, "assistants.json 里没有它，重启就会丢"
