"""助手（Agent 预设）接口。

对应《Windows客户端开发计划》4.4 节。助手把「人设 + 模型 + 可用工具 + 权限策略」
打包成一个可切换的整体，让用户不必每次对话都重新调参数。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ...assistants import evolution, lifecycle, locked_builtins
from ...assistants.persona import RULES_FILE, SOUL_FILE, list_files, read_file, write_file
from ...assistants.presets import (
    DEFAULT_ASSISTANT_ID,
    RENAMED_BUILTIN_IDS,
)
from ...assistants.transfer import (
    TransferError,
    apply_buddy,
    apply_buddy_group,
    parse_buddy_package,
    parse_group_package,
)
from ...config.schemas import AssistantProfile
from ...skill.builtin import xjx
from ...skill.custom import known_skill_names
from ..deps import get_runtime
from ..runtime import AppRuntime

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assistants"], prefix="/v1/assistants")

# 这里曾有 /export、/import、/market、/market/install 四条路由（导出搭子、
# 从文件导入、搭子集市、从集市安装）以及它们共用的 _install_profiles。
# 产品要求把这四项功能整体剔除，后端一并连根删掉 —— 不留没人调的死代码，
# 也不留下"接口还在、界面上却找不到入口"的困惑。
#
# 顺带说明当时的顺序约束（现在没有 /export、/market 这类字面量路由了，但规则
# 仍然成立）：字面量路由必须声明在 ``/{assistant_id}`` **之前**，因为 FastAPI
# 按声明顺序匹配，晚声明会被参数路由吃掉。见下面各路由的排列。


def _validate_model(runtime: AppRuntime, profile: AssistantProfile) -> None:
    """校验助手指定的模型确实存在。

    不校验的话，用户会在第一次对话时收到一个"模型不存在"的报错，
    很难联想到是助手配置的问题。
    """
    if profile.model_id and not runtime.registry.has(profile.model_id):
        available = ", ".join(runtime.registry.ids()) or "(无)"
        raise HTTPException(
            status_code=422,
            detail=f"模型 {profile.model_id} 不存在。当前可用模型：{available}",
        )


def _validate_skills(runtime: AppRuntime, profile: AssistantProfile) -> None:
    """校验技能白名单的名字，并**就地剔掉档案里的历史残留**。

    校验部分：允许出现尚未连接时就写好的 MCP 工具名（它们会随着 Server 上线而
    可用），所以只在**完全找不到**时才拦 —— 但内置技能写错名字一定要拦。

    ⚠️ "顺手改 `profile`" 不是随意的副作用，而是刻意选在这里：`create` / `update`
    两条路都是**先校验、后** `model_copy` 出落盘对象，所以在这里剔除等价于
    "这份档案落盘前就干净了"，一处覆盖两条路。
    """
    from ...skill import groups

    if not profile.enabled_skills:
        return

    # ---- ① 历史残留：**静默剔除**，不报错 ----
    #
    # 「产品经理方法论」「商业诊断工具箱」在四分类第一版里是**通用技能**，用户当时
    # 合法勾过。它们转成了 BuddyManager 专属 —— 老档案于是带着两个
    # "现在不合法"的名字。这里必须静默剔掉而不是拒绝：用户什么都没改、只是打开搭子
    # 点了一下保存，却被告知"专属技能不能写进可用能力"，他既不知道自己错在哪，
    # 也无从下手。
    #
    # ⚠️ 与下面 ③ 那条"拒绝"的分界在**来路**：这里处理"用户不知情的历史残留"，
    # 那里拦"现在硬塞别人的专属技能"（越权企图，必须报错并说清）。
    retired = [name for name in profile.enabled_skills if name in groups.RETIRED_COMMON_NAMES]
    if retired:
        logger.info(
            "剔除搭子「%s」可用能力里已失效的历史技能：%s",
            profile.id,
            "、".join(retired),
        )
        profile.enabled_skills = [
            name for name in profile.enabled_skills if name not in groups.RETIRED_COMMON_NAMES
        ]

    # ---- ② 心鉴学专属技能：拒绝 ----
    # 它们是"线路 + 归属"的纯函数，写进白名单不但不生效，还会把该搭子的工具清单
    # 收窄成"什么都没有"（见 xjx 的说明）。这道闸必须排在"找不找得到"之前。
    try:
        xjx.reject_reserved_skill_names(profile.enabled_skills)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ---- ③ 别人的专属技能：拒绝 ----
    # 它们按搭子归属**自动生效**，写进去既不生效（装配时会被归属过滤排除），
    # 又会让人以为"勾了就有用"。与上面那条同理，也要排在"找不找得到"之前。
    exclusive = [name for name in profile.enabled_skills if groups.is_exclusive(name)]
    if exclusive:
        raise HTTPException(
            status_code=422,
            detail=(
                f"专属技能不能写进可用能力：{'、'.join(exclusive)} —— "
                "它们按搭子归属自动生效，不需要也不能手动添加。"
            ),
        )


def _validate_voice(runtime: AppRuntime, profile: AssistantProfile) -> None:
    """校验这个搭子的唤醒词：不能为空，也不能跟别的搭子撞。

    ## 为什么"撞车"必须在保存时就拦住

    所有搭子的唤醒词是**一起**送去识别的（一个麦克风、一份识别、匹配全部唤醒词），
    谁先匹配上就切到谁。两个搭子配了同一个词，结果就取决于遍历顺序 —— 用户喊
    「你好搭子」，切过去的有可能是小助。这种"喊 A 结果 B 应答"在界面上没法解释，
    只能在这里挡住。

    ⚠️ 给 409 + **说清跟谁撞了**，而不是一句"保存失败"：用户需要知道该去改哪个。
    """
    words = [word.strip() for word in (profile.voice.wake_words or []) if word.strip()]
    if not words:
        raise HTTPException(status_code=422, detail="唤醒词不能为空，否则这个搭子喊不醒。")

    for other in runtime.assistants.sorted():
        if other.id == profile.id:
            continue
        clash = sorted(set(words) & {w.strip() for w in (other.voice.wake_words or []) if w.strip()})
        if clash:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"唤醒词「{'、'.join(clash)}」和搭子"
                    f"「{other.nickname or other.name}」重复了，换一个 —— "
                    "两个搭子用同一个词的话，喊谁醒谁只能靠运气。"
                ),
            )
    # ⚠️ 判断"存不存在"必须包含**指导型技能**（它们不注册成工具，见
    # skill/custom.py 的 known_skill_names）：只查工具表会把用户已经装好、
    # 界面上也勾着的指导型技能判成不存在，保存时莫名 422。
    known = known_skill_names(runtime)
    unknown = [name for name in profile.enabled_skills if name not in known]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"技能不存在：{', '.join(unknown)}。"
                "如果这是 MCP 工具，请先连接对应的 MCP 服务。"
            ),
        )


def _payload(runtime: AppRuntime, profile: AssistantProfile) -> dict[str, Any]:
    """补上界面需要的派生字段。"""
    data = profile.to_dict()
    # 白名单里的技能若当前不可用（例如 MCP 未连接），界面要能提示出来，
    # 否则用户会以为助手坏了。
    # 口径与上面的保存校验**必须一致**（同一个 known_skill_names）：两处口径
    # 一旦分叉，就会出现"保存得了、但保存完立刻显示成不可用"的荒唐状态。
    known = known_skill_names(runtime)
    # ⚠️ 档案可能是四分类之前写的，里面残留着"当时是通用、现在已变内置/专属"的名字
    # （见 `_validate_skills` ① 与 `groups.RETIRED_COMMON_NAMES`）。它们对装配毫无影响
    # （`allowed_skill_names` 只采信 common / mine 的名字），但会让界面的
    # 「内置技能 + N 个」**虚高** —— 用户看到 5 个额外技能，其中 4 个根本不生效。
    #
    # 为什么在这里滤、而不是启动时批量改写用户档案：改用户数据要慎重，那属于"迁移"。
    # 这里只保证**看到的就是真的**；落盘清理留到用户下次保存（那时 ① 会做掉）。
    from ...skill import groups

    sources = runtime.skills.source_map()
    # ⚠️ **注册表里查不到的名字必须保留**（`name not in sources` 那一条）：
    # 指导型自定义技能（`kind="instruction"`）按设计不注册成工具，未连接的 MCP 工具
    # 也还没进注册表 —— 若拿 `bucket_of(name, "")` 去判，它们会掉进"未登记 = 内置"
    # 的兜底里被误剔，表现是"用户勾的技能下次打开就不见了"。
    # 这与 `allowed_skill_names` 对待注册表外名字的口径**必须一致**（那边也是保留）。
    effective = [
        name
        for name in profile.enabled_skills
        if name not in sources
        or groups.bucket_of(name, sources[name])
        in (groups.BUCKET_COMMON, groups.BUCKET_MINE)
    ]
    if len(effective) != len(profile.enabled_skills):
        data["enabled_skills"] = effective
        # 派生字段要跟着一起改：不改的话界面会显示"内置技能 + 0 个"却仍标成"受限"。
        data["restricts_skills"] = bool(effective)
    # ⚠️ 基于**净化后**的列表算，否则已剔掉的名字还会出现在"当前不可用"的提示里
    data["unavailable_skills"] = [name for name in effective if name not in known]
    # 内置搭子的"哪几项被锁、为什么"：界面靠它把字段置灰并写明原因。
    # 少了这一段，用户点半天没反应，只会以为客户端坏了。
    data.update(locked_builtins.lock_payload(profile.id))
    return data


def _upload_name(file: UploadFile) -> str:
    """取上传文件的名字（不带扩展名）。浏览器可能给完整路径，只要文件名部分。"""
    raw = (file.filename or "package").replace("\\", "/").rsplit("/", 1)[-1]
    return raw.rsplit(".", 1)[0] or "package"


# --------------------------------------------------------------------------- #
# 导入搭子 / 搭子群
#
# ⚠️ 三条路径都在**同一处**解析与落盘（`assistants/transfer.py`）：这里是用户上传
# 包的那条入口，AI 自己从官网拉包走的是技能那条入口 —— 两边共用，才不会出现
# "界面导进来的少了昵称、AI 导进来的少了技能"这类只在一条路上出现的怪事。
#
# 路由顺序：字面量必须排在 `/{assistant_id}` 之前（FastAPI 按声明顺序匹配）。
# --------------------------------------------------------------------------- #
@router.post("/import")
async def import_buddy(
    request: Request,
    package: UploadFile = File(...),  # noqa: B008  FastAPI 标准注入写法
) -> dict[str, Any]:
    """导入一个搭子包（zip，或官网那种单独的 .json）。"""
    runtime: AppRuntime = get_runtime(request)
    payload = await package.read()
    name = _upload_name(package)
    # 解析是同步的 zip/json 活，丢线程里做，别占住事件循环（其它会话的 SSE 全排在后面）
    try:
        parsed = await asyncio.to_thread(parse_buddy_package, payload, name)
    except TransferError as exc:
        # 4xx + 人话：文案直接来自解析层（"这个包里没找到搭子文件"这类），
        # 前端原样展示，不吞
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return await apply_buddy(runtime, parsed)
    except TransferError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        # create_assistant 那类"这个名字不能建"的拒绝
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/import-group")
async def import_buddy_group(
    request: Request,
    package: UploadFile = File(...),  # noqa: B008  同上
) -> dict[str, Any]:
    """导入一个搭子群包（zip：group.json + 多个搭子包）。"""
    runtime: AppRuntime = get_runtime(request)
    payload = await package.read()
    name = _upload_name(package)
    try:
        parsed = await asyncio.to_thread(parse_group_package, payload, name)
    except TransferError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return await apply_buddy_group(runtime, parsed)
    except TransferError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
async def list_assistants(request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    config = runtime.assistants
    return {
        "assistants": [_payload(runtime, item) for item in config.sorted()],
        "default_assistant": config.default_assistant or DEFAULT_ASSISTANT_ID,
        # 旧内置搭子 id → 新 id。
        #
        # 给**历史记录**用：审计日志里存的还是旧 id，而我们刻意不改写历史（那是"当时确实
        # 发生了这件事"的凭证）。界面拿这张表把旧 id 显示成搭子名，否则用户会看到一串
        # 「office」——他不知道那是什么，更不知道那就是 Relation Buddy。
        "legacy_ids": dict(RENAMED_BUILTIN_IDS),
    }


@router.post("")
async def create_assistant(payload: AssistantProfile, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    if runtime.assistants.get(payload.id) is not None:
        raise HTTPException(status_code=409, detail=f"助手 id「{payload.id}」已存在。")

    _validate_model(runtime, payload)
    _validate_skills(runtime, payload)
    _validate_voice(runtime, payload)

    # 用户新建的一律不算内置，避免被「恢复默认助手」的逻辑误伤
    profile = payload.model_copy(update={"builtin": False})

    # 唤醒词由 ``AssistantProfile._seed_wake_words`` 在模型层按名字补齐（见那边的
    # 说明：放模型层才能让老配置也受益）。这里只需要让**最终要落盘的那一份**再走
    # 一遍校验 —— 上面那次校验收的还是 payload。
    _validate_voice(runtime, profile)
    config = runtime.assistants.model_copy(deep=True)
    config.upsert(profile)
    runtime.save_assistants(config)

    # 初始 SOUL：新建搭子自动写入（含名字）。用户之后可随时在人格文件里改。
    # 新助手还没有 SOUL.md，直接写不会覆盖任何已有内容。
    _seed_default_soul(runtime, profile)
    # 初始 RULES：带一段「全员进化」系统规则（产品要求）——
    # 自建搭子没有预置任务，靠这段规则让它自己主动问用户要不要建。
    _seed_default_rules(runtime, profile)
    await runtime.audit.op(
        kind="assistant",
        action="create",
        actor_id=profile.id,
        target=profile.id,
        detail=f"新建搭子「{profile.nickname or profile.name}」",
    )
    return _payload(runtime, profile)


def _seed_default_soul(runtime: AppRuntime, profile: AssistantProfile) -> None:
    """给新建搭子写一份带名字的初始 SOUL.md。"""
    name = profile.nickname.strip() or profile.name.strip()
    content = (
        f"# SOUL\n\n你是 {name}。\n"
        "这里写你的说话方式与性格：语气、在意什么、怎么接话。\n"
    )
    try:
        write_file(runtime.paths, profile.id, SOUL_FILE, content)
    except ValueError as exc:
        # 内容超长等边界情况不该让"创建搭子"本身失败
        logger.warning("写入初始 SOUL 失败 %s: %s", profile.id, exc)


def _seed_default_rules(runtime: AppRuntime, profile: AssistantProfile) -> None:
    """给新建搭子写一份初始 RULES.md：里面带一段「全员进化」的系统规则。

    这段规则的作用是让**自建搭子自己**去问用户要不要建那条每周一次的进化任务
    （内置搭子由系统预置，不需要它问；见 ``assistants/evolution.py``）。

    ⚠️ 只有这个搭子**还没有** RULES.md 时才写。新建路径上它必然是空文件，所以这里
    实际上不会覆盖任何东西 —— 但保留这个判断，是为了将来有人在别处复用它时不会误伤
    用户已经写好的规则（本项目的既有口径是"用户改过就算数"）。
    """
    name = profile.nickname.strip() or profile.name.strip()
    try:
        if read_file(runtime.paths, profile.id, RULES_FILE).strip():
            return
        write_file(runtime.paths, profile.id, RULES_FILE, evolution.evolution_rule(name))
    except ValueError as exc:
        # 与初始 SOUL 同一口径：写不进去不该让"创建搭子"本身失败
        logger.warning("写入初始 RULES 失败 %s: %s", profile.id, exc)


@router.get("/{assistant_id}")
async def get_assistant(assistant_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    profile = runtime.assistants.get(assistant_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")
    return _payload(runtime, profile)


@router.put("/{assistant_id}")
async def update_assistant(
    assistant_id: str, payload: AssistantProfile, request: Request
) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    existing = runtime.assistants.get(assistant_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")
    if payload.id != assistant_id:
        raise HTTPException(status_code=422, detail="路径中的助手 id 与请求体不一致。")

    _validate_model(runtime, payload)
    _validate_skills(runtime, payload)
    _validate_voice(runtime, payload)

    # builtin 标记由服务端管理：用户改内容不该把它洗成自定义，
    # 否则「恢复默认助手」会把这个被改过的助手又加一份进来
    profile = payload.model_copy(update={"builtin": existing.builtin})

    # 四位内置搭子的名称 / 简介 / 可用能力写死（见 ``assistants/locked_builtins``）。
    #
    # 刻意**只比"被锁的那几项"是否有变化**，而不是"是不是内置搭子就一律拒绝"：
    # 设置页保存时会整份回传，其中昵称、头像、温度是用户正当要改的 ——
    # 一律拒绝的话，用户在 Soulmate 上连"换个头像"都做不到，
    # 而错误提示还会说成"名称不能改"。
    try:
        locked_builtins.ensure_mutable(
            assistant_id, changes=locked_builtins.changed_fields(existing, profile)
        )
    except locked_builtins.LockedBuiltinError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    config = runtime.assistants.model_copy(deep=True)
    config.upsert(profile)
    runtime.save_assistants(config)
    await runtime.audit.op(
        kind="assistant",
        action="update",
        actor_id=assistant_id,
        target=assistant_id,
        detail=f"修改搭子「{profile.nickname or profile.name}」的配置",
    )
    return _payload(runtime, profile)


@router.delete("/{assistant_id}")
async def delete_assistant(assistant_id: str, request: Request) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    # 连带处理（群成员 / 群角色 / 人格目录 / 默认位）都在 ``assistants/lifecycle``，
    # **与「搭子总管」技能那条删除路径共用同一份实现**。
    #
    # 这里原先只挪了默认位，群成员与人格目录都没管 —— 那些脏数据不会当场报错，
    # 而是要等到"下次开会讨论"或"下次建一个同 id 的搭子"时才以怪现象出现。
    try:
        report = lifecycle.delete_assistant(runtime, assistant_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在") from None
    except locked_builtins.LockedBuiltinError as exc:
        # 409 而不是 403：这不是"你没有权限"，而是"这个对象本身不允许被删"。
        # 文案直接来自 locked_builtins，界面上原样展示，不做二次包装 ——
        # 用户需要知道"为什么不能删"，而不只是一句"删除失败"。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await runtime.audit.op(
        kind="assistant",
        action="delete",
        actor_id=assistant_id,
        target=assistant_id,
        detail=lifecycle.describe_report(report),
    )
    return {"ok": True, **report}


# --------------------------------------------------------------------------- #
# 人格与记忆文件（SOUL.md / MEMORY.md）
# --------------------------------------------------------------------------- #
class PersonaFileWrite(BaseModel):
    content: str = ""


@router.get("/{assistant_id}/persona-files")
async def list_persona_files(assistant_id: str, request: Request) -> dict[str, Any]:
    """列出该助手的人格与记忆文件（含内容，供界面直接展示与编辑）。"""
    runtime: AppRuntime = get_runtime(request)
    if runtime.assistants.get(assistant_id) is None:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")
    return {"files": list_files(runtime.paths, assistant_id)}


@router.put("/{assistant_id}/persona-files/{name}")
async def write_persona_file(
    assistant_id: str, name: str, payload: PersonaFileWrite, request: Request
) -> dict[str, Any]:
    runtime: AppRuntime = get_runtime(request)
    if runtime.assistants.get(assistant_id) is None:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")
    # 内置搭子的人格文件里只有 RULES.md 写死（SOUL / IDENTITY 一次性对齐后可自由
    # 编辑，MEMORY / USER 本来就可写）。``persona.write_file`` 里也有一道同样的
    # 兜底，这里先判是为了给出 409 + 清楚的原因 —— 混在 "文件名不合法 / 内容超长"
    # 的 400 里，用户会以为是自己的操作有问题。
    try:
        locked_builtins.ensure_persona_writable(assistant_id, name)
    except locked_builtins.LockedBuiltinError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        write_file(runtime.paths, assistant_id, name, payload.content)
    except ValueError as exc:
        # 文件名不在白名单、或内容超长 —— 都是用户输入的问题，给 400 而不是 500
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"files": list_files(runtime.paths, assistant_id)}


# --------------------------------------------------------------------------- #
# 人格锁
# --------------------------------------------------------------------------- #
# 清除锁需要输入的确认语。**故意制造一点摩擦**：一步就能拆掉锁的话，
# 这个功能就只剩"每次多输一次密码"的麻烦，没有防护意义。
UNLOCK_CONFIRM_TEXT = "解除人格锁"


class PersonaLockPayload(BaseModel):
    action: Literal["set", "clear", "verify"]
    # verify：要校验的密码；set：要设的**新**密码
    password: str = ""
    # 已经上锁时，修改密码要先过旧密码
    current: str = ""
    confirm: str = ""


@router.post("/{assistant_id}/persona-lock")
async def persona_lock(
    assistant_id: str, payload: PersonaLockPayload, request: Request
) -> dict[str, Any]:
    """设置 / 校验 / 清除「人格锁」。

    只保护人格部分（系统提示词 + SOUL.md），模型、工具这些普通设置不拦 ——
    这是用户明确要的粒度。

    **清除锁不要求旧密码**（只要求确认语）：那条路存在的意义就是"忘了密码也能救回来"。
    要求旧密码的话，这个锁就从"防手滑"变成了"可能把自己的助手锁死"。
    """
    runtime: AppRuntime = get_runtime(request)
    if runtime.assistants.get(assistant_id) is None:
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")

    config = runtime.assistants.model_copy(deep=True)
    target = config.get(assistant_id)
    if target is None:  # 理论上到不了：上面已确认存在
        raise HTTPException(status_code=404, detail=f"助手「{assistant_id}」不存在")

    if payload.action == "verify":
        return {"ok": target.verify_persona_password(payload.password), "locked": bool(target.persona_password_hash)}

    if payload.action == "clear":
        if payload.confirm.strip() != UNLOCK_CONFIRM_TEXT:
            raise HTTPException(
                status_code=400,
                detail=f"请先在确认框里输入「{UNLOCK_CONFIRM_TEXT}」再清除。",
            )
        target.set_persona_password("")
        runtime.save_assistants(config)
        logger.info("已清除助手的人格锁：%s", assistant_id)
        return {"ok": True, "locked": False}

    # action == "set"
    if target.persona_password_hash and not target.verify_persona_password(payload.current):
        raise HTTPException(status_code=403, detail="当前密码不对，无法修改。")
    if not payload.password:
        raise HTTPException(status_code=400, detail="新密码不能为空。")
    target.set_persona_password(payload.password)
    runtime.save_assistants(config)
    logger.info("已设置助手的人格锁：%s", assistant_id)
    return {"ok": True, "locked": True}
