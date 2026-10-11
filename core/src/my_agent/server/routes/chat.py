"""对话接口（SSE 流式）。

这是整个客户端最核心的接口。设计要点：

1. **生产者/消费者解耦**：Agent 在独立 asyncio 任务里跑，把事件塞进队列；
   响应生成器从队列取事件转成 SSE。这样即使前端读得慢也不会阻塞 Agent。
2. **人工确认**：Agent 需要确认时，通过确认回调把 ``permission_request``
   事件塞进**同一个队列**，然后挂起等待 ``POST /v1/confirm`` 回传。
3. **断开即取消**：生成器被关闭（客户端断开/点了停止）时，finally 里取消
   Agent 任务，避免后台空跑烧 token。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ...agent.context import ContextPolicy
from ...agent.engine import Agent, AgentConfig, AgentEvent
from ...llm.base import ImagePart
from ...llm.router import ModelRouter
from ...observability.metrics import METRICS
from ...observability.request_context import bind_session, current_session_id
from ...observability.tracer import Tracer
from ...skill.base import ConfirmRequest, InteractionRequest, SkillContext
from ...skill.custom import persona_with_instructions

# 图片的"校验格式 + 编码"只有这一份实现（搭子头像那条路也走它）。
# 曾经这里自己写了一遍 —— 两份实现的后果是"能当头像的图不能发给模型"这类
# 谁也解释不清的差异。
from ...storage.images import ImageSourceError, encode_data_url
from ..deps import get_runtime
from ..runtime import AppRuntime
from ..sse import format_sse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


ATTACHMENT_OPEN = "[附件]"
ATTACHMENT_CLOSE = "[/附件]"


class ChatRequest(BaseModel):
    # ⚠️ 这里**允许空文本**（产品要求）：很多任务整份都在附件里，
    # 逼用户再打一句废话是不合理的（他的原话：「很多时候任务已经包含在附件当中」）。
    # 合法性由"文本或附件至少有一个"来判定（见 chat 路由里的校验），
    # 而不是靠 pydantic 的 min_length 把"只发附件"这条路直接堵死。
    message: str = Field(
        "",
        description="用户输入；**可以为空**（只发附件时），但 attachments / images 至少要有一个",
    )
    session_id: str | None = None
    model_id: str | None = None
    assistant_id: str | None = Field(
        None, description="助手预设 id；显式传入即把会话切到该助手"
    )
    attachments: list[str] = Field(
        default_factory=list,
        description="工作区文件 id 列表（由 /v1/files/upload 返回）",
    )
    images: list[str] = Field(
        default_factory=list,
        description=(
            "作为**图片**附加到本轮消息的工作区文件 id 列表。"
            "与 attachments 的区别：attachments 只是把文件名与路径写进文字里，"
            "images 会把图片本身发给模型（需要模型支持图片输入）。"
        ),
    )
    reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        None,
        description=(
            "思考强度：low / medium / high；空串表示关掉。"
            "**字段缺席表示不改变会话当前的设置** —— 这与空串是两回事，"
            "靠 pydantic 的 model_fields_set 区分，避免老客户端把用户调过的档位清掉。"
        ),
    )

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _blank_reasoning_effort_means_off(cls, value: Any) -> Any:
        """空串一律当成"关掉"（``None``），与 ``routes/groups.py`` 的 ``GroupUpdate`` 同一套做法。

        前端下拉框里"不发送（服务商默认）"那一项的值就是空串 —— 不在这里归一化，
        它会先被 ``Literal`` 拦成 422，用户看到的是一个莫名其妙的报错。

        ⚠️ 把类型收紧是有原因的：以前这里是 ``str | None``，于是 ``"hight"`` 这种拼错
        会被**接受并落库**，之后整轮**根本不会发**这个字段（``payload_for()`` 返回 ``{}``），
        只在引擎里冒一条"你选了档位但没思考内容"的**误导性** warning ——
        用户完全不知道自己错在哪（见 `agent/engine.py` 那段文案）。
        现在非法值会被明确拒绝。
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ConfirmDecision(BaseModel):
    request_id: str
    approved: bool


class PlanDecision(BaseModel):
    """用户对执行计划的决定（单聊计划模式）。

    一个接口表达三种决定，靠 ``approved`` 与 ``feedback`` 的组合区分 ——
    硬拆成三个接口会让前端"改一下"这种要带文本的场景多一次往返。
    """

    plan_id: str = Field(..., description="计划 id，来自 plan 事件，前端原样回传")
    approved: bool = Field(False, description="True = 「开始执行」")
    feedback: str = Field(
        "",
        description=(
            "approved=False 时使用：**非空**表示「改一下」并带上用户的意见，"
            "AI 会据此重拟计划；**空**表示「不用了」，本次任务到此为止。"
        ),
    )


class StopRequest(BaseModel):
    task_id: str | None = None
    session_id: str | None = None


