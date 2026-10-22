





from __future__ import annotations

import httpx
import pytest

from my_agent.config.schemas import CustomSkillDef, CustomSkillParam
from my_agent.errors import SkillExecutionError
from my_agent.skill.base import SkillMeta
from my_agent.skill.custom import build_custom_skill_class


def make_def(**overrides) -> CustomSkillDef:
    base = dict(
        id="weather",
        name="天气",
        description="查天气",
        params=[CustomSkillParam(name="city", description="城市名")],
        kind="http",
        url="https://api.example.com/weather?q={city}",
        method="GET",
    )
    base.update(overrides)
    return CustomSkillDef(**base)


def run(cls, **params):
    import asyncio

    return asyncio.run(cls().run(None, **params))





def test_template_replaces_placeholders():
    defn = make_def(body_template='{"q": "{city}"}')
    assert defn.render({"city": "北京"}, defn.body_template) == '{"q": "北京"}'


def test_template_uses_plain_replacement_not_format():





    defn = make_def(
        body_template='{"a": "{city}", "b": {"nested": 1}}',
    )
    
    assert '"nested": 1' in defn.render({"city": "x"}, defn.body_template)


def test_missing_param_falls_back_to_default_or_empty():
    defn = make_def(
        params=[CustomSkillParam(name="city", description="c", required=False, default="上海")]
    )
    assert defn.render({}, defn.url) == "https://api.example.com/weather?q=上海"
    assert defn.render({"city": ""}, defn.url).endswith("q=")





def test_meta_is_on_the_class_not_the_instance():




    cls = build_custom_skill_class(make_def())
    assert isinstance(getattr(cls, "meta", None), SkillMeta)
    assert cls.meta.name == "weather"
    assert cls.meta.source == "custom"
    assert cls.meta.category == "custom"
    
    assert cls.meta.parameters["required"] == ["city"]


def test_permission_level_carries_through():
    cls = build_custom_skill_class(make_def(permission_level="admin"))
    assert cls.meta.permission_level == "admin"





def test_command_template_splits_into_argv_without_shell_semantics():





    defn = make_def(
        kind="command",
        command_template='"C:\\Program Files\\tool.exe" --out {city}',
    )
    assert defn.render_argv({"city": "a b.txt"}, defn.command_template) == [
        "C:\\Program Files\\tool.exe",
        "--out",
        "a b.txt",  
    ]


def test_command_placeholder_value_cannot_inject_shell_syntax():






    defn = make_def(
        kind="command",
        command_template="tool {payload}",
        params=[CustomSkillParam(name="payload", description="随便什么")],
    )
    assert defn.render_argv({"payload": "x & del /f /q C:\\"}, defn.command_template) == [
        "tool",
        "x & del /f /q C:\\",
    ]


@pytest.mark.asyncio
async def test_command_actually_runs_via_exec_not_shell():





    import json
    import sys

    from my_agent.skill.custom import _run_command

    script = "import sys,json;print(json.dumps(sys.argv[1:]))"
    defn = make_def(
        kind="command",
        command_template=f'"{sys.executable}" -c "{script}" {{payload}}',
        params=[CustomSkillParam(name="payload", description="随便什么")],
    )
    payload = "x & del /f /q C:\\"
    output = await _run_command(defn, {"payload": payload})
    assert json.loads(output) == [payload]


def test_only_command_skills_get_a_command_preview():

    cmd = build_custom_skill_class(make_def(kind="command", command_template="ping {city}"))
    http = build_custom_skill_class(make_def())
    assert cmd.meta.command_preview is not None
    assert cmd.meta.command_preview({"city": "example.com"}) == "ping example.com"
    assert http.meta.command_preview is None
    
    assert "command_preview" not in cmd.meta.to_dict()


def test_confirm_card_includes_the_rendered_command():

    from my_agent.security.permission import PermissionGuard

    meta = SkillMeta(
        name="mytool",
        description="d",
        permission_level="confirm",
        command_preview=lambda values: f"ping {values.get('host')}",
    )
    merged = PermissionGuard._with_command_preview(meta, {"host": "example.com"})
    assert merged["将执行的命令"] == "ping example.com"
    assert merged["host"] == "example.com"  

    
    plain = SkillMeta(name="plain", description="d")
    same = {"a": 1}
    assert PermissionGuard._with_command_preview(plain, same) is same





def test_http_sends_rendered_request():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="晴 26 度")

    cls = build_custom_skill_class(make_def())
    cls._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    import asyncio

    async def go():
        skill = cls()
        
        from my_agent.skill import custom as custom_module

        original = custom_module.httpx.AsyncClient

        class FakeClient(original):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = httpx.MockTransport(handler)
                super().__init__(*args, **kwargs)

        custom_module.httpx.AsyncClient = FakeClient
        try:
            return await skill.run(None, city="北京")
        finally:
            custom_module.httpx.AsyncClient = original

    result = asyncio.run(go())
    assert "晴" in result
    
    
    assert "q=%E5%8C%97%E4%BA%AC" in str(seen[0].url)


def test_http_blocks_metadata_endpoint():

    cls = build_custom_skill_class(
        make_def(url="http://169.254.169.254/latest/meta-data/")
    )
    with pytest.raises(SkillExecutionError):
        run(cls, city="x")


def test_http_reports_error_status():
    cls = build_custom_skill_class(make_def())
    with pytest.raises(SkillExecutionError):
        run(cls, city="x")





def test_command_runs_and_returns_output():








    import sys

    template = '"' + sys.executable + '" -c "print(\'{city}\')"'
    cls = build_custom_skill_class(
        make_def(kind="command", command_template=template, timeout=30)
    )
    result = run(cls, city="hello")
    assert "hello" in result


def test_command_failure_surfaces_exit_code():

    import sys

    cls = build_custom_skill_class(
        make_def(
            kind="command",
            command_template='"' + sys.executable + '" -c "import sys;sys.exit(3)"',
            timeout=30,
        )
    )
    with pytest.raises(SkillExecutionError) as exc:
        run(cls)
    assert "3" in str(exc.value)
