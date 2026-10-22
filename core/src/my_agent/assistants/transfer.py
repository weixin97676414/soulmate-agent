


































































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



MAX_TRANSFER_BYTES = 32 * 1024 * 1024


MAX_PACKED_ITEMS = 40

BUDDY_TYPE = "xinjianxue.buddy"
GROUP_TYPE = "xinjianxue.buddy-group"


_SKILL_MARKERS = ("skill.json", "skill.md")
_BUDDY_FILE_NAMES = ("buddy.json", "assistant.json", "搭子.json")
_GROUP_FILE_NAMES = ("group.json", "群.json")


class TransferError(ValueError):
    pass





@dataclass
class BuddyPayload:


    name: str
    nickname: str = ""
    emoji: str = "🤖"
    description: str = ""
    soul: str = ""
    identity: str = ""
    rules: str = ""
    temperature: float | None = None
    skills: list[str] = field(default_factory=list)
    
    source_id: str = ""
    
    
    skill_pack: str = ""


@dataclass
class BuddyPackage:
    buddy: BuddyPayload
    
    skill_packs: list[tuple[str, bytes]] = field(default_factory=list)


@dataclass
class GroupPackage:
    name: str
    members: list[BuddyPackage] = field(default_factory=list)
    speaking_order: list[str] = field(default_factory=list)
    confirm_mode: str | None = None
    reasoning_effort: str | None = None





def _pick(data: dict[str, Any], *keys: str) -> Any:

    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def parse_buddy_json(raw: bytes) -> BuddyPayload:

    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:  
        raise TransferError(f"这份搭子文件不是合法的 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise TransferError("搭子文件的顶层应该是一个对象（{...}）。")

    kind = str(data.get("type") or "")
    if kind and kind not in (BUDDY_TYPE, ""):
        
        raise TransferError(f"这个文件的 type 是「{kind}」，不是搭子文件。")

    name = _as_text(_pick(data, "name", "名称", "搭子名称")).strip()
    if not name:
        raise TransferError("搭子文件里没有「名称」—— 名字是必须的。")

    
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
        
        
        
        if not 0 <= temperature <= 2:
            raise TransferError(f"温度要在 0 到 2 之间，收到的是 {temperature}。")

    return BuddyPayload(
        name=name,
        nickname=_as_text(_pick(data, "nickname", "昵称")).strip(),
        emoji=_as_text(_pick(data, "emoji", "图标")).strip() or "🤖",
        
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
        except Exception as exc:  
            raise TransferError(f"group.json 不是合法的 JSON：{exc}") from exc
        if not isinstance(raw_group, dict):
            raise TransferError("group.json 的顶层应该是一个对象（{...}）。")

        kind = str(raw_group.get("type") or "")
        if kind and kind not in (GROUP_TYPE, ""):
            raise TransferError(f"group.json 的 type 是「{kind}」，不是搭子群配置。")

        
        
        
        group_name = _as_text(_pick(raw_group, "name", "名称", "群名称")).strip()
        if not group_name:
            raise TransferError("group.json 里没有「群名称」。")

        order_raw = _pick(raw_group, "speaking_order", "发言顺序")
        order = (
            [str(item).strip() for item in order_raw if str(item).strip()]
            if isinstance(order_raw, list)
            else []
        )

        
        
        
        
        
        
        
        
        
        
        members: list[BuddyPackage] = []
        base = group_file.rsplit("/", 1)[0] if "/" in group_file else ""
        
        
        container = f"{base}/" if base else ""
        for candidate in ("buddies", "搭子", "members"):
            probe = f"{container}{candidate}/"
            if any(entry.startswith(probe) for entry in names):
                container = probe
                break

        
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

        
        for entry in names:
            if not entry.startswith(container) or "/" in entry[len(container) :]:
                continue
            if not entry.lower().endswith(".zip"):
                continue
            label = entry.rsplit("/", 1)[-1][:-4]
            try:
                members.append(_parse_buddy_zip(archive.read(entry), label))
            except TransferError as exc:
                
                
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





def _skill_key_index(runtime: Any) -> dict[str, str]:


















    index: dict[str, str] = {}
    
    
    
    for meta in runtime.skills.list_metas(enabled_only=False):
        index.setdefault(meta.name, meta.name)
        if meta.display_name:
            index.setdefault(meta.display_name, meta.name)
    
    for defn in runtime.custom_skills.skills:
        index.setdefault(defn.id, defn.id)
        if defn.name:
            index.setdefault(defn.name, defn.id)
    return index


def _resolve_skills(runtime: Any, wanted: list[str]) -> tuple[list[str], list[str]]:






    index = _skill_key_index(runtime)
    resolved: list[str] = []
    missing: list[str] = []
    for item in wanted:
        
        
        target = index.get(item) or index.get(item.strip())
        if target is None:
            missing.append(item)
        elif target not in resolved:
            resolved.append(target)
    return resolved, missing


def _skill_already_here(runtime: Any, defn: Any) -> bool:







    
    
    
    
    
    existing = runtime.custom_skills.skills
    ids = {item.id for item in existing}
    names = {(item.name or "").strip() for item in existing if (item.name or "").strip()}
    
    
    
    known = known_skill_names(runtime)
    return defn.id.strip() in (ids | known) or (defn.name or "").strip() in (names | known)


def _install_skill_packs(
    runtime: Any, packs: list[tuple[str, bytes]]
) -> tuple[list[dict[str, Any]], list[str]]:








    
    
    from ..skill.install import install_defs, unpack_for
    from ..skill.package import bind_script_commands

    results: list[dict[str, Any]] = []
    skill_ids: list[str] = []
    for pack_name, payload in packs:
        try:
            parsed = parse_package(payload, pack_name)
        except ValueError as exc:
            
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

    if payload.source_id:
        found = runtime.assistants.get(payload.source_id)
        if found is not None:
            return found
    for item in runtime.assistants.sorted():
        if item.name.strip() == payload.name:
            return item
    return None


def _apply_profile(runtime: Any, assistant_id: str, payload: BuddyPayload, skills: list[str]) -> Any:

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

    results: list[dict[str, Any]] = []

    
    pack_results, packed_skills = _install_skill_packs(runtime, package.skill_packs)
    results.extend(pack_results)

    payload = package.buddy
    
    
    
    
    
    
    reserved = [item for item in payload.skills if xjx.is_reserved(item)]
    if reserved:
        
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
    
    for item in packed_skills:
        if item not in resolved:
            resolved.append(item)
    
    
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

    
    order: list[str] = []
    by_name = {runtime.assistants.get(mid).name: mid for mid in member_ids if runtime.assistants.get(mid)}
    for item in package.speaking_order:
        target = by_name.get(item)
        if target and target not in order:
            order.append(target)

    
    
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
