"""用户自定义技能（声明式）。

重点测三类"不报错但结果错"的坑，以及一个真实的安全边界。
全部离线（httpx.MockTransport / 不真正跑命令的路径除外）。
"""

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


# --------------------------------------------------------------------------- #
# 模板替换
# --------------------------------------------------------------------------- #
def test_template_replaces_placeholders():
    defn = make_def(body_template='{"q": "{city}"}')
    assert defn.render({"city": "北京"}, defn.body_template) == '{"q": "北京"}'


def test_template_uses_plain_replacement_not_format():
    """``str.format`` 会把模板里的花括号当表达式解析。

    请求体几乎都是 JSON，用 format 的话**写个合法的 JSON 模板都会炸**，
    所以必须用朴素替换。
    """
    defn = make_def(
        body_template='{"a": "{city}", "b": {"nested": 1}}',
    )
    # 这一句在 format 下会抛 KeyError/ValueError；朴素替换应该原样通过
    assert '"nested": 1' in defn.render({"city": "x"}, defn.body_template)


def test_missing_param_falls_back_to_default_or_empty():
    defn = make_def(
        params=[CustomSkillParam(name="city", description="c", required=False, default="上海")]
    )
    assert defn.render({}, defn.url) == "https://api.example.com/weather?q=上海"
    assert defn.render({"city": ""}, defn.url).endswith("q=")


# --------------------------------------------------------------------------- #
# 元数据
# --------------------------------------------------------------------------- #
def test_meta_is_on_the_class_not_the_instance():
    """``SkillManager.register`` 读的是 ``type(instance).meta``。

    meta 挂在实例上时，register 会拿不到（或拿到 None）—— 表现为注册失败。
    """
    cls = build_custom_skill_class(make_def())
    assert isinstance(getattr(cls, "meta", None), SkillMeta)
    assert cls.meta.name == "weather"
    assert cls.meta.source == "custom"
    assert cls.meta.category == "custom"
    # 工具 Schema 由参数定义生成，模型靠它知道要传什么
    assert cls.meta.parameters["required"] == ["city"]


def test_permission_level_carries_through():
    cls = build_custom_skill_class(make_def(permission_level="admin"))
    assert cls.meta.permission_level == "admin"


# --------------------------------------------------------------------------- #
# 命令型技能：argv 化（第 84 批，防命令注入）
# --------------------------------------------------------------------------- #
def test_command_template_splits_into_argv_without_shell_semantics():
    """模板按 argv 切分：引号里的空格算一个参数、Windows 路径的反斜杠原样保留。

    用 ``shlex`` 做切分会把 ``\\`` 当转义符吃掉（``C:\\Program Files`` 被切坏），
    所以这里用的是自己那份极简切分（见 ``CustomSkillDef._split_command_template``）。
    """
    defn = make_def(
        kind="command",
        command_template='"C:\\Program Files\\tool.exe" --out {city}',
    )
    assert defn.render_argv({"city": "a b.txt"}, defn.command_template) == [
        "C:\\Program Files\\tool.exe",
        "--out",
        "a b.txt",  # ← 值里的空格**不会**把它切成两个参数
    ]


def test_command_placeholder_value_cannot_inject_shell_syntax():
    """⚠️ 本次最重要的一条：占位值里的 ``&`` / ``|`` / ``>`` 只能是**普通字符**。

    值来自**模型**，以前是拼进 ``create_subprocess_shell`` 的一条命令串 ——
    ``{payload}`` 被填成 ``x & del /f /q ...`` 时 shell 会当成两条命令执行。
    先切 token、再逐 token 替换占位符，值里有什么都改变不了参数结构。
    """
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
    """真的跑一次：参数里的 ``&`` 必须仍留在**同一个** argv 元素里。

    与上一条的区别：上一条验"算出来的 argv"，这条验**执行侧**确实没经过 shell
    （改回 ``create_subprocess_shell`` 时，``&`` 会把命令截断，这条会红）。
    """
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
    """确认卡上的「将执行的命令」只对命令型技能生成，且它**不进** ``to_dict()``。"""
    cmd = build_custom_skill_class(make_def(kind="command", command_template="ping {city}"))
    http = build_custom_skill_class(make_def())
    assert cmd.meta.command_preview is not None
    assert cmd.meta.command_preview({"city": "example.com"}) == "ping example.com"
    assert http.meta.command_preview is None
    # ⚠️ 它是个函数，混进下发字段会炸掉 /v1/skills（JSON 序列化）
    assert "command_preview" not in cmd.meta.to_dict()


def test_confirm_card_includes_the_rendered_command():
    """确认卡必须能说清"到底会跑什么"：把渲染后的命令补成一行参数。"""
    from my_agent.security.permission import PermissionGuard

    meta = SkillMeta(
        name="mytool",
        description="d",
        permission_level="confirm",
        command_preview=lambda values: f"ping {values.get('host')}",
    )
    merged = PermissionGuard._with_command_preview(meta, {"host": "example.com"})
    assert merged["将执行的命令"] == "ping example.com"
    assert merged["host"] == "example.com"  # 原参数一个不少

    # 没有预览器的技能（含所有内置技能）**原样返回**，不新增任何字段
    plain = SkillMeta(name="plain", description="d")
    same = {"a": 1}
    assert PermissionGuard._with_command_preview(plain, same) is same


# --------------------------------------------------------------------------- #
# HTTP 执行
# --------------------------------------------------------------------------- #
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
        # 直接替换实例上的客户端：让请求落到 MockTransport
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
    # 中文会被 httpx 按 URL 规则编码（%E5%8C%97%E4%BA%AC = 北京），
    # 所以断言"占位符被替换了"而不是断言原文
    assert "q=%E5%8C%97%E4%BA%AC" in str(seen[0].url)


def test_http_blocks_metadata_endpoint():
    """与 security/urls.py 同一条红线：这些地址被访问到就等于失陷。"""
    cls = build_custom_skill_class(
        make_def(url="http://169.254.169.254/latest/meta-data/")
    )
    with pytest.raises(SkillExecutionError):
        run(cls, city="x")


def test_http_reports_error_status():
    cls = build_custom_skill_class(make_def())
    with pytest.raises(SkillExecutionError):
        run(cls, city="x")


# --------------------------------------------------------------------------- #
# 命令执行
# --------------------------------------------------------------------------- #
def test_command_runs_and_returns_output():
    """命令跑通后输出会原样回填。

    ⚠️ 这条以前用的模板是 ``echo {city}``。``echo`` 是 cmd 的**内置命令**，
    只有经过 shell 时才存在；第 84 批把命令改成 argv + ``create_subprocess_exec``
    （防命令注入）之后，内置命令与管道 / 重定向一并失效 —— 所以这里换成
    "解释器 + 一段脚本"这种在**任何机器上都成立、且本来就不经 shell** 的写法。
    被测的行为没有变：**命令的输出要回到调用方**。
    """
    import sys

    template = '"' + sys.executable + '" -c "print(\'{city}\')"'
    cls = build_custom_skill_class(
        make_def(kind="command", command_template=template, timeout=30)
    )
    result = run(cls, city="hello")
    assert "hello" in result


def test_command_failure_surfaces_exit_code():
    """退出码非 0 必须带着**完整输出**报出来（不能只留一句"失败了"）。"""
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