# 帧格式统一在 `server/sse.py`。这个文件、`groups.py` 与 `routes/events.py`
# 曾各写一份，而 `groups` 那份漏了 `default=str` —— 同一个对外协议两种行为。
_sse = format_sse


async def build_attachment_block(runtime: AppRuntime, file_ids: list[str]) -> str | None:
    """把附件 id 解析成一段可读的上下文，拼在用户消息前面。

    模型只能通过**文件路径**来操作文件（后续的 excel_read / doc_parse 等
    Skill 接收的都是路径），所以这里必须给出真实绝对路径与原始文件名，
    否则模型会去猜文件名。

    整段内容包裹在 ``[附件]...[/附件]`` 之间，前端可以据此在展示时剥掉它。
    """
    lines: list[str] = []
    for file_id in file_ids:
        record = await runtime.workspace.get(file_id)
        if record is None:
            lines.append(f"- 附件 {file_id} 不存在或已被删除")
            continue
        try:
            path = runtime.workspace.resolve(record.id, record.kind)
        except Exception:  # noqa: BLE001 - 文件丢失不该阻断对话
            lines.append(f"- 附件 {record.original_name} 已丢失")
            continue
        lines.append(f"- {record.original_name}\n  路径: {path}")

    if not lines:
        return None
    return f"{ATTACHMENT_OPEN}\n用户上传了以下文件，可据此操作：\n" + "\n".join(lines) + f"\n{ATTACHMENT_CLOSE}"


# 一轮最多附几张图。取 4 是因为再多的话单次请求的输入 token 会明显抬高，
# 而绝大多数真实场景（截图、表格、白板照）一张就够。
#: 单轮对话的事件队列上限（第 87 批，M-03）。
#:
#: ⚠️ 以前是**无界**队列，注释写着"即使前端读得慢也不会阻塞 Agent" —— 那说对了一半：
#: 确实不阻塞 Agent，但前端读得慢（比如渲染层卡在长会话重渲染上）时，模型持续产出的
#: `delta` / `tool_result` 会**无限堆积在核心进程内存里**，最终可能把整个
#: 单事件循环进程拖 OOM，**连带其它会话一起丢**。本项目其它队列都有上限
#: （`server/events.py` 的 `QUEUE_SIZE=64`、`mcp/client.py` 的 `maxsize=64`）。
#:
#: ⚠️ 这里**刻意只加上限、不做"丢最旧"降级**（审计建议的是丢弃）：`permission_request`
#: / `plan_decision` / `interaction_request` 这类**控制事件**一旦被丢，那条挂起就
#: **永远等不到回答**（这几条通道刻意不设超时），整轮会永久卡死。
#: 而有界 + `await queue.put()` 本身就是**背压**：消费端一恢复，生产端自然继续 ——
#: 既不丢数据，也不让内存无界增长。客户端断开时消费者会取消生产者任务
#: （见本文件头"断开即取消"），所以背压不会变成泄漏。
#:
#: 取 512：一轮正常产生的事件是几百量级，真撞到上限说明消费端已经卡住了。
TURN_QUEUE_SIZE = 512

MAX_IMAGES_PER_TURN = 4
# 单张图片的字节上限。超了明确报错而不是静默截断 —— 一张被"悄悄处理过"
# 的图会让用户以为模型看不清，实际是我们压过了。
MAX_IMAGE_BYTES = 8 * 1024 * 1024


async def build_image_parts(runtime: AppRuntime, file_ids: list[str]) -> list[ImagePart]:
    """把工作区文件 id 解析成可以发给模型的图片。

    **用文件 id 而不是直接收 base64**：data URL 会被塞进消息里一路带着走，
    而这个应用里图片本来就是工作区资产（有上传接口、有存储目录、界面可见）。
    走 id 之后落盘、清理、体积统计都复用同一套逻辑，也不会有一份 base64
    副本留在请求日志里。
    """
    parts: list[ImagePart] = []
    for file_id in file_ids[:MAX_IMAGES_PER_TURN]:
        record = await runtime.workspace.get(file_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"图片附件 {file_id} 不存在")
        try:
            path = runtime.workspace.resolve(record.id, record.kind)
            # ⚠️ **先按大小判上限、再读内容**（第 87 批，M-02）：以前是先
            # `read_bytes()` 再比上限 —— 工作区里一个几十 MB 的"图片"会被
            # **整份读进内存**才被拒（单张上限 8MB，而附件总上限是 50MB）。
            size = path.stat().st_size
            if size > MAX_IMAGE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"图片「{record.original_name}」{size // 1024 // 1024}MB，"
                        f"超过 {MAX_IMAGE_BYTES // 1024 // 1024}MB 上限。请先压缩后再上传。"
                    ),
                )
            # ⚠️ 读盘丢进**线程**：这里是 `async def`，同步 `read_bytes()` 会阻塞
            # **单个事件循环** —— 一次附 4 张接近 8MB 的截图时，所有会话的 SSE
            # 会一起卡住几百毫秒。本项目其余读盘都走了 `asyncio.to_thread`
            #（见 `storage/files.py` / `storage/media.py`），这里以前漏了。
            raw = await asyncio.to_thread(path.read_bytes)
        except HTTPException:
            # 上面那个 413 就是 HTTPException，别被下面的兜底吞成 422
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=422, detail=f"图片附件 {record.original_name} 无法读取：{exc}"
            ) from exc

        # 格式与编码交给 storage/images 那一份实现。它按**魔数**判格式，而不是
        # 信 `record.mime`（那是客户端声明上来的）：一个其实是 webp、名字叫 .png
        # 的文件以前会一路通过，最后在模型那边变成一个"看不清"的怪问题。
        try:
            mime, data_url = encode_data_url(
                raw, max_bytes=MAX_IMAGE_BYTES, label=f"图片「{record.original_name}」"
            )
        except ImageSourceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        parts.append(ImagePart(mime=mime, data_url=data_url, name=record.original_name))
    return parts


