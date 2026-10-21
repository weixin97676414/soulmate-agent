



























from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from ..assistants import evolution, lifecycle, locked_builtins
from ..assistants.persona import IDENTITY_FILE, MEMORY_FILE, RULES_FILE, SOUL_FILE, read_file
from ..config.schemas import AssistantProfile, GroupProfile
from ..skill import groups
from ..skill.builtin import xjx
from ..skill.custom import known_skill_names
from ..storage import images

logger = logging.getLogger(__name__)




_THINKING_RULE = (
    "开始策划前必须先调用 ai_thinking_mode 技能（AI 思考模式·道家做局思维）进行分析梳理。"
)
_RESTRUCTURE_RULE = (
    "策划完成后必须调用 team_restructure 技能重塑团队：先查看现有群成员的设定与技能配置，"
    "再围绕任务核心把团队调整为最佳配置。"
)







MAX_NICKNAME_CHARS = 24


MAX_EMOJI_CHARS = 8





AVATAR_MAX_BYTES = 512 * 1024


_ROLE_NAMES: dict[str, str] = {
    "coordinator": "协调者（总管）",
    "worker": "执行者",
    "reviewer": "审核员",
    "advisor": "优化顾问",
}


class Orchestrator:








    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        
        
        self._tasks: dict[str, asyncio.Task[None]] = {}

    
    
    
    @property
    def running(self) -> list[str]:

        return [group_id for group_id, task in self._tasks.items() if not task.done()]

    def list_assistants(self, *, assistant_id: str = "") -> list[dict[str, Any]]:











        runtime = self._runtime
        wanted = assistant_id.strip()
        result: list[dict[str, Any]] = []
        for item in runtime.assistants.sorted():
            if wanted and item.id != wanted:
                continue
            entry: dict[str, Any] = {
                "id": item.id,
                "name": item.nickname or item.name,
                "description": item.description,
                "skills": list(item.enabled_skills),
                
                
                "group_role": item.group_role,
            }
            for label, file_name in (
                ("identity", IDENTITY_FILE),
                ("rules", RULES_FILE),
                ("tone", SOUL_FILE),
            ):
                try:
                    entry[label] = read_file(runtime.paths, item.id, file_name).strip()
                except (OSError, ValueError) as exc:
                    
                    entry[label] = ""
                    entry.setdefault("read_errors", []).append(f"{file_name}: {exc}")
            result.append(entry)
        return result

    async def list_groups(self) -> list[dict[str, Any]]:










        runtime = self._runtime
        groups: list[dict[str, Any]] = []
        for item in runtime.groups.groups:
            threads: list[dict[str, Any]] = []
            if runtime.db_ready:
                try:
                    rows = await runtime.group_thread_repo.list_threads(item.id)
                except Exception as exc:  
                    logger.warning("读取群对话列表失败 group=%s: %s", item.id, exc)
                    rows = []
                threads = [
                    {"id": row["id"], "title": row["title"], "updated_at": row["updated_at"]}
                    for row in rows
                ]
            groups.append(
                {
                    "id": item.id,
                    "name": item.name,
                    
                    
                    "members": [
                        {"id": member_id, "name": self._display_name(member_id)}
                        for member_id in item.member_assistant_ids
                    ],
                    
                    "roles": {
                        "reviewer": self._role_brief(item.reviewer_id),
                        "advisor": self._role_brief(item.advisor_id),
                    },
                    
                    
                    "threads": threads,
                }
            )
        return groups

    def _role_brief(self, assistant_id: str) -> dict[str, Any] | None:

        cleaned = (assistant_id or "").strip()
        if not cleaned:
            return None
        return {"id": cleaned, "name": self._display_name(cleaned)}

    def _display_name(self, assistant_id: str) -> str:
        profile = self._runtime.assistants.get(assistant_id)
        if profile is None:
            
            return f"{assistant_id}（已删除）"
        return profile.nickname or profile.name

    
    
    
    def _ensure_library_checked(self, from_import: bool) -> None:












        if from_import:
            return
        library = getattr(self._runtime, "buddy_library", None)
        if library is None or library.checked:
            return
        raise ValueError(
            "新建之前必须先**查一遍官网搭子库**：先调 buddy_library_list，"
            "看官网有没有现成的搭子 —— 有合适的就用 buddy_import 直接导进来"
            "（技能包会一起装好），一个合适的都没有再自己建。"
            "如果读取官网失败，也要在回复里说明「官网未查到（附原因），我将自行创建」，"
            "不要跳过这一步。"
        )

    async def create_assistant(
        self,
        *,
        name: str,
        description: str = "",
        identity: str = "",
        abilities: str = "",
        rules: str = "",
        tone: str = "",
        emoji: str = "🤖",
        skills: list[str] | None = None,
        group_role: str = "",
        actor_id: str | None = None,
        from_import: bool = False,
    ) -> dict[str, Any]:
















        runtime = self._runtime
        from ..skill.package import slugify

        self._ensure_library_checked(from_import)

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("搭子得有个名字。")
        existing = [item for item in runtime.assistants.sorted() if item.name == clean_name]
        if existing:
            raise ValueError(
                f"已经有一个叫「{clean_name}」的搭子（id={existing[0].id}），"
                "直接用那个就好 —— 请先看一遍现有搭子清单，别建重复的。"
            )

        
        
        
        
        xjx.reject_reserved_skill_names(skills or [])

        wanted: list[str] = []
        dropped: list[str] = []
        
        
        
        known = known_skill_names(runtime)
        for item in skills or []:
            (wanted if item in known else dropped).append(item)

        
        
        
        
        
        
        
        
        
        wanted = groups.without_exclusive(wanted)

        
        
        
        
        
        
        
        
        
        
        
        
        
        is_analysis = group_role in ("coordinator", "advisor") or any(
            keyword in (description + identity)
            for keyword in ("策划", "规划", "分析", "策略", "咨询", "顾问")
        )
        is_coordinator = group_role == "coordinator"

        
        
        
        
        
        imposed_rules: list[str] = []
        if is_analysis:
            imposed_rules.append(_THINKING_RULE)
        if is_coordinator:
            imposed_rules.append(_RESTRUCTURE_RULE)
        
        
        
        imposed_rules.append(evolution.evolution_rule(clean_name))
        if imposed_rules:
            rules = _merge_rules(rules, imposed_rules)

        profile = AssistantProfile(
            id=f"{slugify(clean_name, fallback='group')}-{uuid.uuid4().hex[:6]}",
            name=clean_name,
            description=description.strip(),
            emoji=emoji or "🤖",
            enabled_skills=wanted,
            
            
            group_role=group_role if group_role in ("coordinator", "worker", "reviewer", "advisor") else "",
            builtin=False,
        )
        config = runtime.assistants.model_copy(deep=True)
        config.upsert(profile)
        runtime.save_assistants(config)

        written, failed = self._write_setup_files(
            profile.id,
            profile.name,
            {
                IDENTITY_FILE: _identity_document(profile.name, identity, abilities),
                RULES_FILE: _rules_document(profile.name, rules),
                SOUL_FILE: _soul_document(profile.name, tone, description),
            },
        )

        await runtime.audit.op(
            kind="assistant",
            action="create",
            actor_id=actor_id,
            target=profile.id,
            detail=f"AI 新建搭子「{clean_name}」：{profile.description[:80] or '（没写简介）'}",
        )
        
        
        
        runtime.events.publish("assistants_changed", assistant_id=profile.id, action="create")

        result: dict[str, Any] = {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "setup_files": written,
            
            
            "required_skills": "已包含在内置技能中（每个搭子都有）",
        }
        if imposed_rules:
            result["imposed_rules"] = imposed_rules
        if dropped:
            
            
            result["ignored_skills"] = dropped
        if failed:
            result["setup_errors"] = failed
        return result

    async def append_assistant_setup(
        self,
        *,
        assistant_id: str,
        identity_append: str = "",
        rules_append: str = "",
        tone_append: str = "",
        memory_append: str = "",
        description_append: str = "",
        actor_id: str | None = None,
    ) -> dict[str, Any]:
















        runtime = self._runtime
        from ..assistants.persona import write_file

        profile = runtime.assistants.get(assistant_id)
        if profile is None:
            raise ValueError(f"搭子「{assistant_id}」不存在（请先用 team_list_assistants 看清单）。")

        
        
        
        docs = (
            (IDENTITY_FILE, identity_append),
            (RULES_FILE, rules_append),
            (SOUL_FILE, tone_append),
            
            (MEMORY_FILE, memory_append),
        )
        for file_name, extra in docs:
            if extra.strip():
                locked_builtins.ensure_persona_writable(assistant_id, file_name)
        if description_append.strip():
            
            locked_builtins.ensure_mutable(assistant_id, changes=("description",))

        appended: list[str] = []
        failed: list[str] = []
        for file_name, extra in docs:
            text = extra.strip()
            if not text:
                continue
            try:
                current = read_file(runtime.paths, profile.id, file_name)
            except (OSError, ValueError):
                current = ""
            
            merged = f"{current.rstrip()}\n\n{text}\n" if current.strip() else f"{text}\n"
            try:
                write_file(runtime.paths, profile.id, file_name, merged)
                appended.append(file_name)
            except ValueError as exc:  
                failed.append(f"{file_name}: {exc}")

        if description_append.strip():
            merged_description = f"{profile.description.rstrip()} {description_append.strip()}".strip()
            updated = profile.model_copy(update={"description": merged_description})
            config = runtime.assistants.model_copy(deep=True)
            config.upsert(updated)
            runtime.save_assistants(config)

        if appended or description_append.strip():
            await runtime.audit.op(
                kind="assistant",
                action="update",
                actor_id=actor_id,
                target=profile.id,
                detail=f"AI 补充搭子设定：{'、'.join(appended) or '简介'}",
            )
            runtime.events.publish("assistants_changed", assistant_id=profile.id, action="update")

        result: dict[str, Any] = {
            "id": profile.id,
            "appended": appended,
            "assistants": self.list_assistants(assistant_id=profile.id),
        }
        if failed:
            result["setup_errors"] = failed
        return result

    
    
    
    
    
    
    
    
    
    
    

    async def update_assistant_profile(
        self,
        *,
        assistant_id: str,
        nickname: str | None = None,
        emoji: str | None = None,
        avatar_source: str = "",
        clear_avatar: bool = False,
        temperature: float | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:

        runtime = self._runtime
        profile = runtime.assistants.get(assistant_id)
        if profile is None:
            raise ValueError(
                f"搭子「{assistant_id}」不存在。要看现有清单请先调 team_list_assistants。"
            )

        changes: dict[str, Any] = {}
        done: list[str] = []

        if nickname is not None:
            clean = nickname.strip()
            if not clean:
                raise ValueError("昵称不能为空。想换名字就给一个新名字。")
            if len(clean) > MAX_NICKNAME_CHARS or "\n" in clean:
                raise ValueError(
                    f"昵称最多 {MAX_NICKNAME_CHARS} 个字且不能换行"
                    f"（当前给了 {len(clean)} 个字）。"
                )
            changes["nickname"] = clean
            done.append(f"昵称改为「{clean}」")

        if emoji is not None:
            clean = emoji.strip()
            if not clean or len(clean) > MAX_EMOJI_CHARS:
                raise ValueError(f"图标要是一个表情符号（最多 {MAX_EMOJI_CHARS} 个字符）。")
            changes["emoji"] = clean
            done.append(f"图标改为 {clean}")

        if temperature is not None:
            if not 0 <= temperature <= 2:
                raise ValueError(f"温度必须在 0 到 2 之间（当前给了 {temperature}）。")
            changes["temperature"] = temperature
            done.append(f"温度改为 {temperature}")

        if clear_avatar:
            changes["avatar"] = ""
            done.append("头像已清掉（回到用图标显示）")
        elif avatar_source.strip():
            
            
            try:
                _, data_url = await images.to_data_url(
                    avatar_source, max_bytes=AVATAR_MAX_BYTES, workspace=runtime.workspace
                )
            except images.ImageSourceError as exc:
                
                raise ValueError(f"设置头像失败：{exc}") from exc
            
            
            changes["avatar"] = data_url
            done.append(f"头像已换成这张图（{len(data_url) // 1024}KB）")

        if not changes:
            raise ValueError(
                "至少要给一个要改的字段：nickname / emoji / avatar_source / temperature。"
            )

        config = runtime.assistants.model_copy(deep=True)
        config.upsert(profile.model_copy(update=changes))
        runtime.save_assistants(config)
        await runtime.audit.op(
            kind="assistant",
            action="update",
            actor_id=actor_id,
            target=assistant_id,
            detail="AI 修改搭子档案：" + "、".join(done),
        )
        
        runtime.events.publish("assistants_changed", assistant_id=assistant_id, action="update")

        saved = runtime.assistants.get(assistant_id)
        return {
            "id": assistant_id,
            "changed": done,
            "nickname": saved.nickname if saved else "",
            "emoji": saved.emoji if saved else "",
            "temperature": saved.temperature if saved else None,
            "has_avatar": bool(saved.avatar) if saved else False,
        }

    async def delete_assistant(
        self, *, assistant_id: str, actor_id: str | None = None
    ) -> dict[str, Any]:














        runtime = self._runtime
        try:
            report = lifecycle.delete_assistant(runtime, assistant_id)
        except KeyError:
            raise ValueError(
                f"搭子「{assistant_id}」不存在。要看现有清单请先调 team_list_assistants。"
            ) from None
        message = lifecycle.describe_report(report)
        await runtime.audit.op(
            kind="assistant",
            action="delete",
            actor_id=actor_id,
            target=assistant_id,
            detail=message,
        )
        
        
        return {**report, "message": message}

    async def ensure_required_skills(
        self,
        *,
        assistant_ids: list[str],
        actor_id: str | None = None,
    ) -> dict[str, Any]:







        from ..assistants.persona import write_file

        runtime = self._runtime
        
        
        
        known = known_skill_names(runtime)
        results: list[dict[str, Any]] = []
        for assistant_id in assistant_ids:
            profile = runtime.assistants.get(assistant_id)
            if profile is None:
                results.append({"id": assistant_id, "error": "搭子不存在"})
                continue
            
            
            
            
            
            if locked_builtins.is_locked(profile.id):
                results.append(
                    {
                        "id": assistant_id,
                        "name": profile.nickname or profile.name,
                        "skipped": True,
                        "error": locked_builtins.locked_persona_message(RULES_FILE),
                    }
                )
                continue
            is_analysis = profile.group_role in ("coordinator", "advisor") or any(
                keyword in (profile.description or "")
                for keyword in ("策划", "规划", "分析", "策略", "咨询", "顾问")
            )
            is_coordinator = profile.group_role == "coordinator"
            required: list[str] = ["self_growth"]
            if is_analysis:
                required.append("ai_thinking_mode")
            if is_coordinator:
                required.append("team_restructure")

            added: list[str] = []
            current = list(profile.enabled_skills)
            
            
            
            
            
            if current:
                for name in required:
                    if name in known and name not in current:
                        current.append(name)
                        added.append(name)
                updated = profile.model_copy(update={"enabled_skills": current})
                config = runtime.assistants.model_copy(deep=True)
                config.upsert(updated)
                runtime.save_assistants(config)

            imposed: list[str] = []
            if is_analysis:
                imposed.append(_THINKING_RULE)
            if is_coordinator:
                imposed.append(_RESTRUCTURE_RULE)
            appended_rules: list[str] = []
            if imposed:
                try:
                    current_rules = read_file(runtime.paths, profile.id, RULES_FILE)
                except (OSError, ValueError):
                    current_rules = ""
                merged = _merge_rules(current_rules, imposed)
                if merged != current_rules:
                    try:
                        write_file(runtime.paths, profile.id, RULES_FILE, merged)
                        appended_rules = imposed
                    except ValueError as exc:
                        results.append({"id": assistant_id, "error": f"规则写失败：{exc}"})
                        continue

            results.append(
                {
                    "id": assistant_id,
                    "name": profile.nickname or profile.name,
                    "required_skills": required,
                    "added_skills": added,
                    "imposed_rules": appended_rules,
                }
            )

        if any(item.get("added_skills") or item.get("imposed_rules") for item in results):
            await runtime.audit.op(
                kind="assistant",
                action="update",
                actor_id=actor_id,
                target=",".join(assistant_ids),
                detail=f"系统统一补装必装技能/规则（{len(results)} 个搭子）",
            )
            runtime.events.publish("assistants_changed", action="update")
        return {"ok": True, "assistants": results}

    def _write_setup_files(
        self, assistant_id: str, name: str, documents: dict[str, str]
    ) -> tuple[list[str], list[str]]:





        from ..assistants.persona import write_file

        written: list[str] = []
        failed: list[str] = []
        for file_name, content in documents.items():
            try:
                write_file(self._runtime.paths, assistant_id, file_name, content)
                written.append(file_name)
            except (OSError, ValueError) as exc:
                logger.warning("写入搭子设定失败 %s/%s: %s", assistant_id, file_name, exc)
                failed.append(f"{file_name}: {exc}")
        return written, failed

    async def create_group(
        self,
        *,
        name: str,
        member_ids: list[str],
        coordinator_id: str = "",
        speaking_order: list[str] | None = None,
        actor_id: str | None = None,
        from_import: bool = False,
    ) -> dict[str, Any]:















        runtime = self._runtime
        from ..skill.package import slugify

        self._ensure_library_checked(from_import)

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("群得有个名字。")

        members: list[str] = []
        missing: list[str] = []
        for member_id in member_ids:
            if runtime.assistants.get(member_id) is None:
                missing.append(member_id)
            elif member_id not in members:
                members.append(member_id)
        if len(members) < 2:
            raise ValueError(
                "一个群至少要两个搭子才讨论得起来。"
                f"（收到 {len(member_ids)} 个成员，其中可用 {len(members)} 个；"
                "搭子 id 请用 list_assistants 的结果，不要自己编。）"
            )

        
        if coordinator_id and not coordinator_id.strip():
            raise ValueError(
                "群总管不能是空白 id：给一个真实搭子的 id，或者（只有用户手建群那种场景）"
                "整个字段留空。"
            )
        coordinator = coordinator_id.strip()
        if coordinator and coordinator not in members:
            if actor_id and coordinator == actor_id:
                raise ValueError(
                    "你说自己是这个群的总管，但成员名单里没有你。要自己当总管就把"
                    f"**你自己也写进 member_ids**（现在群里只有"
                    f"{'、'.join(self._display_name(item) for item in members)}）。"
                    "自称总管却不在群里，用户看到的分工就是假的。"
                )
            raise ValueError(
                f"指名的群总管「{coordinator}」不在成员名单里（id 要用 list_assistants 的结果）："
                "总管必须是这次一起拉进群的人之一。"
            )
        if coordinator:
            
            
            
            target = runtime.assistants.get(coordinator)
            current_role = (target.group_role or "").strip() if target is not None else ""
            if current_role and current_role != "coordinator":
                raise ValueError(
                    f"「{self._display_name(coordinator)}」现在的角色是"
                    f"「{_ROLE_NAMES.get(current_role, current_role)}」，不能同时当这个群的"
                    "总管（一个人的角色不能这样顶掉）。换一个成员当总管。"
                )

        group = GroupProfile(
            id=f"{slugify(clean_name, fallback='group')}-{uuid.uuid4().hex[:6]}",
            name=clean_name,
            member_assistant_ids=members,
            speaking_order=[item for item in (speaking_order or []) if item in members],
            coordinator_id=coordinator,
        )
        config = runtime.groups.model_copy(deep=True)
        config.upsert(group)
        runtime.groups = runtime.config_store.save_groups(config)
        logger.info("AI 新建群 %s（成员 %s，总管 %s）", group.id, members, coordinator or "位次兜底")
        
        runtime.events.publish("groups_changed", group_id=group.id, action="create")

        
        
        if coordinator:
            profile = runtime.assistants.get(coordinator)
            if profile is not None and (profile.group_role or "").strip() != "coordinator":
                assistant_config = runtime.assistants.model_copy(deep=True)
                assistant_config.upsert(profile.model_copy(update={"group_role": "coordinator"}))
                runtime.save_assistants(assistant_config)
                await runtime.audit.op(
                    kind="assistant",
                    action="update",
                    actor_id=actor_id,
                    target=coordinator,
                    detail=f"群角色任命：{self._display_name(coordinator)} → 协调者（总管）",
                )
                runtime.events.publish(
                    "assistants_changed", assistant_id=coordinator, action="update"
                )

        await runtime.audit.op(
            kind="group",
            action="create",
            actor_id=actor_id,
            target=group.id,
            detail=(
                f"AI 新建群「{clean_name}」（成员："
                f"{'、'.join(self._display_name(item) for item in members)}）"
            ),
        )
        result: dict[str, Any] = {
            "id": group.id,
            "name": group.name,
            "members": [
                {"id": item, "name": self._display_name(item)} for item in members
            ],
            
            
            "coordinator": (
                {"id": coordinator, "name": self._display_name(coordinator)}
                if coordinator
                else None
            ),
            
            "existing_assistants": self.list_assistants(),
            
            
            "next_step": (
                (
                    f"这个群的总管是「{self._display_name(coordinator)}」——"
                    "讨论时按这个分工走，别把自己当总管。"
                    if coordinator
                    else "这个群没指定总管，会按发言位次（首位）兜底。"
                )
                + "接着调 team_assign_group_roles 提交这个群的「审核员」与「优化顾问」搭子 id"
                "（没有「不需要」这个选项；有合适的现有搭子就复用，没有就先用 "
                "team_create_assistant 建一个 group_role 为 reviewer / advisor 的）。"
                "没提交之前 team_start_discussion 会被拒绝。"
            ),
        }
        if missing:
            result["ignored_members"] = missing
        if len(members) < len(member_ids):
            result["note"] = "部分成员 id 不存在，已跳过（见 ignored_members）。"
        return result

    
    
    
    
    
    
    
    
    

    def _require_group(self, group_id: str) -> GroupProfile:
        group = self._runtime.groups.get(group_id)
        if group is None:
            raise ValueError(
                f"群「{group_id}」不存在（先用 team_list_assistants 看群清单，"
                "或者 team_create_group 建一个）。"
            )
        return group

    async def _require_thread(self, group_id: str, thread_id: str) -> dict[str, Any]:







        thread = await self._runtime.group_thread_repo.get(group_id, thread_id)
        if thread is None:
            raise ValueError(
                f"群「{group_id}」下没有 id 为「{thread_id}」的对话。"
                "对话 id 必须来自 team_list_assistants 返回的 groups[].threads —— "
                "不要自己编，也不要用别的那条。"
            )
        return thread

    async def create_group_thread(
        self, *, group_id: str, title: str = "", actor_id: str | None = None
    ) -> dict[str, Any]:





        group = self._require_group(group_id)
        thread = await self._runtime.group_thread_repo.create(group.id, title)
        await self._runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group.id,
            detail=f"新建群对话「{thread['title']}」（群「{group.name}」）",
        )
        self._notify_threads_changed(group.id)
        return {
            "group": {"id": group.id, "name": group.name},
            "thread": thread,
            "message": (
                f"已在群「{group.name}」里新建对话「{thread['title']}」"
                f"（thread_id={thread['id']}）。**它现在是空的** —— "
                "话题要接着抛给它才行（用 team_start_discussion 时把 group_id 传这个群）。"
            ),
        }

    async def rename_group_thread(
        self, *, group_id: str, thread_id: str, title: str, actor_id: str | None = None
    ) -> dict[str, Any]:

        group = self._require_group(group_id)
        thread = await self._require_thread(group.id, thread_id)
        clean = title.strip()
        if not clean:
            raise ValueError("对话名字不能为空 —— 空名字在列表里是一条说不清是什么的记录。")
        if clean == thread["title"]:
            
            return {"thread": thread, "message": f"「{clean}」本来就是它的名字，没有改动。"}
        renamed = await self._runtime.group_thread_repo.rename(group.id, thread["id"], clean)
        if not renamed:
            raise ValueError(f"改名失败：群「{group.name}」下找不到那条对话。")
        await self._runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group.id,
            detail=f"群对话改名：「{thread['title']}」→「{clean}」",
        )
        self._notify_threads_changed(group.id)
        return {
            "group": {"id": group.id, "name": group.name},
            "thread_id": thread["id"],
            "before": thread["title"],
            "after": clean,
            "message": f"已把群「{group.name}」里的对话「{thread['title']}」改名为「{clean}」。",
        }

    async def clear_group_thread(
        self, *, group_id: str, thread_id: str, actor_id: str | None = None
    ) -> dict[str, Any]:





        group = self._require_group(group_id)
        thread = await self._require_thread(group.id, thread_id)
        removed = await self._runtime.group_event_repo.clear(group.id, thread["id"])
        await self._runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group.id,
            detail=f"清空群对话「{thread['title']}」的 {removed} 条记录",
        )
        self._notify_threads_changed(group.id)
        return {
            "group": {"id": group.id, "name": group.name},
            "thread_id": thread["id"],
            "removed": removed,
            "message": (
                f"已清空群「{group.name}」里对话「{thread['title']}」的 {removed} 条记录。"
                "**这条对话还在**，可以接着往下聊。"
            ),
        }

    async def delete_group_thread(
        self, *, group_id: str, thread_id: str, actor_id: str | None = None
    ) -> dict[str, Any]:






        group = self._require_group(group_id)
        thread = await self._require_thread(group.id, thread_id)
        remaining = await self._runtime.group_thread_repo.list_threads(group.id)
        if len(remaining) <= 1:
            raise ValueError(
                f"群「{group.name}」只剩这一条对话了，不能删 —— 删掉之后这个群会是空的。"
                "如果目的是清掉内容，用 team_clear_group_thread（对话还在，可以接着聊）。"
            )
        deleted = await self._runtime.group_thread_repo.delete(group.id, thread["id"])
        if not deleted:
            raise ValueError(f"删除失败：群「{group.name}」下找不到那条对话。")
        await self._runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group.id,
            detail=f"删除群对话「{thread['title']}」",
        )
        self._notify_threads_changed(group.id)
        return {
            "group": {"id": group.id, "name": group.name},
            "thread_id": thread["id"],
            "deleted_title": thread["title"],
            "remaining": len(remaining) - 1,
            "message": (
                f"已删除群「{group.name}」里的对话「{thread['title']}」（连带它的记录，"
                f"无法恢复）。该群还剩 {len(remaining) - 1} 条对话。"
            ),
        }

    def _notify_threads_changed(self, group_id: str) -> None:







        self._runtime.events.publish("group_threads_changed", group_id=group_id)

    
    
    
    def _roles_gap(self, group: GroupProfile) -> str:





        runtime = self._runtime
        for role, label in (("reviewer", "审核员"), ("advisor", "优化顾问")):
            assistant_id = self._confirmed_role(group, role)
            if not assistant_id:
                return f"还没提交{label}的搭子 id"
            if assistant_id not in group.member_assistant_ids:
                return f"已确认的{label}「{self._display_name(assistant_id)}」已经不在群里了"
            if runtime.assistants.get(assistant_id) is None:
                return f"已确认的{label}「{assistant_id}」已经被删掉了"
        return ""

    @staticmethod
    def _confirmed_role(group: GroupProfile, role: str) -> str:

        value = group.reviewer_id if role == "reviewer" else group.advisor_id
        return (value or "").strip()

    async def assign_group_roles(
        self,
        *,
        group_id: str,
        reviewer_id: str,
        advisor_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:










        runtime = self._runtime
        group = runtime.groups.get(group_id)
        if group is None:
            raise ValueError(
                f"群「{group_id}」不存在（先用 team_list_assistants 看群清单，"
                "或者 team_create_group 建一个）。"
            )

        reviewer = reviewer_id.strip()
        advisor = advisor_id.strip()
        if not reviewer or not advisor:
            raise ValueError(
                "审核员与优化顾问都要给 id —— 这一步没有「不需要」："
                "确实没有合适的现有搭子时，先用 team_create_assistant 建一个"
                "（group_role 分别填 reviewer / advisor，并在规则里写清这个任务怎么算达标），"
                "再把它们的 id 提交上来。"
            )
        if reviewer == advisor:
            raise ValueError(
                "审核员和优化顾问不能是同一个搭子：一个按标准验收、一个提必要建议，"
                "分开才互相把关。请各指一个。"
            )
        
        if reviewer == self._confirmed_role(group, "advisor") or advisor == self._confirmed_role(
            group, "reviewer"
        ):
            raise ValueError("同一个搭子不能同时担任审核员与优化顾问，请各指一个。")

        members = list(group.member_assistant_ids)
        added: list[str] = []
        roles: dict[str, dict[str, Any]] = {}
        for role, assistant_id in (("reviewer", reviewer), ("advisor", advisor)):
            label = _ROLE_NAMES[role]
            profile = runtime.assistants.get(assistant_id)
            if profile is None:
                raise ValueError(
                    f"搭子「{assistant_id}」不存在 —— id 必须来自 team_list_assistants 的结果，"
                    "不要自己编。"
                )
            current = (profile.group_role or "").strip()
            if current and current != role:
                raise ValueError(
                    f"「{profile.nickname or profile.name}」现在的角色是"
                    f"「{_ROLE_NAMES.get(current, current)}」，不能再当{label}"
                    "（一个人的角色不能这样顶掉）。请另外指一个搭子。"
                )
            if assistant_id not in members:
                
                
                members.append(assistant_id)
                added.append(assistant_id)
            roles[role] = {
                "id": assistant_id,
                "name": profile.nickname or profile.name,
                "role_written": current == role,
            }

        order = [item for item in group.speaking_order if item in members]
        order += [item for item in members if item not in order]
        updated = group.model_copy(
            update={
                "member_assistant_ids": members,
                "speaking_order": order,
                "reviewer_id": reviewer,
                "advisor_id": advisor,
            }
        )
        config = runtime.groups.model_copy(deep=True)
        config.upsert(updated)
        runtime.groups = runtime.config_store.save_groups(config)
        runtime.events.publish("groups_changed", group_id=group.id, action="update")

        
        
        appointed: list[str] = []
        for role in ("reviewer", "advisor"):
            assistant_id = roles[role]["id"]
            profile = runtime.assistants.get(assistant_id)
            if profile is None or (profile.group_role or "").strip() == role:
                continue
            assistant_config = runtime.assistants.model_copy(deep=True)
            assistant_config.upsert(profile.model_copy(update={"group_role": role}))
            runtime.save_assistants(assistant_config)
            await runtime.audit.op(
                kind="assistant",
                action="update",
                actor_id=actor_id,
                target=assistant_id,
                detail=f"群角色任命：{profile.nickname or profile.name} → {_ROLE_NAMES[role]}",
            )
            runtime.events.publish("assistants_changed", assistant_id=assistant_id, action="update")
            appointed.append(assistant_id)

        await runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group.id,
            detail=(
                f"确认群角色「{group.name}」：审核员={roles['reviewer']['name']}、"
                f"优化顾问={roles['advisor']['name']}"
                + (
                    "；顺带拉进群：" + "、".join(self._display_name(item) for item in added)
                    if added
                    else ""
                )
            ),
        )
        result: dict[str, Any] = {
            "id": group.id,
            "name": group.name,
            "roles": roles,
            "members": [{"id": item, "name": self._display_name(item)} for item in members],
            "roles_ready": True,
            "next_step": "角色已配齐，现在可以用 team_start_discussion 把话题抛进去。",
        }
        if added:
            result["added_members"] = [
                {"id": item, "name": self._display_name(item)} for item in added
            ]
        if appointed:
            result["role_written_to_profile"] = appointed
        return result

    async def update_group(
        self,
        *,
        group_id: str,
        name: str = "",
        add_member_ids: list[str] | None = None,
        remove_member_ids: list[str] | None = None,
        speaking_order: list[str] | None = None,
        avatar_source: str = "",
        clear_avatar: bool = False,
        actor_id: str | None = None,
    ) -> dict[str, Any]:






        runtime = self._runtime
        existing = runtime.groups.get(group_id)
        if existing is None:
            raise ValueError(f"群「{group_id}」不存在（先用 team_list_assistants 看群清单）。")

        members = list(existing.member_assistant_ids)
        added: list[str] = []
        dropped: list[str] = []
        missing: list[str] = []
        for assistant_id in add_member_ids or []:
            if runtime.assistants.get(assistant_id) is None:
                missing.append(assistant_id)
                continue
            if assistant_id not in members:
                members.append(assistant_id)
                added.append(assistant_id)
        for assistant_id in remove_member_ids or []:
            if assistant_id in members:
                members.remove(assistant_id)
                dropped.append(assistant_id)
            else:
                missing.append(assistant_id)
        if len(members) < 2:
            raise ValueError(
                "一个群至少要两个搭子才讨论得起来"
                f"（按你要的改动，群里只剩 {len(members)} 个了，已拒绝这次修改）。"
            )

        order = [item for item in existing.speaking_order if item in members]
        order += [item for item in members if item not in order]
        if speaking_order:
            picked = [item for item in speaking_order if item in members]
            order = picked + [item for item in order if item not in picked]

        
        
        kept_roles: dict[str, str] = {}
        cleared: list[str] = []
        for role, label in (("reviewer", "审核员"), ("advisor", "优化顾问")):
            confirmed = self._confirmed_role(existing, role)
            if confirmed and confirmed not in members:
                cleared.append(label)
                kept_roles[f"{role}_id"] = ""
            else:
                kept_roles[f"{role}_id"] = (
                    existing.reviewer_id if role == "reviewer" else existing.advisor_id
                )

        
        coordinator_kept = (existing.coordinator_id or "").strip()
        if coordinator_kept and coordinator_kept not in members:
            cleared.append("总管")
            coordinator_kept = ""

        
        
        
        avatar = existing.avatar
        avatar_note = ""
        if clear_avatar:
            avatar = ""
            avatar_note = "换头像（交给系统重新分配）"
        elif avatar_source.strip():
            try:
                _, avatar = await images.to_data_url(
                    avatar_source, max_bytes=AVATAR_MAX_BYTES, workspace=runtime.workspace
                )
            except images.ImageSourceError as exc:
                raise ValueError(f"设置群头像失败：{exc}") from exc
            
            avatar_note = f"换头像（{len(avatar) // 1024}KB）"

        group = existing.model_copy(
            update={
                "name": name.strip() or existing.name,
                "member_assistant_ids": members,
                "speaking_order": order,
                "coordinator_id": coordinator_kept,
                "avatar": avatar,
                **kept_roles,
            }
        )
        config = runtime.groups.model_copy(deep=True)
        config.upsert(group)
        runtime.groups = runtime.config_store.save_groups(config)
        runtime.events.publish("groups_changed", group_id=group.id, action="update")
        await runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group_id,
            detail=(
                f"AI 调整群「{group.name}」："
                + "、".join(
                    item
                    for item in (
                        "改名" if name.strip() and name.strip() != existing.name else "",
                        f"加人（{'、'.join(self._display_name(i) for i in added)}）" if added else "",
                        f"减人（{'、'.join(self._display_name(i) for i in dropped)}）" if dropped else "",
                        "调整发言顺序" if speaking_order else "",
                        avatar_note,
                        f"角色失效（{'、'.join(cleared)}，需重新提交 id）" if cleared else "",
                    )
                    if item
                )
                or "提交后无实际变化"
            ),
        )
        result: dict[str, Any] = {
            "id": group.id,
            "name": group.name,
            "members": [
                {"id": item, "name": self._display_name(item)} for item in members
            ],
            "speaking_order": [self._display_name(item) for item in order],
        }
        if added:
            result["added"] = [self._display_name(item) for item in added]
        if dropped:
            result["removed"] = [self._display_name(item) for item in dropped]
        if missing:
            result["ignored_ids"] = missing
        if cleared:
            
            result["roles_cleared"] = cleared
            result["next_step"] = (
                f"被移出群的人里包含已确认的{'、'.join(cleared)}，该角色已作废："
                "开讨论前要用 team_assign_group_roles 重新提交一个 id。"
            )
        return result

    async def set_speaking_order(
        self, *, group_id: str, order: list[str], actor_id: str | None = None
    ) -> dict[str, Any]:

        runtime = self._runtime
        existing = runtime.groups.get(group_id)
        if existing is None:
            raise ValueError(f"群「{group_id}」不存在。")
        members = list(existing.member_assistant_ids)
        cleaned = [item for item in order if item in members]
        rest = [item for item in members if item not in cleaned]
        group = existing.model_copy(update={"speaking_order": cleaned + rest})
        config = runtime.groups.model_copy(deep=True)
        config.upsert(group)
        runtime.groups = runtime.config_store.save_groups(config)
        await runtime.audit.op(
            kind="group",
            action="update",
            actor_id=actor_id,
            target=group_id,
            detail=f"调整发言顺序：{' → '.join(self._display_name(item) for item in cleaned + rest)}",
        )
        return {
            "id": group.id,
            "order": [
                {"id": item, "name": self._display_name(item)} for item in cleaned + rest
            ],
        }

    
    
    
    async def start_discussion(
        self,
        *,
        group_id: str,
        topic: str,
        origin_session_id: str = "",
        origin_assistant_id: str | None = None,
    ) -> dict[str, Any]:




        runtime = self._runtime
        from .group_domain import ordered_members, resolve_thread, restore_history

        group = runtime.groups.get(group_id)
        if group is None:
            raise ValueError(
                f"群「{group_id}」不存在。可以先看一遍现有的群，或者建一个。"
            )
        
        
        
        
        
        
        
        gap = self._roles_gap(group)
        if gap:
            raise ValueError(
                f"「{group.name}」还没配齐「审核员 / 优化顾问」：{gap}。"
                "先用 team_assign_group_roles 把这两个角色的搭子 id 提交上来"
                "（这一步没有「不需要」；没有合适的搭子就先用 team_create_assistant 建一个），"
                "再发起讨论。"
            )
        clean_topic = topic.strip()
        if not clean_topic:
            raise ValueError("得给一个讨论话题，否则搭子们不知道要聊什么。")
        if group_id in self.running:
            raise ValueError(f"「{group.name}」里已经有一场讨论在跑了，等它结束。")
        members = ordered_members(runtime, group)
        if not members:
            raise ValueError(f"群「{group.name}」里没有可用的成员（搭子可能被删掉了）。")

        
        
        
        thread_id = await resolve_thread(runtime, group_id, "")
        
        await restore_history(runtime, group_id, thread_id)

        task = asyncio.create_task(
            self._run(
                group, members, clean_topic, origin_session_id, origin_assistant_id, thread_id
            ),
            name=f"group-discussion-{group_id}",
        )
        self._tasks[group_id] = task
        task.add_done_callback(lambda _task, gid=group_id: self._tasks.pop(gid, None))

        
        runtime.events.publish(
            "group_task_started",
            group_id=group_id,
            group_name=group.name,
            topic=clean_topic,
            session_id=origin_session_id,
        )
        await runtime.audit.op(
            kind="group",
            action="background_start",
            actor_id=origin_assistant_id,
            target=group_id,
            session_id=origin_session_id or None,
            detail=f"在后台发起讨论「{group.name}」：{clean_topic[:120]}",
        )
        return {
            "group_id": group_id,
            "group_name": group.name,
            "topic": clean_topic,
            "members": [item.name for item in members],
            "started": True,
        }

    async def _run(
        self,
        group: GroupProfile,
        members: list[Any],
        topic: str,
        origin_session_id: str,
        origin_assistant_id: str | None,
        thread_id: str,
    ) -> None:

        runtime = self._runtime
        
        
        
        from ..protocol import parse_sse
        from .group_discussion import discussion_source
        from .group_domain import persisting_stream

        summary = ""
        last_speech = ""
        outcome = "done"
        error = ""
        try:
            source = persisting_stream(
                runtime,
                group.id,
                thread_id,
                discussion_source(runtime, group, members, topic, thread_id, background=True),
                background=True,
            )
            async for chunk in source:
                parsed = parse_sse(chunk)
                if parsed is None:
                    continue
                name, data = parsed
                if name == "summary":
                    summary = str(data.get("content") or "")
                elif name == "message":
                    last_speech = str(data.get("content") or "")
                elif name == "done" and str(data.get("reason") or "") == "max_rounds":
                    
                    outcome = "incomplete"
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except Exception as exc:  
            outcome = "failed"
            error = str(exc)[:300]
            logger.exception("后台群讨论失败 group=%s", group.id)
        finally:
            await self._deliver(
                group,
                topic,
                outcome,
                summary or last_speech,
                error,
                origin_session_id,
                origin_assistant_id,
            )

    async def _deliver(
        self,
        group: GroupProfile,
        topic: str,
        outcome: str,
        body: str,
        error: str,
        origin_session_id: str,
        origin_assistant_id: str | None,
    ) -> None:





        runtime = self._runtime
        if outcome == "done":
            head = f"【{group.name}】的讨论有结论了："
        elif outcome == "incomplete":
            head = (
                f"【{group.name}】的讨论聊到安全轮数上限就停了，"
                "没有投票收敛出结论。最后聊到："
            )
        elif outcome == "cancelled":
            head = f"【{group.name}】的讨论被中断了（应用退出或主动停止）。最后聊到："
        else:
            head = f"【{group.name}】的讨论出错了：{error or '原因未知'}。"

        text = head + ("\n\n" + body if body else "\n\n（没有拿到任何发言。）")

        if origin_session_id:
            try:
                session = await runtime.sessions.get(origin_session_id)
                session.memory.add_assistant(text)
                session.touch()
                await runtime.persist_session(session)
            except Exception as exc:  
                logger.warning("群聊结果写回会话失败 session=%s: %s", origin_session_id, exc)

        runtime.events.publish(
            "group_task_done",
            group_id=group.id,
            group_name=group.name,
            topic=topic,
            session_id=origin_session_id,
            outcome=outcome,
            content=text,
        )
        await runtime.audit.op(
            kind="group",
            action="background_done" if outcome == "done" else "background_failed",
            actor_id=origin_assistant_id,
            target=group.id,
            session_id=origin_session_id or None,
            status="ok" if outcome == "done" else "error",
            detail=f"后台讨论结束（{outcome}）：{topic[:80]}" + (f"；{error}" if error else ""),
        )

    async def stop_discussion(self, group_id: str) -> dict[str, Any]:







        task = self._tasks.get(group_id)
        if task is None or task.done():
            return {"group_id": group_id, "stopped": False}
        task.cancel()
        logger.info("已停止群后台讨论 group=%s", group_id)
        return {"group_id": group_id, "stopped": True}

    async def shutdown(self) -> None:




        pending = [task for task in self._tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except (asyncio.CancelledError, Exception):  
                pass
        self._tasks.clear()


def _merge_rules(rules: str, imposed: list[str]) -> str:






    body = rules.strip()
    parts = [body] if body else []
    for clause in imposed:
        if clause not in body:
            parts.append(clause)
    return "\n".join(parts)


def _identity_document(name: str, identity: str, abilities: str) -> str:





    return (
        f"# IDENTITY · {name}\n\n"
        "## 我是谁\n\n"
        f"{identity.strip()}\n\n"
        "## 我能做什么\n\n"
        f"{abilities.strip()}\n"
    )


def _rules_document(name: str, rules: str) -> str:

    return f"# RULES · {name} 的工作规则\n\n{rules.strip()}\n"


def _soul_document(name: str, tone: str, description: str) -> str:






    body = tone.strip() or "语气自然、直接，始终围绕你自己那份职责说话。"
    return f"# SOUL\n\n你是 {name}。{body}\n"
