





















from __future__ import annotations

import logging
import shutil
from typing import Any

from . import locked_builtins, persona

logger = logging.getLogger(__name__)




_MIN_GROUP_MEMBERS = 2


def delete_assistant(runtime: Any, assistant_id: str) -> dict[str, Any]:









    config = runtime.assistants.model_copy(deep=True)
    profile = config.get(assistant_id)
    if profile is None:
        raise KeyError(assistant_id)
    
    label = profile.nickname or profile.name

    
    
    
    
    locked_builtins.ensure_deletable(assistant_id, label)

    config.remove(assistant_id)
    default_moved_to = ""
    if config.default_assistant == assistant_id:
        remaining = config.sorted()
        config.default_assistant = remaining[0].id if remaining else ""
        default_moved_to = config.default_assistant
    runtime.save_assistants(config)

    groups_updated: list[str] = []
    groups_removed: list[str] = []
    groups = runtime.groups.model_copy(deep=True)
    changed = False
    
    for group in list(groups.groups):
        involved = (
            assistant_id in group.member_assistant_ids
            or assistant_id in (group.reviewer_id, group.advisor_id)
        )
        if not involved:
            continue
        members = [item for item in group.member_assistant_ids if item != assistant_id]
        if len(members) < _MIN_GROUP_MEMBERS:
            groups.remove(group.id)
            groups_removed.append(group.name)
            changed = True
            continue
        groups.upsert(
            group.model_copy(
                update={
                    "member_assistant_ids": members,
                    "speaking_order": [
                        item for item in group.speaking_order if item != assistant_id
                    ],
                    
                    
                    "reviewer_id": "" if group.reviewer_id == assistant_id else group.reviewer_id,
                    "advisor_id": "" if group.advisor_id == assistant_id else group.advisor_id,
                }
            )
        )
        groups_updated.append(group.name)
        changed = True
    if changed:
        runtime.groups = runtime.config_store.save_groups(groups)

    persona_removed = False
    directory = persona.assistant_dir(runtime.paths, assistant_id)
    if directory.exists():
        try:
            shutil.rmtree(directory)
            persona_removed = True
        except OSError as exc:
            
            
            
            logger.warning("删除搭子人格目录失败 id=%s: %s", assistant_id, exc)

    
    
    runtime.events.publish("assistants_changed", assistant_id=assistant_id, action="delete")
    if changed:
        runtime.events.publish("groups_changed", group_id="", action="delete")

    return {
        "id": assistant_id,
        "name": label,
        "default_moved_to": default_moved_to,
        "groups_updated": groups_updated,
        "groups_removed": groups_removed,
        "persona_removed": persona_removed,
    }


def describe_report(report: dict[str, Any]) -> str:

    parts = [f"已删除搭子「{report['name']}」"]
    if report["groups_updated"]:
        parts.append(f"从群 {'、'.join(report['groups_updated'])} 里移除了它")
    if report["groups_removed"]:
        parts.append(
            f"群 {'、'.join(report['groups_removed'])} 因成员不足两人而被一并删除"
        )
    if report["default_moved_to"]:
        parts.append("它原本是默认搭子，默认位已移交给清单里的第一位")
    if not report["persona_removed"]:
        parts.append("（人格文件没能删干净，可能被占用）")
    return "；".join(parts) + "。"


__all__ = ["delete_assistant", "describe_report"]