@router.post("/v1/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    runtime: AppRuntime = get_runtime(request)
    settings = runtime.config.settings

    # 既没文字也没附件 → 明确拒绝并说清原因（而不是让它空跑一轮模型）
    if not payload.message.strip() and not payload.attachments and not payload.images:
        raise HTTPException(
            status_code=400,
            detail="既没有输入文字，也没有附件 —— 请说点什么，或者加一个附件。",
        )

    session = await runtime.get_session(payload.session_id, model_id=payload.model_id)

    # ---- 助手：显式指定 > 会话已绑定 > 不指定 -------------------------- #
    # 先应用助手，再让显式 model_id 覆盖：优先级是
    # 「助手默认模型 < 用户在工具条上手选的模型」
    profile = None
    if payload.assistant_id:
        profile = runtime.resolve_assistant(payload.assistant_id)
        if profile is None:
            raise HTTPException(
                status_code=404, detail=f"助手「{payload.assistant_id}」不存在"
            )
        session.apply_assistant(profile)
    elif session.assistant_id:
        # 会话绑定的助手可能已被删除；此时沿用会话里已经解析好的配置，不报错，
        # 否则用户删除一个助手会让所有历史会话都打不开
        profile = runtime.resolve_assistant(session.assistant_id)
        if profile is not None:
            session.apply_assistant(profile)

    # ---- 思考强度 ------------------------------------------------------ #
    # **只在客户端显式传了这个字段时才改**（`model_fields_set` 能区分"没传"与"传了空串"）。
    # 用"传了就覆盖"的简单写法会踩同一个坑：老客户端没带这个字段，
    # 一次保存就把用户调好的档位清成默认。
    if "reasoning_effort" in payload.model_fields_set:
        session.reasoning_effort = (payload.reasoning_effort or "").strip() or None

    # ---- 模型路由 ------------------------------------------------------ #
    # 只在"用户/助手都没有指定模型"时才路由。指定了就必须听用户的：
    # 悄悄换掉他手选的模型，比多花点钱糟糕得多。
    requested_model = payload.model_id or session.model_id
    model_id = requested_model or runtime.config.models.default_model

    if requested_model is None and settings.agent.enable_model_routing:
        routed = ModelRouter(
            default_id=runtime.config.models.default_model,
            candidates=runtime.config.models.models,
        ).pick(
            text=payload.message,
            need_tools=len(runtime.skills) > 0,
        )
        if routed:
            model_id = routed

    if len(runtime.registry) == 0:
        # 空清单是**新装的正常状态**（出厂不再硬塞默认模型）。在这里用 400
        # 给出引导，而不是让 registry 抛"未知模型"——那是配置错了的措辞，
        # 而用户只是还没配。
        raise HTTPException(
            status_code=400,
            detail="还没有配置任何模型。请先在「设置 → 模型服务商」里添加一个，或重新运行首次引导。",
        )
    llm = runtime.registry.get(model_id)

    session.model_id = model_id
    session.auto_title(payload.message)
    session.touch()

    # 附件信息拼在用户消息前面送进模型；标题仍用用户原始输入
    user_text = payload.message
    if payload.attachments:
        block = await build_attachment_block(runtime, payload.attachments)
        if block:
            user_text = f"{block}\n\n{payload.message}"

    # ---- 图片附件 ------------------------------------------------------ #
    spec = runtime.config.models.get(model_id)
    supports_vision = bool(spec and spec.supports_vision)
    image_parts: list[ImagePart] = []
    vision_notice = ""

    if payload.images:
        if supports_vision:
            image_parts = await build_image_parts(runtime, payload.images)
        else:
            # **刻意不静默丢弃。** 用户特意附了图，如果回答完全无视它，
            # 他会以为是模型能力不行，而不会想到"这个模型根本没开图片支持"。
            # 图片依然不发（发出去整条请求会被厂商直接拒掉，连文字都拿不到回复），
            # 但必须让他知道发生了什么、以及去哪儿打开。
            vision_notice = (
                f"本轮附带的 {len(payload.images)} 张图片没有被发送："
                f"模型「{model_id}」未标记为支持图片输入。"
                "可在「设置 → 模型」中为该模型勾选「支持图片」。"
            )

    tracer = Tracer(enabled=settings.trace_enabled)
    # 上限 + `await put` = 背压（理由见 `TURN_QUEUE_SIZE` 那段）
    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue(maxsize=TURN_QUEUE_SIZE)

    # ---- 确认通道：把确认请求推到 SSE 流，并挂起等待前端回传 ---------- #
    async def emit_confirm(confirm: ConfirmRequest) -> None:
        await queue.put(
            AgentEvent(
                "permission_request",
                {
                    "request_id": confirm.request_id,
                    "skill_name": confirm.skill_name,
                    "display_name": confirm.display_name,
                    "description": confirm.description,
                    "permission_level": confirm.permission_level,
                    "params": confirm.params,
                    "prompt": confirm.prompt,
                },
            )
        )

    async def confirm_callback(confirm: ConfirmRequest) -> bool:
        return await runtime.request_confirm(confirm, emit_confirm, owner=session.id)

    # ---- 交互通道：技能要问用户时（选择 / 敏感输入）--------------------- #
    #
    # 与确认通道同形（推事件 + 挂起等回传），但**不设超时**、答案是任意结构。
    # ⚠️ 只走单聊与群聊：定时任务与 CLI 不注入，技能会自动降级成
    # "按最可能的理解往下做"（见 SkillContext.ask_interaction）。
    async def emit_interaction(interaction: InteractionRequest) -> None:
        await queue.put(AgentEvent("interaction_request", interaction.to_dict()))

    async def interaction_callback(interaction: InteractionRequest) -> dict[str, Any]:
        return await runtime.request_interaction(interaction, emit_interaction, owner=session.id)

    # ---- 计划确认通道（单聊计划模式）----------------------------------- #
    #
    # 与权限确认共用"挂起—回传"这套形态，但语义不同：**不设超时**，
    # 用户盯着计划想多久都行（理由见 runtime.request_plan_decision）。
    async def plan_decider(plan: dict[str, Any]) -> tuple[bool, str]:
        """把决定权交给用户：挂起，直到前端 POST /v1/plan/decision。

        ``plan`` 事件早就由引擎推给前端了（顺序在挂起之前），所以这里只管等 ——
        卡片上有得点，才需要等下去。

        用**计划自带的 id**（而不是这里新生成一个）：前端把收到的 id 原样回传，
        两边对得上才对得回这一份计划。
        """
        return await runtime.request_plan_decision(str(plan.get("id") or uuid4().hex), owner=session.id)

    ctx = SkillContext(
        settings=settings,
        tracer=tracer,
        paths=runtime.paths,
        confirm=confirm_callback,
        interaction=interaction_callback,
        audit=runtime.audit.record,
        session_id=session.id,
        assistant_id=session.assistant_id,
        workspace=runtime.workspace,
        path_policy=runtime.path_policy,
        extra=runtime.skill_services_for(session.assistant_id),
        logger=logging.getLogger("my_agent.skill"),
        # 助手可以给这个会话指定专属的权限策略（例如数据分析师一律不许写文件）。
        # ⚠️ 传**闭包**而不是取值：任务跑到一半时用户改了搭子的权限策略，后续
        # 工具调用要立刻按新策略走（见 PermissionGuard.effective_mode）。
        #
        # ⚠️⚠️ **单聊的权限只来自这里，绝不能读群设置**（特别强调：
        # "单聊的权限设置是管每个搭子在单聊中权限的；群聊的权限设置是管群里每个
        # 搭子在群聊当中权限的，千万不能搞混"）。
        # 群聊那份在 `routes/groups.py` 的 `live_confirm_mode` 里，顺序是
        # 群设置 → 成员档案 → 全局；**两条链各读各的**，不要在这里加群。
        # 边界由 `tests/integration/test_group_confirm.py` 的
        # `test_群权限设置不会影响单聊` 守着。
        confirm_mode=lambda: runtime.assistant_confirm_mode(session.assistant_id),
    )

    agent_cfg = settings.agent
    agent = Agent(
        llm=llm,
        # 压缩 / 规划 / 自检可以走另一个模型（设置项 agent.utility_model_id）
        utility_llm=runtime.utility_llm(llm),
        skill_manager=runtime.skills,
        memory=session.memory,
        config=AgentConfig(
            # 助手没指定的参数沿用全局设置，而不是硬编码一个默认值——
            # 否则用户在设置里调过的参数会被静默忽略
            max_iterations=(
                profile.max_iterations if profile and profile.max_iterations else agent_cfg.max_iterations
            ),
            max_tool_calls_per_turn=(
                profile.max_tool_calls_per_turn
                if profile and profile.max_tool_calls_per_turn
                else agent_cfg.max_tool_calls_per_turn
            ),
            temperature=(
                profile.temperature
                if profile and profile.temperature is not None
                else agent_cfg.temperature
            ),
            # 这三个只来自全局设置：助手预设里没有对应字段。
            # 加进助手会让"同一个助手在两台机器上表现不同"变得难以解释，
            # 而它们调的是模型行为、不属于人设
            top_p=agent_cfg.top_p,
            frequency_penalty=agent_cfg.frequency_penalty,
            presence_penalty=agent_cfg.presence_penalty,
            # 思考强度取自**会话**而不是全局设置：用户对"这轮值不值得多想一会儿"
            # 的判断是按对话来的。上面的 model_fields_set 保证"客户端没提这个字段"
            # 时不会把它清掉。
            reasoning_effort=session.reasoning_effort,
            # 这里曾有 ``system_prompt=session.system_prompt or
            # agent_cfg.system_prompt``（"自定义提示词 + 内置兜底"那条链的出口），
            # 已按产品要求整体退役：提示词只由下面的 persona 提供。会话与全局的
            # 字段都还留着（零迁移风险），只是没有人再读它们。
            # 助手的人格与记忆文件（SOUL.md / MEMORY.md），再加上**已启用的
            # 指导型技能**（上传技能包里的 SKILL.md）。什么都没有时返回空串，
            # 也就不会给提示词添任何东西 —— 所以没用上这些的用户不会多付一个 token
            # 惰性提供者：助手在同轮里改写人格文件后，引擎能立刻重读（见 engine）
            persona=lambda: persona_with_instructions(  # type: ignore[arg-type,return-value]
                runtime, session.assistant_id, session.enabled_skills
            ),
            same_tool_failure_tolerance=agent_cfg.same_tool_failure_tolerance,
            # ⚠️ 不能直接传 `session.enabled_skills`：那是"用户勾了哪几个"的**原始记录**，
            # 而新口径下"没勾"≠"全开"（没有默认加载全部技能的搭子了，见 skill/groups.py）。
            # 这里统一展开成"内置技能 ∪ 自己的专属 ∪ 勾选的通用/我的"。
            enabled_skills=runtime.skills.allowed_names(
                assistant_id=session.assistant_id,
                enabled_skills=session.enabled_skills,
            ),
            # 专属技能（心鉴学那套 + 搭子总管那批）按"这个会话是哪个搭子在说话"过滤，
            # 见 skill/groups.py
            target_assistant=session.assistant_id or "",
            # 上下文窗口取自**实际选中的模型**，不是全局配置：
            # 路由可能刚把模型换成另一个上下文窗口差别很大的那个。
            # 走 effective_context_tokens 而不是 llm.token_limit，
            # 是为了和 MemoryManager 的裁剪预算用同一个数 —— 两边不一致时
            # 会出现"压缩阈值按 100 万算、实际却在 3.2 万处裁剪"的分裂行为
            token_limit=runtime.effective_context_tokens(model_id),
            context_policy=ContextPolicy(
                keep_recent=agent_cfg.keep_recent_messages,
                compress_threshold=agent_cfg.compress_threshold,
            ),
            # ---- 计划模式：**单聊恒开**（产品约定）------------ #
            #
            # 不读 ``agent_cfg.enable_planner``：那个设置项默认关闭，而用户要的是
            # "装上就能用，不用去设置里找开关"。群聊那边写死 False（见
            # routes/groups.py），定时任务 / 命令行不注入 plan_decider，
            # 所以"只在单聊用"这条口径由**是否注入 decider**统一兜住。
            #
            # 恒开不等于每次都规划：引擎还要过一遍 should_plan（多步任务才出计划），
            # 简单问答一个 token 都不会多花。
            enable_planner=True,
            plan_decider=plan_decider,
            enable_reflection=agent_cfg.enable_reflection,
            reflection_rounds=agent_cfg.reflection_rounds,
        ),
        ctx=ctx,
        tracer=tracer,
    )

    # 本轮实际跑了几轮（done 事件里带），用于用量流水
    run_stats: dict[str, Any] = {}

    # ---- 生产者：跑 Agent，把事件推进队列 ---------------------------- #
    async def produce() -> None:
        try:
            async for event in agent.run_stream(user_text, images=image_parts):
                if event.type == "done":
                    run_stats["iterations"] = int(event.data.get("iterations") or 0)
                await queue.put(event)
        except asyncio.CancelledError:
            logger.info("任务已取消 session=%s", session.id)
            raise
        except Exception as exc:  # noqa: BLE001 - 统一转成 error 事件
            # ⚠️ 必须带关联 ID（第 88 批，M-24）：用户拿着界面上的 trace_id 来反馈时，
            # 一句裸 traceback 在日志里**搜不到任何东西**；而 trace 只在内存里留 100 条，
            # 被淘汰后这条线索就彻底断了。上面那句取消日志带了 session，
            # 同一函数里两句口径不一致本身就是个坑。
            logger.exception(
                "Agent 执行失败 session=%s model=%s trace=%s",
                session.id,
                model_id,
                tracer.trace_id,
            )
            await queue.put(
                AgentEvent(
                    "error",
                    {
                        "code": getattr(exc, "code", "internal_error"),
                        "message": getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}",
                    },
                )
            )
        finally:
            # ⚠️ 队列有上限之后**不能**再用 `put_nowait(None)`：满了会抛 `QueueFull`，
            # 结束哨兵进不去，消费者就**永远等下去**（表现为"回答完了界面一直在转圈"）。
            # 用 `await put` 让它排在队尾（背压），保证哨兵一定送得到。
            await queue.put(None)

    # ---- 消费者：事件 -> SSE ----------------------------------------- #
    async def event_stream() -> AsyncIterator[str]:
        """占一个全局对话位，再把事件流出去。

        闸门放在**会话锁之前**：先拿全局位、再排队等会话锁。
        反过来的话，一个正在排队的请求会先占住会话锁，而它其实还没开始干活 ——
        别的会话看到的"锁被占着"就成了一种假象。
        """
        slot = await runtime.acquire_chat_slot()
        if slot is None:
            # **明确拒绝并说明原因**，而不是让界面一直转圈。
            # "点了发送但什么都不发生"是最难排查的一种失败：
            # 用户既不知道是在排队、还是坏了、还是自己点漏了。
            limit = settings.agent.max_concurrent_chats
            yield _sse(
                "error",
                {
                    "code": "too_many_concurrent",
                    "message": (
                        f"同时进行的对话已达上限（{limit} 个），本次排队超时未执行。"
                        "请等其中一个结束后重试。"
                    ),
                },
            )
            return
        try:
            async for chunk in _stream_events():
                yield chunk
        finally:
            runtime.release_chat_slot(slot)

    async def _stream_events() -> AsyncIterator[str]:
        # 同一会话的对话必须**串行**：锁覆盖「跑 Agent + 落盘」的完整周期。
        # 只锁 Agent 不够 —— persist 是整体替换消息，两个并发请求各替换一次，
        # 后写的会把先写的**整轮覆盖掉**。锁是会话级的，不同会话之间仍完全并行。
        async with session.lock:
            started = asyncio.get_running_loop().time()
            # 落一条"未完成运行"：这一轮要是没跑完（失败 / 被叫停 / 步数用尽），
            # 界面上的「继续」按钮就靠它出现。
            #
            # **为什么落库而不是界面自己判断**：前端拿不到"被取消 / 失败"的权威
            # 状态，只能猜；落库之后刷新、切会话、重启全都自愈 —— 读的是同一张表
            # （与定时任务、群讨论同一套机制，见 storage/runs.py）。
            run_id = await runtime.runs.start(
                kind="chat", ref_id=session.id, session_id=session.id
            )
            # 进度口径与另两处一致：每次**工具执行**算一步。"做到哪一步了"才是
            # 续跑时该告诉模型的东西，它不需要知道写了多少字。
            step = 0
            last_action = ""
            # 这一轮的结局（在 finally 末尾据此决定进度行的去向）。
            # ``completed`` 只表示"事件流被正常读完"，用户点停止 / 界面断开都不走它。
            completed = False
            error_code = ""
            error_message = ""
            partial = False
            # 绑定会话上下文：降级事件这类在**适配器内部**产生的事件拿不到请求信息，
            # 只能靠 ContextVar 归属到会话。
            #
            # 必须在这里设、且必须在 create_task **之前** —— asyncio 任务继承的是
            # **创建时**的上下文；而本生成器由 Starlette 迭代，与路由函数不一定
            # 处在同一个上下文里，所以放在路由入口处设是不可靠的。
            context_token = bind_session(session.id)
            task = asyncio.create_task(produce(), name=f"agent-{session.id}")
            running = runtime.register_task(session.id, task)
            try:
                yield _sse(
                    "meta",
                    {
                        "session_id": session.id,
                        "task_id": running.id,
                        "trace_id": tracer.trace_id,
                        "model_id": model_id,
                    },
                )
                if vision_notice:
                    # 紧跟在 meta 之后、正文之前：用户看到回答的同时就知道
                    # "它其实没看到那张图"，而不是等发现答得不对才回头怀疑
                    yield _sse("warning", {"message": vision_notice})

                while True:
                    event = await queue.get()
                    if event is None:
                        completed = True
                        break
                    data = event.data
                    # 逐个事件把"这一轮跑成什么样"记下来。放在**转发之前**记：
                    # 这条 yield 之后生成器就可能被关掉（用户点停止），
                    # 那时再想补记已经没机会了。
                    if event.type == "tool_result":
                        step += 1
                        last_action = str(
                            data.get("display_name") or data.get("name") or ""
                        )
                        await runtime.runs.progress(run_id, step=step, last_action=last_action)
                    elif event.type == "error":
                        error_code = str(data.get("code") or "error")
                        error_message = str(data.get("message") or "")
                    elif event.type == "done" and data.get("partial"):
                        # 步数用尽。引擎那句文案明确说了"这不是出错，是防失控的
                        # 兜底"，所以它归 incomplete 而不是 failed（见 finally）。
                        partial = True
                    yield _sse(event.type, data)
                if settings.trace_enabled:
                    yield _sse("trace", tracer.export())
            finally:
                # 先把"是被停止的吗"记下来：下面这段收尾会**主动**取消任务，
                # 之后再问就分不清"用户点的停止"和"我们收尾时取消的"了。
                #
                # 为什么非要单独判它：``/v1/stop`` 取消 produce 后，produce 会把
                # None 塞进队列收尾（见上面的 finally），消费端读到的就是一次
                # "正常读完" —— 只看 completed 的话，用户按了停止却连「继续」
                # 都不给。任务自身的取消状态才是权威判据。
                stopped = task.cancelled()
                # 客户端断开或主动停止时，务必取消 Agent 任务
                if not task.done():
                    task.cancel()
                # 必须**等它真正收尾**：cancel() 只是投递信号，engine 的
                # CancelledError 分支（补齐未回填的工具调用、补写部分文本）
                # 发生在这之后。不等就落盘，会出现「内存已修好、库里仍是破损
                # 序列」，下次载入又变回损坏状态，问题看起来像是"修了没用"。
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.gather(task, return_exceptions=True)
                # 只让本会话挂起的确认失效，不要波及别的会话正在等待的确认
                runtime.reject_pending(session.id)
                runtime.unregister_task(running.id)
                # 落盘放在最后：即使前端中途断开，已经产生的对话也必须保住。
                # SessionManager.persist 内部已吞掉数据库异常，不会影响响应收尾。
                await runtime.persist_session(session)

                # 本轮对话归档到该搭子的长期记忆（#4）：取本轮最后一条 user /
                # assistant。history() 已跳过 system/tool/internal 合成消息。
                last_user = ""
                last_assistant = ""
                for item in session.history():
                    if item["role"] == "user":
                        last_user = item["content"]
                    elif item["role"] == "assistant":
                        last_assistant = item["content"]
                await runtime.archive_turn(
                    assistant_id=session.assistant_id,
                    session_id=session.id,
                    user_text=last_user,
                    assistant_text=last_assistant,
                )

                # 把这次 Trace 存进短期留存表，供 `GET /v1/traces/{id}` 查询。
                # 放在 finally 而不是上面的 yield 之后：客户端中途断开时
                # trace 事件根本没机会发出去，而**恰恰是那种情况最需要排查**。
                if settings.trace_enabled:
                    runtime.traces.put(tracer.trace_id, tracer.export())

                # 用 set 返回的 token 复位，而不是再 set(None)：
                # 后者在嵌套场景下会把外层的值一起清掉
                current_session_id.reset(context_token)

                # 记录用量与费用（含缓存命中）。放在落盘之后，并且
                # `UsageService.record` 内部自己吞掉异常 —— 统计失败
                # 绝不能影响"对话已经保住"这件事。（第 102 批起从 runtime 转发改为直调服务。）
                # 被中断的轮次同样要记：那些 token 厂商照收。
                await runtime.usage.record(
                    session_id=session.id,
                    model_id=model_id,
                    usage=tracer.usage,
                    trace_id=tracer.trace_id,
                    duration_ms=round(
                        (asyncio.get_running_loop().time() - started) * 1000, 2
                    ),
                    iterations=int(run_stats.get("iterations", 0)),
                )

                # ---- 这一轮的最终去向：跑完删行，没跑完留成待续跑 ----------- #
                #
                # 放在 finally 的**最后**：前面每一步都会抛（落盘、归档、用量），
                # 进度行要是卡在 running，启动时的清理会把它当成"上次进程没退干净"
                # 删掉（见 RunStore.clear_running）—— 用户就永远看不到那个「继续」。
                #
                # 「步数用尽」归 incomplete 而不是 failed：引擎那句文案已经说明
                # "这不是出错，是防失控的兜底"，归到 failed 会让界面显示成
                # 「执行失败」，与它自己给出的解释自相矛盾。
                if stopped:
                    outcome = "cancelled"
                elif error_code == "agent_max_iterations" or partial:
                    outcome = "incomplete"
                elif error_code:
                    outcome = "failed"
                elif completed:
                    outcome = ""
                else:
                    # 没读完事件流也没出错 → 界面断开了连接
                    outcome = "cancelled"
                if outcome:
                    # ⚠️ 失败率必须进指标（第 88 批，L-14）：以前指标里**只有成功侧**
                    # （调用数 / token / 花费 / 时长），于是"最近是不是老在坏"
                    # 在指标里完全看不出来 —— 而用户感知到的正是"它老答一半就没了"。
                    # `reason` 区分三种去向：`incomplete`（步数用尽）的文案明确说了
                    # "这不是出错"，`cancelled`（用户点停止 / 界面断开）更不是故障，
                    # 混成一个数会让失败率虚高、把真正的问题淹掉。
                    METRICS.inc("turn_failed_total", model=model_id, reason=outcome)
                    await runtime.runs.interrupt(
                        run_id,
                        status=outcome,
                        step=step,
                        last_action=last_action,
                        error=(
                            "你点了停止（或界面断开了连接）"
                            if outcome == "cancelled"
                            else error_message
                        ),
                    )
                else:
                    await runtime.runs.finish(run_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/v1/confirm")
async def confirm(payload: ConfirmDecision, request: Request) -> dict[str, Any]:
    """回传用户的权限确认结果，唤醒挂起的 Agent 循环。"""
    runtime: AppRuntime = get_runtime(request)
    resolved = runtime.resolve_confirm(payload.request_id, payload.approved)
    if not resolved:
        return {"ok": False, "message": "确认请求不存在或已超时"}
    return {"ok": True, "approved": payload.approved}


@router.post("/v1/plan/decision")
async def plan_decision(payload: PlanDecision, request: Request) -> dict[str, Any]:
    """回传用户对执行计划的决定，唤醒挂起的 Agent 循环（单聊计划模式）。

    与 ``/v1/confirm`` 分开的两个接口：那个管权限（超时=拒绝），
    这个管计划（不超时），共用会互相污染语义。
    """
    runtime: AppRuntime = get_runtime(request)
    feedback = payload.feedback.strip()
    resolved = runtime.resolve_plan(payload.plan_id, payload.approved, feedback)
    if not resolved:
        # 常见原因：用户重复点了同一个按钮，或计划已经超期作废。
        # 返回明确原因而不是假装成功 —— 前端据此提示而不是干等。
        return {"ok": False, "message": "这个计划已经不在等待中了（可能已开始执行或被取消）"}
    if payload.approved:
        action = "approved"
    elif feedback:
        action = "revise"
    else:
        action = "aborted"
    return {"ok": True, "action": action}


class InteractionDecision(BaseModel):
    """``POST /v1/interaction/decision`` 的请求体。

    ⚠️ ``answer`` 是**任意结构**（选择题回选项 id，敏感输入回名字列表），
    所以类型是宽松的 ``dict``。但**绝不许把敏感值放进来** ——
    这条链路会进日志与审计（见 ``security/interaction.py`` 的模块注释）：
    敏感值由渲染层直接写本地加密文件，这里只回传名字。
    """

    request_id: str
    answer: dict[str, Any] = Field(default_factory=dict)


@router.post("/v1/interaction/decision")
async def interaction_decision(payload: InteractionDecision, request: Request) -> dict[str, Any]:
    """回传用户对交互弹窗的作答，唤醒挂起的技能调用。

    与 ``/v1/confirm``（权限，超时=拒绝）和 ``/v1/plan/decision``（计划，三元组）
    分开的第三个接口：这个承载的是"任意结构的用户输入"，不超时。
    三者共用会互相污染语义，所以宁可多一个接口。
    """
    runtime: AppRuntime = get_runtime(request)
    resolved = runtime.resolve_interaction(payload.request_id, payload.answer)
    if not resolved:
        # 常见原因：用户重复点了同一个选项、或这条任务已经被停止 / 会话被关掉了。
        # 返回明确原因而不是假装成功 —— 前端据此提示，而不是让用户干等。
        return {"ok": False, "message": "这次交互已经不在等待中了（可能已作答或被取消）"}
    return {"ok": True}


@router.post("/v1/stop")
async def stop(payload: StopRequest, request: Request) -> dict[str, Any]:
    """中断当前生成。"""
    runtime: AppRuntime = get_runtime(request)
    cancelled = 0
    if payload.task_id:
        # 反查所属会话，好把**该会话**挂起的确认一起收掉。
        #
        # ⚠️ 查不到所属会话时**绝不能**退回"收全部"：`reject_pending(None)` 的语义是
        # 整体关闭（唯一的另一个调用点是 `AppRuntime.shutdown`），而这条分支的常态
        # 恰恰是"任务已经正常跑完、被 unregister 掉了"（见上面 finally 里的
        # `unregister_task`）—— 用户重复点一下「停止」，或前端重放一个旧 task_id，
        # 就会把**其它会话**正在等待的确认 / 计划卡 / 密钥输入框一起作废，
        # 而且没有任何日志能解释"我那个确认框怎么自己没了"。
        owner = runtime.tasks.get(payload.task_id)
        cancelled = 1 if runtime.cancel_task(payload.task_id) else 0
        owner_session = owner.session_id if owner is not None else ""
        if owner_session:
            runtime.reject_pending(owner_session)
    elif payload.session_id:
        cancelled = runtime.cancel_session_tasks(payload.session_id)
        runtime.reject_pending(payload.session_id)
    return {"ok": True, "cancelled": cancelled}
