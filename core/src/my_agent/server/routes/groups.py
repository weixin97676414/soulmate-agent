"""AI 群（多搭子群聊）接口。

对应需求 #15 / #6：把多个搭子拉进一个群，用户抛出一个话题后，搭子们
**自主讨论** —— 按可设置的发言顺序逐轮流式发言，后发言者能看到前文，
可以互相 @，可以发起结束投票，投票通过后由发起者做**总结**交付给用户。

## 与旧版「轮流接话」的区别

``/chat``（旧，保留兼容）是"用户说一句、每人回一句"的一轮广播；
``/discuss``（新）是多轮讨论，搭子自主推进话题并收敛出结论。

## 控制标记

模型用发言末尾的标记表达控制意图（解析不到就按普通发言处理，不强制）：
- ``[END_VOTE]`` 发起结束投票
- ``[AGREE]`` / ``[DISAGREE]`` 对被发起的投票表态

## 边界（第一版取舍）

- 讨论**不设硬轮数上限**（用户明确选择），但有极高的安全阀 ``MAX_ROUNDS``
  防止死循环烧 token；触发时如实告知。
- 群历史**逐条落库**（`storage/group_events.py`）：切走页面、重启应用后仍在，
  用户可以清空对话或删掉整个群。内存里同时保留一份，讨论过程中不必频繁读写库。
- 群聊里每个搭子用**自己的 Agent**（带技能/MCP），需要人工确认的工具**会弹窗**
  （见下面"确认通道"）。
- 群里可以单独设置**思考强度**，且优先于成员各自的设置（群 > 成员 > 不发送）。

## 确认通道为什么走全局事件流，而不是本群的 SSE 流

群里某个搭子要执行 confirm 级技能时，得有人来点「允许/拒绝」。实现上有两条路：

1. 把确认请求塞进本群的讨论流（像单聊 `/v1/chat` 那样）；但讨论流是"边跑边
   `yield`"的生成器，而确认回调是在 `await` 深处被调用的 —— **没法从回调里 yield**，
   要让确认事件上流就必须把整场讨论改成"生产者任务 + 队列 + 消费生成器"。
2. 用一个**常驻**的通道下发（这里选的就是它）：`runtime.events` 那条 `/v1/events`
   长连接在应用启动时就建立了，而确认弹窗在**所有页面**都会渲染。

选 2 还有一个更重要的理由：一场讨论可能持续几分钟，用户中途会切到别的页面，
而"确认"这件事必须在他切走之后依然能弹出来。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ...agent.group_discussion import (
    discussion_source as _discussion_source,
)

# ⚠️ 群聊的**领域逻辑**已下沉到 `agent/group_domain.py`（审计 H-06 / M-22）：
# 发言顺序 / 上下文写入与渲染 / 历史恢复 / 对话 id 解析。
# 这里**保留同名私有别名**（`_say` 等），所以本文件里那十几处调用点一行都没动 ——
# 搬运与改名分开做，回归面最小。新代码请直接用 group_domain 的公开名。
from ...agent.group_domain import (
    ordered_members as _ordered_members,
)
from ...agent.group_domain import (
    persisting_stream as _persisting_stream,
)
from ...agent.group_domain import (
    render_history as _render_history,
)
from ...agent.group_domain import (
    resolve_thread as _resolve_thread,
)
from ...agent.group_domain import (
    restore_history as _restore_history,
)
from ...agent.group_domain import (
    say as _say,
)
from ...agent.orchestrator import AVATAR_MAX_BYTES
from ...config.schemas import ConfirmMode, GroupProfile
from ...llm.base import Message
from ...skill.custom import persona_with_instructions
from ...skill.package import slugify
from ...storage import images
from ..deps import get_runtime
from ..runtime import AppRuntime
from ..sse import format_sse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["groups"], prefix="/v1/groups")

# 安全阀：极高，正常讨论远达不到。用户选择"不设硬上限"，但完全不设会死循环烧 token。


def _slugify(text: str) -> str:
    """群 id 的 slug 前缀。

    ⚠️ 实现已收敛到 `skill/package.py::slugify`（末批 H-06 顺手）：原先 `routes/groups.py`
    与 `skill/package.py` 各有一份**逐字相同**的实现，只差"整串被过滤光时用什么兜底"
    （`"group"` vs `"skill"`）。共用一份、把兜底当参数传，就不存在"改了一边忘了另一边"。
    """
    return slugify(text, fallback="group")


# 帧格式统一在 `server/sse.py`（这里有过的实现漏了 `default=str`，与单聊那份不一致）。
_sse = format_sse


async def _reply_once(
    runtime: AppRuntime, group: GroupProfile, assistant: Any, history: list[dict[str, str]]
) -> str:
    model_id = assistant.model_id or runtime.config.models.default_model
    llm = runtime.registry.get(model_id or None)
    persona = persona_with_instructions(
        runtime, assistant.id, list(assistant.enabled_skills) or None
    )
    context = _render_history(history, group.name, assistant.name)
    # 兜底提示词已退役：这里直接用该搭子的人格文档（见 engine._system_prompt）。
    # 人格为空时**不发** system 消息 —— 宁可不带，也不发一条空的。
    messages = [Message(role="user", content=context)]
    if persona:
        messages.insert(0, Message(role="system", content=persona))
    response = await llm.chat(
        messages,
        temperature=assistant.temperature if assistant.temperature is not None else 0.7,
    )
    return (response.content or "").strip()


# --------------------------------------------------------------------------- #
# 请求模型
# --------------------------------------------------------------------------- #
async def _normalize_group_avatar(runtime: AppRuntime, raw: str | None) -> str:
    """把传来的群头像归一成能存进配置的 data URL。

    ⚠️ 必须走 `storage.images` 那套统一入口（校验格式 / 限大小 / base64），
    而不是把字符串直接塞进配置：它守着的是"配置里不会存进一个不是图片的东西"，
    界面和 AI 两条路都得过它。与 `Orchestrator.update_assistant_profile` 里
    处理搭子头像是同一份逻辑、同一个上限。

    空串 = **清掉**（不是"不动"）：前端看到空串会按"优先不与现有群重复"的规则
    补一张，所以清掉的实际效果是"重新分配一张"，而不是"没有头像"。
    """
    text = (raw or "").strip()
    if not text:
        return ""
    # 前端 `readImageAsDataUrl` 的产物已经是 data URL，不必再解一遍 base64；
    # 但仍要卡一次大小 —— 它是**要写进 groups.json** 的，每次启动都会被读。
    if text.startswith("data:"):
        if len(text) > AVATAR_MAX_BYTES * 2:
            # base64 会把原始字节放大 4/3，所以阈值放宽一倍再判
            raise HTTPException(
                status_code=400,
                detail=(
                    f"这张头像太大了（约 {len(text) // 1024}KB），请换一张小一点的图。"
                    "群头像每次启动都会被读进配置，所以刻意卡得比聊天附图紧。"
                ),
            )
        return text
    try:
        _, data_url = await images.to_data_url(
            text, max_bytes=AVATAR_MAX_BYTES, workspace=runtime.workspace
        )
    except images.ImageSourceError as exc:
        # 原样转出去：这条文案是写给用户看的（"换张小图或先压缩"），别吞成 500
        raise HTTPException(status_code=400, detail=f"设置群头像失败：{exc}") from exc
    return data_url


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=48)
    member_assistant_ids: list[str] = Field(default_factory=list)
    speaking_order: list[str] = Field(default_factory=list)
    #: 建群时顺带指定头像（data URL）。留空 = 由前端按规则随机补一张。
    avatar: str = ""


class GroupChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class GroupDiscussRequest(BaseModel):
    topic: str = Field("", description="讨论话题；留空表示继续上一个话题")
    # 附件与单聊同一套语义（见 routes/chat.py）：``attachments`` 只把文件信息
    # 写进文字，``images`` 才把图片本体发给模型
    attachments: list[str] = Field(default_factory=list, description="工作区文件 id（附件）")
    images: list[str] = Field(default_factory=list, description="工作区文件 id（图片）")
    #: 话题抛给哪条对话。留空 = 该群**最近有动静**的那条，一条都没有就现建一条。
    #:
    #: ⚠️ 刻意做成可选：老客户端不会传这个字段，而"发消息时没有对话"是完全正常的
    #: 首次使用路径。让后端兜底比让前端每次都必须先建好对话更稳 ——
    #: 否则漏传一次就是"消息发出去了但不在任何对话里"。
    thread_id: str = Field("", description="目标对话 id；留空则用最近一条（无则新建）")


class GroupThreadCreate(BaseModel):
    title: str = Field("", max_length=48, description="对话标题；留空用默认名")


class GroupThreadRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=48)


class GroupUpdate(BaseModel):
    """群设置的**局部**更新。

    ``None`` 与"没传这个字段"是两回事，这里靠 ``model_fields_set`` 区分
    （与 ``routes/chat.py`` 里 ``reasoning_effort`` 用的是同一套做法）：
    "没传" = 不动，"显式传 null / 空串" = 清回"跟随成员各自的设置"。
    用 ``is not None`` 判断的话，界面上就永远没办法把某个选项改回默认值。
    """

    name: str | None = Field(None, min_length=1, max_length=48)
    # 建好之后增删成员（产品要求：群聊要能随时调整成员）。
    # ``None`` = 不动；传了就按新名单整体替换（顺序即发言顺序的基准）。
    member_assistant_ids: list[str] | None = None
    speaking_order: list[str] | None = None
    #: 群头像（data URL）。**空串 = 清掉，让前端重新补一张**（不是"不动"）——
    #: 与 `name` 那几个字段的语义保持一致：显式传空串就是"清回默认"。
    #: 不传（`None`）= 不动。
    avatar: str | None = None
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    confirm_mode: ConfirmMode | None = None
    #: 语音唤醒词。
    #:
    #: ⚠️ 与上面几个字段的语义**不一样**：这里是"说了它切到这个群"，
    #: 所以「空列表」不是"清回默认"，而是**用户明确不要唤醒词**（这个群不参与
    #: 语音唤醒）。`None`（不传）才是"不动"。
    #:
    #: 之所以不做成"空 = 清回默认"：用户把词删光的意思几乎不可能是"帮我按群名
    #: 再生成一个吧" —— 那种情况下他想要的是**别再用声音切进这个群**。
    wake_words: list[str] | None = None

    @field_validator("reasoning_effort", "confirm_mode", mode="before")
    @classmethod
    def _blank_means_default(cls, value: Any) -> Any:
        """空串一律当成"清回默认"。

        前端下拉框的"跟随…"选项值就是空串 —— 如果不在这里归一化，
        它会先被 Literal 校验拒掉（422），用户看到的是一个莫名其妙的报错。
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
@router.get("")
async def list_groups(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    return {"groups": [item.model_dump(mode="json") for item in runtime.groups.groups]}


@router.post("")
async def create_group(payload: GroupCreate, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    for assistant_id in payload.member_assistant_ids:
        if runtime.assistants.get(assistant_id) is None:
            raise HTTPException(status_code=400, detail=f"搭子「{assistant_id}」不存在")

    group = GroupProfile(
        id=f"{_slugify(payload.name)}-{uuid.uuid4().hex[:6]}",
        name=payload.name,
        member_assistant_ids=payload.member_assistant_ids,
        speaking_order=payload.speaking_order,
        # 留空就留给前端补（群头像库在前端，见 GroupProfile.avatar 的说明）
        avatar=await _normalize_group_avatar(runtime, payload.avatar),
    )
    config = runtime.groups.model_copy(deep=True)
    config.upsert(group)
    runtime.groups = runtime.config_store.save_groups(config)
    await runtime.audit.op(
        kind="group",
        action="create",
        target=group.id,
        detail=f"新建群「{group.name}」（成员：{'、'.join(group.member_assistant_ids)}）",
    )
    return group.model_dump(mode="json")


@router.patch("/{group_id}")
async def update_group(group_id: str, payload: GroupUpdate, request: Request) -> dict[str, Any]:
    """局部更新群设置（名字、发言顺序、思考强度、权限策略）。

    为什么需要它：群级设置是**讨论中随时可能调**的东西（"这场讨论要它多想一点"
    "这个群里别再逐个问我了"），而整条替换的 PUT 要求客户端先把自己那份完整配置
    提交回来 —— 界面上一旦有两条路径同时改（比如思考强度和权限策略），
    后提交的那份会把前一份的改动顺手覆盖掉。
    """
    runtime: AppRuntime = get_runtime(request)
    existing = runtime.groups.get(group_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")

    # 只收"显式传过"的字段（见 GroupUpdate 的说明）
    changes: dict[str, Any] = {}
    if "name" in payload.model_fields_set:
        changes["name"] = payload.name or existing.name
    if "member_assistant_ids" in payload.model_fields_set and payload.member_assistant_ids is not None:
        # 建好之后也要能增删成员（产品要求）。校验只保留"成员必须真的存在"。
        #
        # ⚠️ 原先这里还有一条 `len(members) < 2` —— 按产品要求**去掉**：
        # "用户手动拉的群，不需要有必须指定的搭子，可以随意安排搭子"。
        # 那条限制的出发点是"一个搭子讨论不起来"，但它把"先建个空群，
        # 想好了再拉人"这件事直接堵死了，而那是完全正当的用法。
        # 真正讨论不起来时由聊天入口拦住（那里有专门的提示，见 group_chat）。
        members: list[str] = []
        for assistant_id in payload.member_assistant_ids:
            if runtime.assistants.get(assistant_id) is None:
                raise HTTPException(status_code=400, detail=f"搭子「{assistant_id}」不存在")
            if assistant_id not in members:
                members.append(assistant_id)
        changes["member_assistant_ids"] = members
        # 发言顺序要跟着成员走：被移出群的不能还留在顺序里（否则排序界面会显示幽灵成员）
        order = [item for item in existing.speaking_order if item in members]
        changes["speaking_order"] = order + [item for item in members if item not in order]
        # 群角色确认也跟成员走（加的「审核员 / 优化顾问」确认）：把已确认的
        # 审核员或顾问移出群时，那个角色就作废了 —— 不清掉的话，AI 那边的闸门会以为角色
        # 还齐着，而实际上这个人根本不在群里、讨论时也不会发言。
        for role in ("reviewer", "advisor"):
            field = f"{role}_id"
            confirmed = (getattr(existing, field) or "").strip()
            if confirmed and confirmed not in members:
                changes[field] = ""
    if "speaking_order" in payload.model_fields_set:
        # 顺序里只保留当前成员：换成员时上面已经重排过一次，这里处理"只改顺序"的调用
        current_members = changes.get("member_assistant_ids") or list(
            existing.member_assistant_ids
        )
        changes["speaking_order"] = [
            item for item in (payload.speaking_order or []) if item in current_members
        ]
    if "reasoning_effort" in payload.model_fields_set:
        changes["reasoning_effort"] = payload.reasoning_effort
    if "confirm_mode" in payload.model_fields_set:
        changes["confirm_mode"] = payload.confirm_mode
    if "avatar" in payload.model_fields_set:
        # 先原样放着，下面再过一遍图片校验（它是 async 的，混在这一串同步的
        # 字段搬运里会读错）
        changes["avatar"] = payload.avatar
    if "wake_words" in payload.model_fields_set and payload.wake_words is not None:
        # 去掉空白项并按原顺序去重。
        #
        # ⚠️ 两个坑：
        # · **空列表是合法输入**（用户清空 = 这个群不参与语音唤醒），所以这里
        #   只过滤空白项、不补默认值。想"重新按群名生成"的用户会去改掉那个词，
        #   而不是删光。
        # · 不能交给 `GroupProfile._seed_wake_words` 去补 —— 它判的是"等于出厂
        #   哨兵值才补"，而这里传进来的空列表恰恰是**明确意图**，补了就变成
        #   "删不掉"。
        cleaned: list[str] = []
        for word in payload.wake_words:
            text = word.strip()
            if text and text not in cleaned:
                cleaned.append(text)
        changes["wake_words"] = cleaned

    if not changes:
        return existing.model_dump(mode="json")

    if "avatar" in changes:
        # 放这里（而不是上面那个 if 里）是因为它是 async 的，
        # 而上面那一串是纯字段搬运 —— 混在一起读起来会以为它也是同步的
        changes["avatar"] = await _normalize_group_avatar(runtime, changes["avatar"])

    group = existing.model_copy(update=changes)
    config = runtime.groups.model_copy(deep=True)
    config.upsert(group)
    runtime.groups = runtime.config_store.save_groups(config)
    logger.info("群设置已更新 group=%s 变更=%s", group_id, sorted(changes))
    await runtime.audit.op(
        kind="group",
        action="update",
        target=group_id,
        detail=f"修改群设置「{group.name}」：{('、'.join(sorted(changes))) or '无字段变化'}",
    )
    return group.model_dump(mode="json")


@router.delete("/{group_id}")
async def delete_group(group_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    config = runtime.groups.model_copy(deep=True)
    if not config.remove(group_id):
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    runtime.groups = runtime.config_store.save_groups(config)
    # 内存上下文的主键是 (群, 对话)：**必须按前缀清**，`pop(group_id)` 清不掉任何东西
    # （键现在是个元组），留着的那堆上下文会让"删掉群再建一个同名的"记得旧发言
    runtime._group_history = {
        key: value for key, value in runtime._group_history.items() if key[0] != group_id
    }
    # 连带清掉聊天记录：群都没了，留着只是一堆永远读不到的孤儿数据
    if runtime.db_ready:
        try:
            await runtime.group_event_repo.delete_group(group_id)
            await runtime.group_thread_repo.delete_group(group_id)
        except Exception as exc:  # noqa: BLE001 - 删群已经成功，清理失败不该让接口失败
            logger.warning("清理群聊记录失败 group=%s: %s", group_id, exc)
    await runtime.audit.op(
        kind="group", action="delete", target=group_id, detail="删除群（连带清掉该群的聊天记录）"
    )
    return {"ok": True}


# --------------------------------------------------------------------------- #
# 讨论：自主多轮 + 结束投票 + 总结（流式）
# --------------------------------------------------------------------------- #


@router.post("/{group_id}/stop")
async def stop_group_discussion(group_id: str, request: Request) -> dict[str, Any]:
    """停止某个群正在跑的后台讨论（观察窗的「暂停任务」按钮）。

    只作用于**后台**讨论（``runtime.orchestrator`` 在跑的那些）；前台 `/discuss`
    的流式讨论由前端断开连接即停止，不经过这里。群不存在或没在跑都返回
    ``stopped=False``，不算错误。
    """
    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    return await runtime.orchestrator.stop_discussion(group_id)


@router.post("/{group_id}/discuss")
async def discuss(group_id: str, payload: GroupDiscussRequest, request: Request) -> Any:
    """群聊自主讨论（SSE 流式）：用户抛话题，搭子们多轮讨论到投票收敛。"""
    runtime: AppRuntime = get_runtime(request)
    group = runtime.groups.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    members = _ordered_members(runtime, group)
    if not members:
        raise HTTPException(status_code=400, detail="这个群还没有成员，先拉几个搭子进来。")

    # 话题抛给哪条对话：客户端没指定就用最近一条，一条都没有就现建一条
    thread_id = await _resolve_thread(runtime, group_id, payload.thread_id)
    # 先把**这条对话**的历史从库里恢复（重启后仍能"接着说"），再开讨论
    await _restore_history(runtime, group_id, thread_id)
    # 有新动静了：让这条对话在列表里往前排（排序靠 updated_at，见 GroupThreadRepository）
    if runtime.db_ready:
        try:
            await runtime.group_thread_repo.touch(group_id, thread_id)
        except Exception as exc:  # noqa: BLE001 - 只影响排序，不该让话题发不出去
            logger.warning("群对话时间戳更新失败 group=%s thread=%s: %s", group_id, thread_id, exc)

    # 附件与图片：直接复用单聊那两个构造函数（含图片数量/体积上限与 MIME 白名单），
    # 群里再写一套的话，两边迟早会出现"单聊能发的图群里发不了"
    from .chat import build_attachment_block, build_image_parts

    attachment_block = await build_attachment_block(runtime, payload.attachments or [])
    images = await build_image_parts(runtime, payload.images or [])

    return StreamingResponse(
        _persisting_stream(
            runtime,
            group_id,
            thread_id,
            _discussion_source(
                runtime,
                group,
                members,
                payload.topic,
                thread_id,
                attachment_block=attachment_block or "",
                images=images,
            ),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/{group_id}/messages")
async def list_group_messages(
    group_id: str, request: Request, thread_id: str = ""
) -> dict[str, Any]:
    """取**某条对话**的讨论记录（按事件回放）。

    返回的是**事件流**而不是"消息列表"：前端本来就在消费同一套事件来渲染，
    重放一遍即可，不需要再写一条并行的构造路径（两条路径迟早会长歪）。

    ``thread_id`` 留空表示"最近有动静的那条"（见 `_resolve_thread`）。
    返回值里带回**实际用的** `thread_id`，这样前端不必猜自己读的是哪条。
    """
    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not runtime.db_ready:
        # 内存模式下没有持久化，如实说明而不是假装"没有记录"
        return {"events": [], "persistent": False, "thread_id": thread_id}
    resolved = await _resolve_thread(runtime, group_id, thread_id)
    events = await runtime.group_event_repo.list_events(group_id, resolved)
    return {"events": events, "persistent": True, "thread_id": resolved}


@router.delete("/{group_id}/messages")
async def clear_group_messages(
    group_id: str, request: Request, thread_id: str = ""
) -> dict[str, Any]:
    """清空**某条对话**的记录（保留群本身、成员与其它对话）。

    ⚠️ 这以前是"清空整个群"。群有了多条对话之后，那个语义会让用户
    "清掉一条对话，结果所有对话都没了" —— 所以必须按对话来。
    """
    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    resolved = await _resolve_thread(runtime, group_id, thread_id)
    removed = 0
    if runtime.db_ready:
        removed = await runtime.group_event_repo.clear(group_id, resolved)
    # 内存里的上下文也要一起清，否则"清空之后下一个话题"仍然带着旧的前文
    runtime._group_history.pop((group_id, resolved), None)
    return {"ok": True, "removed": removed, "thread_id": resolved}


# --------------------------------------------------------------------------- #
# 对话列表（一个群可以有多条）
# --------------------------------------------------------------------------- #
@router.get("/{group_id}/threads")
async def list_group_threads(group_id: str, request: Request) -> dict[str, Any]:
    """列出该群的对话，最近有动静的排前面。

    **一条都没有时会顺手建一条**：用户打开一个从没聊过的群，界面上应该已经有一条
    "新对话"等着他，而不是空白列表 + 一个得自己去找的加号。空态与"有一条空对话"
    在体验上是两回事，后者才是他已经熟悉的样子（单聊就是这样）。
    """
    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not runtime.db_ready:
        return {"threads": [], "persistent": False}
    threads = await runtime.group_thread_repo.list_threads(group_id)
    if not threads:
        threads = [await runtime.group_thread_repo.create(group_id)]
    return {"threads": threads, "persistent": True}


@router.post("/{group_id}/threads")
async def create_group_thread(
    group_id: str, payload: GroupThreadCreate, request: Request
) -> dict[str, Any]:
    """新建一条空对话（输入栏左下角那个「开启新对话」按钮）。"""
    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not runtime.db_ready:
        raise HTTPException(status_code=503, detail="当前是内存模式，无法新建对话")
    return await runtime.group_thread_repo.create(group_id, payload.title or None)


@router.patch("/{group_id}/threads/{thread_id}")
async def rename_group_thread(
    group_id: str, thread_id: str, payload: GroupThreadRename, request: Request
) -> dict[str, Any]:
    """给对话改名。"""
    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not runtime.db_ready:
        raise HTTPException(status_code=503, detail="当前是内存模式，无法改名")
    if not await runtime.group_thread_repo.rename(group_id, thread_id, payload.title):
        raise HTTPException(status_code=404, detail=f"对话「{thread_id}」不存在")
    thread = await runtime.group_thread_repo.get(group_id, thread_id)
    if thread is None:  # 极端并发：刚改完就被删了
        raise HTTPException(status_code=404, detail=f"对话「{thread_id}」不存在")
    return thread


@router.delete("/{group_id}/threads/{thread_id}")
async def delete_group_thread(
    group_id: str, thread_id: str, request: Request
) -> dict[str, Any]:
    """删一条对话（连带它的事件）。

    内存上下文也一并丢掉 —— 留着的话，用户"删掉再建一条新的"之后，
    模型仍然记得那条已经删掉的对话里说过的话。那是很难解释的串味。
    """
    runtime: AppRuntime = get_runtime(request)
    if runtime.groups.get(group_id) is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not runtime.db_ready:
        raise HTTPException(status_code=503, detail="当前是内存模式，无法删除对话")
    if not await runtime.group_thread_repo.delete(group_id, thread_id):
        raise HTTPException(status_code=404, detail=f"对话「{thread_id}」不存在")
    runtime._group_history.pop((group_id, thread_id), None)
    await runtime.audit.op(
        kind="group", action="delete", target=group_id, detail=f"删除群对话「{thread_id}」"
    )
    return {"ok": True}


# --------------------------------------------------------------------------- #
# 旧接口：一轮轮流接话（保留兼容）
# --------------------------------------------------------------------------- #
@router.post("/{group_id}/chat")
async def group_chat(group_id: str, payload: GroupChatRequest, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    group = runtime.groups.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"群「{group_id}」不存在")
    if not group.member_assistant_ids:
        raise HTTPException(status_code=400, detail="这个群还没有成员，先拉几个搭子进来。")

    # 旧接口（一轮轮流接话）：它没有对话的概念，挂到该群"最近一条"上即可 ——
    # 这条路径只为兼容老客户端存在，不值得再给它开一个对话维度的参数。
    thread_id = await _resolve_thread(runtime, group_id, "")
    await _restore_history(runtime, group_id, thread_id)
    history = runtime._group_history.setdefault((group_id, thread_id), [])
    _say(history, role="user", name="用户", content=payload.message)

    replies: list[dict[str, str]] = []
    for member_id in group.member_assistant_ids:
        assistant = runtime.assistants.get(member_id)
        if assistant is None:
            continue
        try:
            reply = await _reply_once(runtime, group, assistant, history)
        except Exception as exc:  # noqa: BLE001 - 某个搭子的模型挂了不该拖垮整个群
            replies.append(
                {"assistant_id": member_id, "name": assistant.name, "content": "", "error": str(exc)}
            )
            continue
        if not reply:
            continue
        _say(history, role="assistant", name=assistant.name, content=reply)
        replies.append({"assistant_id": member_id, "name": assistant.name, "content": reply})

    return {"replies": replies}
