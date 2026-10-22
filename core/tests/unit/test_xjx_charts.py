











from __future__ import annotations

import json

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin import discover_builtin_skills, xjx
from my_agent.skill.builtin.xjx_charts import (
    AstroParams,
    BaziParams,
    XjxFetchAstroSkill,
    XjxFetchBaziSkill,
    XjxFetchMeihuaSkill,
    XjxFetchTarotSkill,
)
from my_agent.skill.builtin.xjx_report import XjxHttpResult

FORTUNE = "FortuneTellingBuddy"


class FakeGateway:


    def __init__(self, *results: XjxHttpResult) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict]] = []

    async def post_json(self, path, body, *, timeout):  
        self.calls.append((path, dict(body)))
        if self.results:
            return self.results.pop(0)
        return XjxHttpResult(200, "{}")


def _ctx(gateway: FakeGateway, assistant_id: str | None = FORTUNE) -> SkillContext:
    return SkillContext(session_id="s1", assistant_id=assistant_id, extra={"xjx": gateway})


def _ok(payload: dict) -> XjxHttpResult:
    return XjxHttpResult(200, json.dumps(payload, ensure_ascii=False))


ASTRO_BODY = {
    "birth_place": "中国 新疆 北屯",
    "country": "中国",
    "year": 1991,
    "month": 9,
    "day": 21,
    "h": 14,
    "m": 45,
}





class TestOwnership:
    def test_四个取数工具只归算命搭子(self) -> None:
        for tool in (
            xjx.TOOL_FETCH_ASTRO,
            xjx.TOOL_FETCH_BAZI,
            xjx.TOOL_FETCH_MEIHUA,
            xjx.TOOL_FETCH_TAROT,
        ):
            assert xjx.tool_owners(tool) == (FORTUNE,), tool
            assert xjx.may_use_tool(FORTUNE, tool) is True
            assert xjx.may_use_tool("soulmate", tool) is False

    def test_算命搭子拿不到取报告的工具(self) -> None:

        blocked = xjx.forbidden_tool_names(FORTUNE)
        assert xjx.TOOL_FETCH_REPORT in blocked
        assert xjx.TOOL_FETCH_ASTRO not in blocked
        
        assert xjx.TOOL_PLACE_LOOKUP not in blocked

    def test_取报告的三位拿不到四个取数工具(self) -> None:
        for assistant_id in ("soulmate", "LoveBuddy", "RelationBuddy"):
            blocked = xjx.forbidden_tool_names(assistant_id)
            for tool in (
                xjx.TOOL_FETCH_ASTRO,
                xjx.TOOL_FETCH_BAZI,
                xjx.TOOL_FETCH_MEIHUA,
                xjx.TOOL_FETCH_TAROT,
            ):
                assert tool in blocked, (assistant_id, tool)
            assert xjx.TOOL_FETCH_REPORT not in blocked
            assert xjx.TOOL_PLACE_LOOKUP not in blocked

    def test_搭子总管连一个心鉴学工具都看不到(self) -> None:
        assert xjx.forbidden_tool_names("BuddyManager") == xjx.XJX_TOOL_NAMES


class TestPlaceFieldWording:







    def test_出生地字段是越精确越好_没有写到城市(self) -> None:
        for model in (AstroParams, BaziParams):
            desc = model.model_fields["birth_place"].description or ""
            assert "越精确越好" in desc, model.__name__
            assert "写到城市" not in desc, model.__name__

    def test_行运的当前所在地也允许更细(self) -> None:
        desc = AstroParams.model_fields["current_place"].description or ""
        assert "越精确越好" in desc
        assert "最少到城市" in desc


class TestSkills:
    def test_同一模块按线路二选一(self) -> None:
        for line, suffix in (("cn", "-cn"), ("seoul", "-global")):
            names = {item.name for item in xjx.active_skills(line)}
            assert len(names) == 6, (line, names)
            assert all(name.endswith(suffix) for name in names)

    def test_算命搭子在大陆线路上拿到四个模块(self) -> None:
        skills = xjx.skills_for_assistant(FORTUNE, "cn")
        assert {item.display_name for item in skills} == {"西占", "八字", "梅花易数", "塔罗"}
        assert all(item.line == xjx.LINE_CN for item in skills)

    def test_取报告的三位仍然只有一张卡(self) -> None:
        assert [item.display_name for item in xjx.skills_for_assistant("soulmate", "cn")] == [
            "Soulmate专用"
        ]

    def test_报表分组只认取报告技能(self) -> None:

        assert xjx.group_for_assistant(FORTUNE, "cn") is None
        assert xjx.group_for_assistant("soulmate", "cn") == xjx.GROUP_SOULMATE

    def test_每份正文都能读出来且没有悬空指针(self) -> None:
        for item in xjx.XJX_SKILLS:
            text = xjx.instructions(item.name)
            assert text.strip(), item.name
            
            assert "references/" not in text, item.name
        
        
        for name in ("xjx-astro-cn", "xjx-meihua-cn", "xjx-tarot-cn"):
            assert "## 附：解读规则" in xjx.instructions(name), name
        assert "## 附：牌阵表" in xjx.instructions("xjx-tarot-cn")

    def test_四门技能的收费口径是同一句(self) -> None:









        for module in ("astro", "bazi", "meihua", "tarot"):
            for line in ("cn", "global"):
                text = xjx.instructions(f"xjx-{module}-{line}")
                assert "免费，仅消耗 6 token （社区贡献）" in text, (module, line)
                assert "每次仅消耗6 token（社区贡献点）" not in text, (module, line)
                assert "billing.charged" not in text, (module, line)

    def test_四个工具都真的注册进了技能表(self) -> None:
        names = {cls.meta.name for cls in discover_builtin_skills()}
        for tool in (
            xjx.TOOL_FETCH_ASTRO,
            xjx.TOOL_FETCH_BAZI,
            xjx.TOOL_FETCH_MEIHUA,
            xjx.TOOL_FETCH_TAROT,
        ):
            assert tool in names, tool





