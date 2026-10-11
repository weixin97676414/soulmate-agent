"""搭子 / 搭子群的导入：**唯一的**解析与落盘实现。

## 为什么单独一个模块

导入有**两条入口**：用户在界面上传一个包，以及 AI 自己从官网把包拉下来导入。
两条入口必须走同一套解析与落盘 —— 各写一份的结果是"界面导进来的搭子少了昵称、
AI 导进来的少了技能"这类只在一条路径上出现的怪事。所以这里放唯一的实现，
两边都调它。

## 两种包结构（产品约定）

**搭子包**（一个 zip）：

```
buddy.json           # 或任意一个"看起来像搭子"的根级 *.json（见下）
skills/              # 该搭子的技能包：可以放 zip，也可以放文件夹
  XJX-Soulmate.zip
  我的技能/           # 文件夹形式：里面要有 skill.json 或 SKILL.md
```

也可以**只给一个 .json**（官网现在就是一个 json + 一个 zip 两个文件）。
这种"裸 json"没有附带技能包，技能名只能去匹配本机已有的技能 —— 匹配不到会如实列出来。

**搭子群包**（一个 zip）：

```
group.json
buddies/
  某个搭子/            # 一个搭子包（文件夹形式）
    buddy.json
    skills/…
  另一个搭子.zip       # 一个搭子包（zip 形式）
```

群包里**不含优化顾问与审核员**：那两个角色由既有的"必须提交搭子 id"闸门另行处理，
导入不替用户拍板（产品约定）。

## 兼容两种搭子 JSON

- **官网格式**：``{"type": "xinjianxue.buddy", "version": 1, "line": "cn", "id": ...,
  "name": ..., "emoji": ..., "description": ..., "intro_md": ...,
  "persona": {"SOUL.md": ..., "IDENTITY.md": ..., "RULES.md": ...}, "skill_pack": ...}``
- **扁平格式**：``{"name": ..., "nickname": ..., "description": ..., "soul": ...,
  "identity": ..., "rules": ..., "temperature": 0.8, "skills": [...]}``
  （键名也接受中文：名称 / 昵称 / 说明 / 温度 / 技能名）

两种都给示例，见交付文档《搭子与搭子群导入格式说明》。

## 幂等：同名或同 id 就更新，不重复建

导入一个已经存在的搭子（例如官网的 Soulmate 就是我们内置的 ``soulmate``）时，
**更新它**而不是造第二个同名的 —— 否则用户导两次就有两个"Soulmate"，
而 `orchestrator.create_assistant` 本身也是拒绝同名的。
更新的范围：昵称 / 图标 / 简介 / 温度 / 人格三件套（**原文覆盖**）+ 技能（**并集**）。
技能取并集而不是覆盖，是为了不把用户后来自己加的技能悄悄抹掉。

## 一处刻意的取舍：导入的规则不再叠加"系统强加条款"

``orchestrator.create_assistant`` 会给策划类搭子在 RULES.md 里强加两条条款
（先调 ai_thinking_mode、策划完调 team_restructure）。那是给 **AI 自建**兜底的 ——
防止它只写一句"你是 XX"就交差。

**导入的搭子以包内的 RULES.md 原文为准，不再叠加**：这个包是别人写好的成品，
它的规则就是它的规则。所以下面写完人格文件后会把 create_assistant 生成的那份
**覆盖掉**，这是有意为之，不是漏了合并。
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from dataclasses import dataclass, field, replace
from typing import Any

from ..skill.builtin import xjx
from ..skill.custom import known_skill_names
from ..skill.package import parse_package
from . import locked_builtins, persona

logger = logging.getLogger(__name__)

# 单个上传包的上限。技能包本身另有上限（见 skill/archive.py 的 MAX_PACKAGE_BYTES），
# 这里管的是"整个压缩包"，所以要给得比单包宽。
MAX_TRANSFER_BYTES = 32 * 1024 * 1024
# 一个包里最多认几个技能包 / 几个搭子包。防"有人传了个几千项的包"把导入拖成几分钟，
# 超了**明确报错**而不是默默只装前几个。
MAX_PACKED_ITEMS = 40

BUDDY_TYPE = "xinjianxue.buddy"
GROUP_TYPE = "xinjianxue.buddy-group"

# 技能包/搭子包里，"长这样"的文件名。
_SKILL_MARKERS = ("skill.json", "skill.md")
_BUDDY_FILE_NAMES = ("buddy.json", "assistant.json", "搭子.json")
_GROUP_FILE_NAMES = ("group.json", "群.json")


class TransferError(ValueError):
    """包不合法、或结构不认识。文案直接给用户看。"""


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class BuddyPayload:
    """一个搭子的全部设定（解析结果，尚未落盘）。"""

    name: str
    nickname: str = ""
    emoji: str = "🤖"
    description: str = ""
    soul: str = ""
    identity: str = ""
    rules: str = ""
    temperature: float | None = None
    skills: list[str] = field(default_factory=list)
    # 包里的原始 id（官网 json 有），用于"同一个搭子导两次"的判重
    source_id: str = ""
    # 官网 json 里指向技能包的文件名（如 XJX-Soulmate-cn.zip）。
    # 官网上 json 与技能包是**两个文件**，靠它才能把技能包自动跟上（见 library.py）。
    skill_pack: str = ""


@dataclass
class BuddyPackage:
    buddy: BuddyPayload
    # (包名, zip 字节) —— 统一成 zip 字节，这样能直接喂给既有的 parse_package
    skill_packs: list[tuple[str, bytes]] = field(default_factory=list)


@dataclass
class GroupPackage:
    name: str
    members: list[BuddyPackage] = field(default_factory=list)
    speaking_order: list[str] = field(default_factory=list)
    confirm_mode: str | None = None
    reasoning_effort: str | None = None


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def _pick(data: dict[str, Any], *keys: str) -> Any:
    """按给定顺序取第一个存在的键（键名同时接受英文与中文写法）。"""
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def parse_buddy_json(raw: bytes) -> BuddyPayload:
    """把一段搭子 JSON 解析成 ``BuddyPayload``。"""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - 要把原因说给用户听
        raise TransferError(f"这份搭子文件不是合法的 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise TransferError("搭子文件的顶层应该是一个对象（{...}）。")

    kind = str(data.get("type") or "")
    if kind and kind not in (BUDDY_TYPE, ""):
        # 允许缺 type（扁平格式就没有），但写了别的值要说清
        raise TransferError(f"这个文件的 type 是「{kind}」，不是搭子文件。")

    name = _as_text(_pick(data, "name", "名称", "搭子名称")).strip()
    if not name:
        raise TransferError("搭子文件里没有「名称」—— 名字是必须的。")

    # 人格三件套：官网放在 persona 对象里，扁平格式直接平铺
    block = data.get("persona") if isinstance(data.get("persona"), dict) else {}
    soul = _as_text(_pick(block, "SOUL.md", "soul.md", "soul", "SOUL")) or _as_text(
        _pick(data, "soul", "soul_md", "SOUL.md", "soul.md", "SOUL")
    )
    identity = _as_text(_pick(block, "IDENTITY.md", "identity.md", "identity", "IDENTITY")) or _as_text(
        _pick(data, "identity", "identity_md", "IDENTITY.md", "identity.md", "IDENTITY")
    )
    rules = _as_text(_pick(block, "RULES.md", "rules.md", "rules", "RULES")) or _as_text(
        _pick(data, "rules", "rules_md", "RULES.md", "rules.md", "RULES")
    )

    raw_skills = _pick(data, "skills", "技能名", "技能", "enabled_skills")
    if isinstance(raw_skills, str):
        skills = [item.strip() for item in raw_skills.replace("，", ",").split(",") if item.strip()]
    elif isinstance(raw_skills, list):
        skills = [str(item).strip() for item in raw_skills if str(item).strip()]
    else:
        skills = []

    temperature: float | None = None
    raw_temp = _pick(data, "temperature", "温度")
    if raw_temp is not None:
        try:
            temperature = float(raw_temp)
        except (TypeError, ValueError) as exc:
            raise TransferError(f"温度「{raw_temp}」不是数字。") from exc
        # 范围与 `AssistantProfile.temperature`（ge=0, le=2）对齐。
        # 在这里先挡一次，是因为落盘那一刻才炸的话，用户看到的是 pydantic 的
        # 校验堆栈，而不是"温度写错了"——而且那时技能包已经装进去了。
        if not 0 <= temperature <= 2:
            raise TransferError(f"温度要在 0 到 2 之间，收到的是 {temperature}。")

    return BuddyPayload(
        name=name,
        nickname=_as_text(_pick(data, "nickname", "昵称")).strip(),
        emoji=_as_text(_pick(data, "emoji", "图标")).strip() or "🤖",
        # 说明：优先 description；官网的 intro_md 更长，作兜底
        description=_as_text(_pick(data, "description", "说明", "简介", "intro_md")).strip(),
        soul=soul,
        identity=identity,
        rules=rules,
        temperature=temperature,
        skills=skills,
        source_id=_as_text(_pick(data, "id", "搭子id")).strip(),
        skill_pack=_as_text(_pick(data, "skill_pack", "技能包")).strip(),
    )


def _read_archive(payload: bytes, what: str) -> zipfile.ZipFile:
    if len(payload) > MAX_TRANSFER_BYTES:
        raise TransferError(
            f"{what}太大了（{len(payload) / 1024 / 1024:.1f} MB，上限 "
            f"{MAX_TRANSFER_BYTES // 1024 // 1024} MB）。"
        )
    try:
        return zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise TransferError(f"{what}不是合法的 zip 压缩包。") from exc


def _zip_subtree(archive: zipfile.ZipFile, prefix: str) -> bytes | None:
    """把压缩包里的一个子目录**原样**打包成一个新的 zip。

    为什么绕这一圈：技能包的解析（``skill/package.parse_package``）吃的是
    "一个 zip 里装着这个技能"；而搭子包里技能可以是**一个文件夹**。
    转成同一形态之后，解析就只有一份实现，不必为"文件夹形式"再写一条解析路径。
    """
    head = f"{prefix}/"
    members = [name for name in archive.namelist() if name.startswith(head) and not name.endswith("/")]
    if not members:
        return None
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for name in members:
            target.writestr(name[len(head) :], archive.read(name))
    return buffer.getvalue()


def _collect_skill_packs(archive: zipfile.ZipFile) -> list[tuple[str, bytes]]:
    """找出包里的全部技能包。

    两种写法都支持（用户口径：技能包是 zip 或文件夹）：

    ① 嵌在包里的 ``.zip``（一个 zip = 一个技能包）；
    ② 任何**含 skill.json / SKILL.md 的目录**（转成 zip 之后交给同一套解析）；
    ③ 包根目录直接放 skill.json / SKILL.md —— 整个包就是一个技能包。
    """
    names = [name for name in archive.namelist() if not name.endswith("/")]
    packs: list[tuple[str, bytes]] = []

    for name in names:
        if name.lower().endswith(".zip"):
            packs.append((name.rsplit("/", 1)[-1][:-4], archive.read(name)))

    folders: set[str] = set()
    root_has_marker = False
    for name in names:
        if name.rsplit("/", 1)[-1].lower() not in _SKILL_MARKERS:
            continue
        if "/" in name:
            folders.add(name.rsplit("/", 1)[0])
        else:
            root_has_marker = True
    for folder in sorted(folders):
        data = _zip_subtree(archive, folder)
        if data is not None:
            packs.append((folder.rsplit("/", 1)[-1], data))
    if root_has_marker:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
            for name in names:
                target.writestr(name, archive.read(name))
        packs.append(("skill", buffer.getvalue()))

    if len(packs) > MAX_PACKED_ITEMS:
        raise TransferError(
            f"这个包里有 {len(packs)} 个技能包，超过上限 {MAX_PACKED_ITEMS} 个。"
            "请确认是不是传错了文件。"
        )
    return packs


def _find_buddy_json(archive: zipfile.ZipFile) -> tuple[str, bytes] | None:
    """在包里找搭子 JSON：先认约定文件名，再认"根级里唯一一个能解析成搭子的 json"。"""
    root_json = [
        name
        for name in archive.namelist()
        if not name.endswith("/") and "/" not in name and name.lower().endswith(".json")
    ]
    for name in root_json:
        if name.lower() in _BUDDY_FILE_NAMES:
            return name, archive.read(name)
    for name in root_json:
        raw = archive.read(name)
        try:
            parse_buddy_json(raw)
        except TransferError:
            continue
        return name, raw
    return None


def parse_buddy_package(payload: bytes, package_name: str) -> BuddyPackage:
    """解析一个搭子包。

    除了 zip，也接受**裸 JSON** —— 官网现在的导入文件就是一个单独的 ``.json``
    （技能包是另一个 zip），用户直接把那个 json 拖进来也该能用。
    """
    # zip 以 PK 开头；不是 zip 就按 JSON 解析
    if payload.lstrip()[:1] != b"{":
        return _parse_buddy_zip(payload, package_name)
    return BuddyPackage(buddy=parse_buddy_json(payload))


def _parse_buddy_zip(payload: bytes, package_name: str) -> BuddyPackage:
    archive = _read_archive(payload, "搭子包")
    try:
        found = _find_buddy_json(archive)
        if found is None:
            raise TransferError(
                "这个包里没找到搭子文件（应该是包根目录下的一个 .json，"
                "写明名称、说明、人格三件套等字段）。"
            )
        buddy = parse_buddy_json(found[1])
        return BuddyPackage(buddy=buddy, skill_packs=_collect_skill_packs(archive))
    finally:
        archive.close()


def parse_group_package(payload: bytes, package_name: str) -> GroupPackage:
    """解析一个搭子群包（zip）：``group.json`` + 多个搭子包。"""
    archive = _read_archive(payload, "搭子群包")
    try:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        group_file = next(
            (name for name in names if name.rsplit("/", 1)[-1].lower() in _GROUP_FILE_NAMES),
            None,
        )
        if group_file is None:
            raise TransferError("搭子群包里没找到 group.json（群配置）。")

        try:
            raw_group = json.loads(archive.read(group_file).decode("utf-8-sig"))
        except Exception as exc:  # noqa: BLE001
            raise TransferError(f"group.json 不是合法的 JSON：{exc}") from exc
        if not isinstance(raw_group, dict):
            raise TransferError("group.json 的顶层应该是一个对象（{...}）。")

        kind = str(raw_group.get("type") or "")
        if kind and kind not in (GROUP_TYPE, ""):
            raise TransferError(f"group.json 的 type 是「{kind}」，不是搭子群配置。")

        # 名字单独存一个不易被覆盖的变量：下面的循环里会用到 `entry`，
        # 早先这里叫 `name`，结果被 `for name in names` 循环变量**覆盖**成
        # 最后一个 zip 条目 —— 群名变成了"buddies/xx/xx.json"。
        group_name = _as_text(_pick(raw_group, "name", "名称", "群名称")).strip()
        if not group_name:
            raise TransferError("group.json 里没有「群名称」。")

        order_raw = _pick(raw_group, "speaking_order", "发言顺序")
        order = (
            [str(item).strip() for item in order_raw if str(item).strip()]
            if isinstance(order_raw, list)
            else []
        )

        # ---- 成员：group.json 同级的子目录 或 .zip ----
        #
        # 约定（同一份说明也写进交付文档）：
        #
        #   group.json
        #   buddies/<搭子名>/            ← 文件夹形式：里面有搭子 json 与 skills/
        #   buddies/<搭子名>.zip         ← zip 形式
        #
        # **技能包一律放在各自的搭子包里**，这里不单独认 —— 用户的口径就是
        # "搭子包 = 搭子 json + 多个技能包"，技能跟搭子走，不跟群走。
        members: list[BuddyPackage] = []
        base = group_file.rsplit("/", 1)[0] if "/" in group_file else ""
        # 成员放在哪个目录下：约定是 `buddies/`（也认「搭子」/`members`）；
        # 没有这个目录时，成员就与 group.json 同级。
        container = f"{base}/" if base else ""
        for candidate in ("buddies", "搭子", "members"):
            probe = f"{container}{candidate}/"
            if any(entry.startswith(probe) for entry in names):
                container = probe
                break

        # ① 文件夹形式的搭子包（容器下一层目录，里面**直接**放着搭子 json）
        subdirs = sorted(
            {
                entry[len(container) :].split("/")[0]
                for entry in names
                if entry.startswith(container) and "/" in entry[len(container) :]
            }
        )
        for folder in subdirs:
            if not _has_buddy_json(archive, f"{container}{folder}"):
                continue
            data = _zip_subtree(archive, f"{container}{folder}")
            if data is not None:
                members.append(_parse_buddy_zip(data, folder))

        # ② zip 形式的搭子包（只看容器这一层）
        for entry in names:
            if not entry.startswith(container) or "/" in entry[len(container) :]:
                continue
            if not entry.lower().endswith(".zip"):
                continue
            label = entry.rsplit("/", 1)[-1][:-4]
            try:
                members.append(_parse_buddy_zip(archive.read(entry), label))
            except TransferError as exc:
                # 如实记一笔，但**不在这里报错**：整包"一个成员都没解出来"
                # 最后会统一给出更准确的那条提示
                logger.warning("群包里的 %s 解不出搭子包，已跳过：%s", entry, exc)

        if not members:
            raise TransferError(
                "这个搭子群包里没有找到任何搭子包。每个搭子包应该是一个文件夹"
                "（里面有搭子 json 与 skills/）或者一个 .zip。"
            )
        if len(members) > MAX_PACKED_ITEMS:
            raise TransferError(
                f"这个群包里有 {len(members)} 个搭子包，超过上限 {MAX_PACKED_ITEMS} 个。"
            )

        return GroupPackage(
            name=group_name,
            members=members,
            speaking_order=order,
            confirm_mode=_as_text(_pick(raw_group, "confirm_mode")).strip() or None,
            reasoning_effort=_as_text(_pick(raw_group, "reasoning_effort")).strip() or None,
        )
    finally:
        archive.close()


def _has_buddy_json(archive: zipfile.ZipFile, folder: str) -> bool:
    """这个目录里**直接**放着一个"像搭子文件"的 json 吗（不等于技能包的 skill.json）。"""
    prefix = f"{folder}/"
    for name in archive.namelist():
        if not name.startswith(prefix) or name.endswith("/"):
            continue
        leaf = name[len(prefix) :]
        if "/" in leaf:
            continue
        low = leaf.lower()
        if low.endswith(".json") and low not in _SKILL_MARKERS and low not in _GROUP_FILE_NAMES:
            return True
    return False


# --------------------------------------------------------------------------- #
# 落盘
# --------------------------------------------------------------------------- #
def _skill_key_index(runtime: Any) -> dict[str, str]:
    """「用户可能怎么写」→「规范键」的唯一对照表。

    规范键 = ``enabled_skills`` 白名单里该写的那一个：自定义技能用 ``defn.id``
    （见 ``skill/custom.py`` 的 ``collect_instructions`` 与工具过滤），内置技能
    用 manager 里的技能名。

    **为什么必须有这张表**（2026-09-28 用户实测撞到）：解析技能名
    （``_resolve_skills``）原先只查 manager 里的工具名，而**指导型技能
    （``kind="instruction"``）根本不会被注册进 manager** ——
    ``custom.sync_custom_skills`` 明确跳过它们（它不执行动作，注册了只会让模型
    看到一个"调了也没意义"的工具，它的内容走 ``collect_instructions`` 进 system）。
    于是随包带进来的指导型技能**永远匹配不到**，而同一个包里的同一个技能在
    ``_skill_already_here`` 那边（查的是 ``custom_skills.skills``）却被判成
    "已存在"：用户看到的就是同一条技能一边打绿勾、一边进「未找到」清单。

    ⚠️ 查技能"存不存在"时必须走这里，不要各自去查 ``all_names()`` 或
    ``custom_skills``：两处各查各的，迟早再分叉一次。
    """
    index: dict[str, str] = {}
    # 先放可执行技能（内置 + 自定义的非指导型）：同名时以它们为准。
    # `enabled_only=False` 是刻意的 —— **被关掉的技能依然是"本机已有的技能"**，
    # 漏看它们会让"导入时自动打开"变成"导入时说找不到"。
    for meta in runtime.skills.list_metas(enabled_only=False):
        index.setdefault(meta.name, meta.name)
        if meta.display_name:
            index.setdefault(meta.display_name, meta.name)
    # 再放全部自定义技能（**含指导型**）：这些正是 manager 里看不到的那一类
    for defn in runtime.custom_skills.skills:
        index.setdefault(defn.id, defn.id)
        if defn.name:
            index.setdefault(defn.name, defn.id)
    return index


def _resolve_skills(runtime: Any, wanted: list[str]) -> tuple[list[str], list[str]]:
    """把包里的"技能名"对上本机真实存在的技能。

    先按技能内部 ``name`` 精确匹配，再按 ``display_name`` 匹配（用户写的可能是
    界面上看到的中文名）。**匹配不到的逐条返回**，由调用方如实报给用户 ——
    静默丢弃会让用户以为"技能都装上了"。
    """
    index = _skill_key_index(runtime)
    resolved: list[str] = []
    missing: list[str] = []
    for item in wanted:
        # 先按原样查，再按去掉首尾空格的查（包里手写的 json 常带尾空格，
        # 而"多一个空格"在界面上完全看不出来，用户只会看到"未找到"）
        target = index.get(item) or index.get(item.strip())
        if target is None:
            missing.append(item)
        elif target not in resolved:
            resolved.append(target)
    return resolved, missing


def _skill_already_here(runtime: Any, defn: Any) -> bool:
    """这个技能本机已经有了吗（按 id 或名字判）。

    判"已有"是为了满足用户那条口径：**技能已存在就不重复导入**，只把它配给新搭子。
    不判的话，既有的安装路径会给重名技能加 ``-2`` 后缀再装一遍 ——
    "同一个搭子导两次"就会多出一堆 ``xxx-2``、``xxx-3``，而新搭子的技能白名单里
    指的是哪一个也说不清。
    """
    # 与 `_skill_key_index` **同源但刻意窄一层**：自定义技能看 id 与名字，
    # 内置技能只看技能名，**不认内置技能的显示名**。
    # 这一处不对称是有理由的：两类判断的错法代价不同 —— "判已有"误判会让用户
    # 新装的技能**静默缺失**（他以为装上了），所以宁可漏判；而 `_resolve_skills`
    # 相反，匹配得越宽越好，宽了只是把已有的技能正确地指出来。
    existing = runtime.custom_skills.skills
    ids = {item.id for item in existing}
    names = {(item.name or "").strip() for item in existing if (item.name or "").strip()}
    # 内置技能也叫这个名字 —— 那更不该再装一份自定义的。
    # 这里换成与别处同源的 known_skill_names（含工具名 + 自定义技能的 id/名字）：
    # 上一版手写的 ids/names 与它语义相同，但两份实现迟早分叉。
    known = known_skill_names(runtime)
    return defn.id.strip() in (ids | known) or (defn.name or "").strip() in (names | known)


def _install_skill_packs(
    runtime: Any, packs: list[tuple[str, bytes]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """逐包装技能、逐条回报。

    返回 ``(逐条结果, 这些包里涉及的技能 id)`` —— 后一项要**配给新搭子**：
    包里带技能包，本来就是为了让这个搭子用得上它们。

    复用 ``skill/install.py`` 那套"解析 → 校验 → 落盘 → 装 → 重载"的唯一实现，
    但在装之前**先把本机已有的滤掉**（见 ``_skill_already_here``）。
    """
    # ⚠️ 原先这里 import 的是 `server/routes/skills.py` 里的**兼容包装**（审计 H-06）：
    # 领域层为了装技能，反过来依赖路由层。包装已在末批删除，这里直接指向真实实现。
    from ..skill.install import install_defs, unpack_for
    from ..skill.package import bind_script_commands

    results: list[dict[str, Any]] = []
    skill_ids: list[str] = []
    for pack_name, payload in packs:
        try:
            parsed = parse_package(payload, pack_name)
        except ValueError as exc:
            # 一个包坏掉不该拖垮整次导入：如实记下，继续装下一个
            results.append({"pack": pack_name, "name": pack_name, "ok": False, "message": str(exc)})
            continue
        results.extend({**item, "pack": pack_name} for item in parsed.results)

        fresh: list[Any] = []
        for item in parsed.defs:
            if _skill_already_here(runtime, item):
                skill_ids.append(item.id)
                results.append(
                    {
                        "pack": pack_name,
                        "name": item.name or item.id,
                        "id": item.id,
                        "ok": True,
                        "skipped": True,
                        "message": "本机已有这个技能，未重复导入（直接配置给新搭子）",
                    }
                )
            else:
                fresh.append(item)
        if not fresh:
            continue

        def prepare(defn: Any, _parsed: Any = parsed) -> Any:
            """随包带的技能也要整包落盘 —— 只装定义的话，SKILL.md 里写的
            "按 templates/x.md 来"那份模板就没了，模型只能凭空编。"""
            unpack_for(runtime, defn, _parsed.members.members, _parsed.members.container)
            return bind_script_commands(defn, runtime.paths.skills_dir / defn.id)

        before = len(results)
        install_defs(runtime, fresh, results, prepare=prepare)
        for item in results[before:]:
            item.setdefault("pack", pack_name)
            if item.get("id"):
                skill_ids.append(str(item["id"]))
    return results, skill_ids


def _open_disabled_skills(runtime: Any, keys: list[str]) -> list[str]:
    """把这次要用、但**被全局关掉**的自定义技能打开；返回打开的 id。

    用户口径（2026-09-28）：「导入搭子包时随包带的技能，如果本机已有但被关掉了，
    配给新搭子并**自动打开**」。

    为什么必须打开、而不是"只配上去"：指导型技能在 ``custom.collect_instructions``
    里会被 ``defn.enabled`` 直接跳过，工具技能也会被 ``SkillMeta.enabled`` 过滤 ——
    把一份关着的技能配给搭子等于配了个摆设，而界面上**一句提示都不会有**
    （用户只会觉得"这个搭子怎么不按包里写的来做"）。

    只动 ``keys`` 里那几个（= 这次真正要用到的）：全量打开会把用户自己关掉的、
    跟这个搭子无关的技能一并打开，那是另一件事、不该顺手做。
    """
    if not keys:
        return []
    wanted = set(keys)
    config = runtime.custom_skills.model_copy(deep=True)
    opened: list[str] = []
    for defn in config.skills:
        if defn.id in wanted and not defn.enabled:
            config.upsert(defn.model_copy(update={"enabled": True}))
            opened.append(defn.id)
    if opened:
        runtime.config_store.save_custom_skills(config)
        runtime.reload_custom_skills(config)
    return opened


def _find_existing(runtime: Any, payload: BuddyPayload) -> Any:
    """这个包对应的搭子是不是已经在本机了（先按 id、再按名字）。"""
    if payload.source_id:
        found = runtime.assistants.get(payload.source_id)
        if found is not None:
            return found
    for item in runtime.assistants.sorted():
        if item.name.strip() == payload.name:
            return item
    return None


def _apply_profile(runtime: Any, assistant_id: str, payload: BuddyPayload, skills: list[str]) -> Any:
    """把昵称/图标/简介/温度/技能写进档案；技能取**并集**（不抹掉用户后加的）。"""
    config = runtime.assistants.model_copy(deep=True)
    current = config.get(assistant_id)
    if current is None:
        raise TransferError(f"搭子 {assistant_id} 不在清单里，无法更新。")

    merged = list(current.enabled_skills)
    for item in skills:
        if item not in merged:
            merged.append(item)

    changes: dict[str, Any] = {"enabled_skills": merged}
    if payload.nickname:
        changes["nickname"] = payload.nickname
    if payload.emoji:
        changes["emoji"] = payload.emoji
    if payload.description:
        changes["description"] = payload.description
    if payload.temperature is not None:
        changes["temperature"] = payload.temperature

    updated = current.model_copy(update=changes)
    config.upsert(updated)
    runtime.save_assistants(config)
    return updated


def _write_persona_verbatim(runtime: Any, assistant_id: str, payload: BuddyPayload) -> list[str]:
    """人格三件套**原文写入**（见模块开头的取舍说明）。返回写了哪几份。"""
    written: list[str] = []
    for name, text in (
        (persona.SOUL_FILE, payload.soul),
        (persona.IDENTITY_FILE, payload.identity),
        (persona.RULES_FILE, payload.rules),
    ):
        if not text.strip():
            continue
        persona.write_file(runtime.paths, assistant_id, name, text)
        written.append(name)
    return written


async def apply_buddy(
    runtime: Any, package: BuddyPackage, *, actor_id: str | None = None
) -> dict[str, Any]:
    """落盘一个搭子包：装技能 → 建/更新搭子 → 写人格文件。逐条回报。"""
    results: list[dict[str, Any]] = []

    # ① 先装技能再建搭子：技能名要对得上，就得先让它们注册进 manager
    pack_results, packed_skills = _install_skill_packs(runtime, package.skill_packs)
    results.extend(pack_results)

    payload = package.buddy
    # 随包带来的心鉴学专属技能名：**剔除 + 说明**，而不是让导出一整个失败。
    #
    # ⚠️ 这里刻意不用 ``reject_reserved_skill_names``（那条是给模型用的硬拒绝）：
    # 官网导出的搭子包里**本来就写着**这几个名字，硬拒会让"导入官方包"直接报错 ——
    # 用户看到的是"包坏了"。正确做法是收下这个包、把这几项丢掉、
    # 并告诉他"这是自动生效的，不用配"。
    reserved = [item for item in payload.skills if xjx.is_reserved(item)]
    if reserved:
        # BuddyPayload 是 dataclass（不是 pydantic），换字段要用 replace
        payload = replace(
            payload,
            skills=[item for item in payload.skills if not xjx.is_reserved(item)],
        )
        results.append(
            {
                "name": "专属技能",
                "ok": True,
                "message": (
                    f"包里写了「{'、'.join(reserved)}」，已跳过："
                    "这是按当前线路自动启用、只属于对应搭子的内置专属技能，不需要（也不能）配置。"
                ),
            }
        )

    # 包里写了**别的搭子的专属技能**（团队管理 / 电脑操作 / 产品经理方法论那一批）：
    # 同样**剔除 + 说明**。
    #
    # ⚠️ 2026-10-07 补：这条路原先没做这件事 —— 用户保存搭子那条路会拒绝
    # （`routes/assistants.py::_validate_skills`），但**导入搭子包**这条不走那里，
    # 于是外来包里的专属名会静默落进新搭子的清单：装配时被归属过滤排除（不生效），
    # 而导入结果却回报"已配置 N 个技能"，用户以为配上了。
    # 不硬拒的理由与上一条相同：外来包不该因为"多带了个名字"就整包导入失败。
    from ..skill import groups

    exclusive = [item for item in payload.skills if groups.is_exclusive(item)]
    if exclusive:
        payload = replace(payload, skills=groups.without_exclusive(payload.skills))
        results.append(
            {
                "name": "专属技能",
                "ok": True,
                "message": (
                    f"包里写了「{'、'.join(exclusive)}」，已跳过："
                    "这些技能按搭子归属自动生效，只有归属的搭子能用，不需要（也不能）配置。"
                ),
            }
        )
    resolved, missing = _resolve_skills(runtime, payload.skills)
    # 随包进来的技能也配给它 —— 包里带技能包就是为了让这个搭子用得上
    for item in packed_skills:
        if item not in resolved:
            resolved.append(item)
    # 随包技能里凡是**被全局关掉**的都打开（产品约定），并如实回报 ——
    # 不回报的话用户只看到一句"已存在"，既不知道它之前是关着的、也不知道被打开了。
    for skill_id in _open_disabled_skills(runtime, resolved):
        results.append(
            {
                "name": skill_id,
                "id": skill_id,
                "ok": True,
                "message": "本机已有但之前是关闭的，已自动打开",
            }
        )
    if payload.skills:
        results.append(
            {
                "name": "技能清单",
                "ok": not missing,
                "message": (
                    f"已配置 {len(resolved)} 个技能"
                    + (f"，未找到：{'、'.join(missing)}" if missing else "")
                ),
            }
        )

    existing = _find_existing(runtime, payload)
    # ⚠️ 导入是"改内置搭子"的最后一条路，而且它**按名字匹配**：
    # 一个叫「Soulmate」的包会直接命中产品自带的那位，然后把它的人设、简介、
    # 能力一并覆盖掉。用户看到的只是"导入成功"，代价是内置搭子被换了个人。
    # 所以这里明确拒绝并如实回报（不是静默跳过 —— 那样用户会以为包装上了）。
    if existing is not None and locked_builtins.is_locked(existing.id):
        results.append(
            {
                "name": payload.name,
                "id": existing.id,
                "ok": False,
                "kind": "assistant",
                "message": locked_builtins.locked_persona_message(persona.IDENTITY_FILE),
            }
        )
        return {
            "ok": False,
            "action": "blocked",
            "assistant": {"id": existing.id, "name": existing.name},
            "skills": [],
            "skills_missing": missing,
            "results": results,
        }
    if existing is None:
        created = await runtime.orchestrator.create_assistant(
            name=payload.name,
            description=payload.description,
            identity=payload.identity,
            rules=payload.rules,
            emoji=payload.emoji,
            skills=resolved or None,
            actor_id=actor_id,
            # 导入这条路本身就是"已经用上现成的了"，不该再被"先查官网"的闸门拦住
            from_import=True,
        )
        assistant_id = created["id"]
        action = "create"
    else:
        assistant_id = existing.id
        action = "update"

    profile = _apply_profile(runtime, assistant_id, payload, resolved)
    files = _write_persona_verbatim(runtime, assistant_id, payload)
    if action == "update":
        # 建的那条由 create_assistant 推过了；更新这条要自己推，否则界面不刷新
        runtime.events.publish("assistants_changed", assistant_id=assistant_id, action="update")

    results.append(
        {
            "name": payload.name,
            "id": assistant_id,
            "ok": True,
            "kind": "assistant",
            "message": (
                f"{'更新' if action == 'update' else '新建'}搭子「{payload.name}」"
                + (f"，写入人格文件 {'、'.join(files)}" if files else "（包里没带人格文件）")
            ),
        }
    )
    return {
        "ok": True,
        "action": action,
        "assistant": {"id": profile.id, "name": profile.name},
        "skills": resolved,
        "skills_missing": missing,
        "results": results,
    }


async def apply_buddy_group(
    runtime: Any, package: GroupPackage, *, actor_id: str | None = None
) -> dict[str, Any]:
    """落盘一个搭子群包：逐个导成员 → 建/更新群。"""
    results: list[dict[str, Any]] = []
    member_ids: list[str] = []
    for member in package.members:
        outcome = await apply_buddy(runtime, member, actor_id=actor_id)
        results.extend(outcome["results"])
        member_ids.append(outcome["assistant"]["id"])

    if len(member_ids) < 2:
        raise TransferError(
            f"群「{package.name}」只解析出 {len(member_ids)} 个搭子，"
            "一个群至少要两个搭子 —— 请检查包里的搭子包是否完整。"
        )

    # 按成员**名字**匹配发言顺序（包里写的是名字，不是 id）
    order: list[str] = []
    by_name = {runtime.assistants.get(mid).name: mid for mid in member_ids if runtime.assistants.get(mid)}
    for item in package.speaking_order:
        target = by_name.get(item)
        if target and target not in order:
            order.append(target)

    # 群包里的总管：导入路径**没有模型在场**，所以只在成员档案已经把谁写成总管时
    # 才指名（包里不写角色 → 交给 create_group 的位次兜底，与导入前的行为一致）。
    coordinator_id = ""
    for mid in member_ids:
        profile = runtime.assistants.get(mid)
        if profile is not None and (profile.group_role or "").strip() == "coordinator":
            coordinator_id = mid
            break

    existing = next(
        (item for item in runtime.groups.groups if item.name.strip() == package.name), None
    )
    if existing is None:
        created = await runtime.orchestrator.create_group(
            name=package.name,
            member_ids=member_ids,
            coordinator_id=coordinator_id,
            speaking_order=order or None,
            actor_id=actor_id,
            from_import=True,
        )
        group_id = created["id"]
        action = "create"
    else:
        config = runtime.groups.model_copy(deep=True)
        updated = existing.model_copy(
            update={
                "member_assistant_ids": member_ids,
                "speaking_order": order,
            }
        )
        config.upsert(updated)
        runtime.groups = runtime.config_store.save_groups(config)
        runtime.events.publish("groups_changed", group_id=existing.id, action="update")
        group_id = existing.id
        action = "update"

    # 群配置里其余可选字段（建群那条路径不管它们，这里补）
    if package.confirm_mode or package.reasoning_effort:
        config = runtime.groups.model_copy(deep=True)
        current = config.get(group_id)
        if current is not None:
            changes: dict[str, Any] = {}
            if package.confirm_mode:
                changes["confirm_mode"] = package.confirm_mode
            if package.reasoning_effort:
                changes["reasoning_effort"] = package.reasoning_effort
            config.upsert(current.model_copy(update=changes))
            runtime.groups = runtime.config_store.save_groups(config)

    group = runtime.groups.get(group_id)
    if group is None:
        raise TransferError(
            f"群「{package.name}」写进配置后又读不到了，请把日志发给我们。"
        )
    results.append(
        {
            "name": package.name,
            "id": group_id,
            "ok": True,
            "kind": "group",
            "message": (
                f"{'更新' if action == 'update' else '新建'}群「{package.name}」，"
                f"成员 {len(member_ids)} 个"
                "（审核员与优化顾问需另行提交，导入不替你决定）"
            ),
        }
    )
    members_info = [
        item.to_dict()
        for item in (runtime.assistants.get(mid) for mid in member_ids)
        if item is not None
    ]
    return {
        "ok": True,
        "action": action,
        "group": {"id": group_id, "name": group.name},
        "assistants": members_info,
        "results": results,
    }


__all__ = [
    "BuddyPackage",
    "BuddyPayload",
    "GROUP_TYPE",
    "GroupPackage",
    "MAX_TRANSFER_BYTES",
    "TransferError",
    "apply_buddy",
    "apply_buddy_group",
    "parse_buddy_json",
    "parse_buddy_package",
    "parse_group_package",
]
