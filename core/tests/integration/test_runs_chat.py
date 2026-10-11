"""单聊的断点续跑：没跑完要留下"接着做"的现场。

这组守的是三种结局，它们的处理方式**不一样**，混在一起就会骗用户：

1. 正常跑完 → 不留痕（否则界面上永远挂着一个「继续」）；
2. 步数用尽 → 记 ``incomplete``，**不是** ``failed``：引擎自己都说"这不是出错，
   是防失控的兜底"，而且它和失败的处理方向相反（一个能接着做，一个要去修配置）；
3. 用户点停止 → 记 ``cancelled``，并且"接着要说的那句话"由**后端**给出来 ——
   零基础用户不需要知道要自己打「继续」两个字（这正是本次反转上次结论的原因）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from my_agent.llm.base import LLMResponse, StreamChunk

from ..conftest import FakeLLM, tool_call
from .conftest import install_fake_model, read_sse


def _register_probe(runtime, calls: list[str]) -> None:
    """注册一个 safe 级探针技能：用它把"来回跑很多步"造出来。"""
    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name="probe_steps",
        display_name="探针",
        description="测试用探针（无副作用）",
        permission_level="safe",
    )
    class _Probe(BaseSkill):
        async def run(self, ctx, **params):  # type: ignore[no-untyped-def]
            calls.append("probe_steps")
            return "ok"

    runtime.skills.register(_Probe)


async def _chat_runs(runtime) -> list:
    """待续跑列表里的单聊记录（跑完的不会在这里）。"""
    return [run for run in await runtime.runs.list_pending() if run.kind == "chat"]


async def _wait_chat_run(runtime, *, timeout: float = 30.0):
    """等收尾把进度行写出来。

    收尾发生在响应生成器的 finally 里，与"客户端读到流结束"**不是严格同步**的：
    那之后还要落盘、归档长期记忆、记用量、存 trace、最后才写进度行。
    所以只能轮询，不能读完流就断言。

    ⚠️ 超时从 5s 放宽到 30s 是**有意**的（第 89 批，M-30）：
    整跑（七百多个用例、机器同时在做文件索引/杀软扫描）时这一段偶尔会超过 5 秒，
    于是用例报 "run is None" —— 看起来像"停止没有留下可续跑的现场"这个功能坏了，
    实际只是机器慢。**这类假红最贵**：它会让人去改一段其实没问题的代码
    （`test_runs_chat` 那组历史上就被当成过"已知 flaky"挂着）。
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        rows = await _chat_runs(runtime)
        if rows:
            return rows[0]
        await asyncio.sleep(0.05)
    return None


@pytest.mark.asyncio
async def test_finished_chat_leaves_no_pending_run(runtime, client):
    install_fake_model(runtime, FakeLLM(["你好呀"]))
    await read_sse(client, {"message": "你好", "model_id": "fake"})

    assert await _chat_runs(runtime) == []


@pytest.mark.asyncio
async def test_step_limit_leaves_incomplete_run_and_gives_resume_topic(runtime, client):
    """步数用尽 → 「没做完」（而不是「失败」），并且续跑能把那句话给回来。"""
    calls: list[str] = []
    _register_probe(runtime, calls)
    runtime.config.settings.agent.max_iterations = 2
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    content="",
                    tool_calls=[tool_call("probe_steps", {})],
                    finish_reason="tool_calls",
                ),
                LLMResponse(
                    content="",
                    tool_calls=[tool_call("probe_steps", {})],
                    finish_reason="tool_calls",
                ),
            ]
        ),
    )

    events = await read_sse(client, {"message": "一直做下去", "model_id": "fake"})
    # 先把"引擎确实是因为步数用尽才停的"钉住，否则下面几条断言可能因为别的原因通过
    assert any(
        name == "error" and data.get("code") == "agent_max_iterations"
        for name, data in events
    )
    assert calls == ["probe_steps", "probe_steps"]

    run = await _wait_chat_run(runtime)
    assert run is not None, "没跑完的单聊必须留下可续跑的现场"
    assert run.status == "incomplete"
    assert run.step == 2
    assert run.last_action == "探针"
    assert run.session_id

    listed = (await client.get("/v1/runs")).json()["runs"]
    item = next(entry for entry in listed if entry["id"] == run.id)
    # 给用户看的那句话要能区分"没做完"和"失败"，而且要把引擎给的**去哪儿改**带出来
    assert "没做完" in item["summary"]
    assert "上限" in item["summary"]

    resumed = (await client.post(f"/v1/runs/{run.id}/resume")).json()
    assert resumed["kind"] == "chat"
    assert resumed["session_id"] == run.session_id
    # 接着要说的那句由后端给（它是协议的一部分，不该散落在界面文案里）
    assert "续跑" in resumed["topic"] and "不要重做" in resumed["topic"]
    # 续跑后这条就该消失：否则「继续」一直挂着，用户会以为点了没反应
    assert await _chat_runs(runtime) == []


class _SlowLLM(FakeLLM):
    """永远说不完的模型：用来制造"用户中途点停止"。

    继承 ``FakeLLM`` 只为省掉 ``chat`` 的实现；覆盖 ``stream`` 时**必须**连带
    接受采样参数（Agent 会无条件传 top_p / frequency_penalty / presence_penalty），
    只写 temperature 会让这里抛 TypeError —— 而表现是"停止返回 cancelled=0"，
    看起来像取消功能坏了，跟签名一点关系都没有。
    """

    def __init__(self) -> None:
        super().__init__([])

    async def stream(  # type: ignore[override]
        self, messages, tools=None, *, temperature=0.7, max_tokens=None, **_sampling
    ):
        for _ in range(500):
            await asyncio.sleep(0.05)
            yield StreamChunk(delta="…")


@pytest.mark.asyncio
async def test_user_stop_keeps_a_resumable_run(runtime, client):
    """点了停止也要能接着做。

    ⚠️ 这里最容易写错的一处：``/v1/stop`` 取消的是**生产者**，而生产者收尾时会往
    队列塞一个 None（"流结束"），消费端看到的是一次"正常读完"。只看"读完了吗"，
    用户明明按了停止却连「继续」都不给 —— 判据必须是任务自身的取消状态。
    """
    install_fake_model(runtime, _SlowLLM())

    stopped_once = False
    # ⚠️ 刻意**读到流自然结束**，而不是收到 meta 就 `break`（第 89 批，M-30）。
    #
    # `break` 会让 httpx 立刻关闭响应，于是"客户端中途断开"与"服务端收尾"这两件事
    # 挤在一起赛跑 —— 那正是这组用例偶发 `CancelledError` 的来源（断开时机随机器负载漂移）。
    # 而真实的界面**不会**在点了停止之后立刻把连接掐掉：它会一直读到服务端收尾。
    # 顺着真实行为写，竞态就没了；顺带还多验了一条：**停止之后流必须正常收尾**
    #（`/v1/stop` 取消生产者 → 生产者 finally 补一个结束哨兵 → 消费端正常退出）。
    async with client.stream(
        "POST", "/v1/chat", json={"message": "慢慢说", "model_id": "fake"}
    ) as resp:
        current = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
                continue
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if current == "meta":
                result = await client.post("/v1/stop", json={"task_id": data["task_id"]})
                assert result.json()["cancelled"] == 1
                stopped_once = True
            current = None

    assert stopped_once, "没读到 meta 事件，说明这次停止根本没发生（下面的断言就不可信了）"

    run = await _wait_chat_run(runtime)
    assert run is not None, "被停下的单聊同样要留下现场（用户常常只是按错了）"
    assert run.status == "cancelled"
    assert run.session_id