class TestAstro:
    @pytest.mark.asyncio
    async def test_成功时剥掉_billing(self) -> None:
        gateway = FakeGateway(
            _ok({"success": True, "report": {"x": 1}, "meta": {}, "billing": {"charged": 6}})
        )
        result = await XjxFetchAstroSkill().run(_ctx(gateway), **ASTRO_BODY)

        assert result["ok"] is True
        assert "billing" not in result
        assert gateway.calls[0][0] == "/api/astro/v1/natal"

    @pytest.mark.asyncio
    async def test_行运必须带当前所在地(self) -> None:
        gateway = FakeGateway()
        result = await XjxFetchAstroSkill().run(_ctx(gateway), report="transit", **ASTRO_BODY)

        assert result["code"] == "bad_request"
        assert "当前所在地" in result["message"]
        assert gateway.calls == []

    @pytest.mark.asyncio
    async def test_缺出生地先在本地拦住(self) -> None:
        gateway = FakeGateway()
        body = dict(ASTRO_BODY)
        body["birth_place"] = "  "
        result = await XjxFetchAstroSkill().run(_ctx(gateway), **body)

        assert result["code"] == "bad_request"
        assert "出生地" in result["message"]
        assert gateway.calls == []


class TestBazi:
    @pytest.mark.asyncio
    async def test_性别只收男女(self) -> None:
        gateway = FakeGateway()
        result = await XjxFetchBaziSkill().run(_ctx(gateway), **ASTRO_BODY, gender="先生")

        assert result["code"] == "bad_request"
        assert gateway.calls == []

    @pytest.mark.asyncio
    async def test_成功时返回成品文本(self) -> None:
        gateway = FakeGateway(_ok({"success": True, "data": {"bazi": "辛未"}, "text": "八字原命局"}))
        result = await XjxFetchBaziSkill().run(_ctx(gateway), **ASTRO_BODY, gender="男")

        assert result["ok"] is True
        assert result["text"] == "八字原命局"
        assert gateway.calls[0][0] == "/api/bazi/v1/chart"


class TestMeihuaAndTarot:
    @pytest.mark.asyncio
    async def test_梅花按两个数起卦(self) -> None:
        gateway = FakeGateway(_ok({"success": True, "data": {"ben": {"name": "天风姤"}}}))
        result = await XjxFetchMeihuaSkill().run(_ctx(gateway), n1=17, n2=29, question="合作")

        assert result["ok"] is True
        path, body = gateway.calls[0]
        assert path == "/api/meihua/v1/chart"
        assert body["n1"] == 17 and body["n2"] == 29
        assert body["question"] == "合作"
        
        assert 8 <= len(body["request_id"]) <= 64

    @pytest.mark.asyncio
    async def test_塔罗只洗牌_问题可空(self) -> None:
        gateway = FakeGateway(_ok({"success": True, "data": {"total": 78}}))
        result = await XjxFetchTarotSkill().run(_ctx(gateway))

        assert result["ok"] is True
        path, body = gateway.calls[0]
        assert path == "/api/tarot/v1/shuffle"
        assert "question" not in body


class TestErrors:
    @pytest.mark.asyncio
    async def test_401_要重新登录(self) -> None:
        gateway = FakeGateway(XjxHttpResult(401, "未登录"))
        result = await XjxFetchTarotSkill().run(_ctx(gateway))
        assert result["code"] == "need_login"

    @pytest.mark.asyncio
    async def test_402_提示补贡献点但不报数字(self) -> None:
        gateway = FakeGateway(XjxHttpResult(402, '{"need_token": 6}'))
        result = await XjxFetchTarotSkill().run(_ctx(gateway))

        assert result["code"] == "need_recharge"
        assert "6" not in result["message"]
        assert "token" not in result["message"].lower()

    @pytest.mark.asyncio
    async def test_400_把服务端原话交给模型(self) -> None:
        gateway = FakeGateway(XjxHttpResult(400, '{"error": "地点无法识别"}'))
        result = await XjxFetchMeihuaSkill().run(_ctx(gateway), n1=1, n2=2)

        assert result["code"] == "bad_request"
        assert result["message"] == "地点无法识别"

    @pytest.mark.asyncio
    async def test_502_只重试一次且复用同一个_request_id(self) -> None:
        gateway = FakeGateway(
            XjxHttpResult(502, "busy"),
            XjxHttpResult(502, "busy"),
            _ok({"success": True}),  
        )
        result = await XjxFetchMeihuaSkill().run(_ctx(gateway), n1=1, n2=2)

        assert result["code"] == "upstream_busy"
        assert len(gateway.calls) == 2
        assert gateway.calls[0][1]["request_id"] == gateway.calls[1][1]["request_id"]

    @pytest.mark.asyncio
    async def test_502_后重试成功(self) -> None:
        gateway = FakeGateway(XjxHttpResult(503, "busy"), _ok({"success": True, "report": {}}))
        result = await XjxFetchAstroSkill().run(_ctx(gateway), **ASTRO_BODY)

        assert result["ok"] is True
        assert len(gateway.calls) == 2

    @pytest.mark.asyncio
    async def test_非归属搭子直接用不了(self) -> None:
        gateway = FakeGateway(_ok({"success": True}))
        with pytest.raises(SkillExecutionError) as exc:
            await XjxFetchAstroSkill().run(_ctx(gateway, assistant_id="soulmate"), **ASTRO_BODY)

        assert "Fortune telling Buddy" in str(exc.value)
        assert gateway.calls == []
