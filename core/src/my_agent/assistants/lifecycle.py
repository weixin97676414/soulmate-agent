"""搭子生命周期里"带连带影响"的动作 —— 目前只有删除。

## 为什么值得单独一个模块

删掉一个搭子**不是**"从 ``assistants.json`` 划掉一行"。它被三处引用着，漏一处就
会留下谁也解释不清的脏数据：

1. **群成员与群角色**（``member_assistant_ids`` / ``speaking_order`` /
   ``reviewer_id`` / ``advisor_id``）。不清理的话，群里留着一个不存在的成员 ——
   而这个洞要等到**下一次开会讨论**才炸，报错还完全指不到"是因为某天删了个搭子"。
2. **人格目录** ``data/assistants/<id>/``。搭子没了文件还在，用户下次建一个 id
   恰好相同的搭子时会**莫名继承上一份人设**（他会以为新搭子是干净的）。
3. **默认搭子**：删掉的正好是默认位时要把默认位让出去，否则新会话指向空气。

原先只有"设置页的删除按钮"那条路会走到这里，而且它只做了第 3 件。现在「搭子总管」
也要能删搭子，所以抽成**一份实现** —— 两条路各写一遍的话，"设置页删"和"让 AI 删"
迟早会长成两种行为，而用户完全看不出为什么。

⚠️ 删除是**不可逆**的。调用方必须保证用户在动手前点过头（设置页那个确认框、
或总管技能的 ``confirm`` 权限）。
"""

from __future__ import annotations

import logging
import shutil
from typing import Any

from . import locked_builtins, persona

logger = logging.getLogger(__name__)

# 一个群至少要两个搭子（建群时就定下的硬规矩，见 ``Orchestrator.create_group``）。
# 删人之后不足这个数，就把群也删掉：留一个"只有一个人的团队"比删掉更让人困惑，
# 而且它已经无法再开会了（开会要至少两个成员）。
_MIN_GROUP_MEMBERS = 2


def delete_assistant(runtime: Any, assistant_id: str) -> dict[str, Any]:
    """删掉一个搭子，并连带清干净所有引用它的地方。返回"一共动了什么"。

    调用方**必须**把返回值里的事如实报出去 —— "顺手删了你一个群"这种连带影响，
    比"删了那个搭子"本身更需要被说出来。

    搭子不存在时抛 :class:`KeyError`（调用方翻译成 404 / 明确的错误话术）；
    是四位内置搭子之一时抛 :class:`~assistants.locked_builtins.LockedBuiltinError`
    （它是 ``ValueError`` 的子类，调用方的既有兜底能直接接住）。
    """
    config = runtime.assistants.model_copy(deep=True)
    profile = config.get(assistant_id)
    if profile is None:
        raise KeyError(assistant_id)
    # 记名字用于回报：删完之后再也取不到了
    label = profile.nickname or profile.name

    # ⚠️ 内置搭子的删除裁决**必须放在这里**，而不是各自的调用点：删除一共三条路
    # （设置页按钮 / 搭子总管技能 / 群解散时的连带删除），它们都汇到这一个函数。
    # 在调用点各判一次的话，迟早有一条漏掉 —— 而漏掉的那条一旦被走到，
    # 用户就是"内置搭子没了"，且没有任何办法恢复。
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
    # 遍历副本：循环体里可能会把群从 config 里删掉
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
                    # 角色也挂在它身上时一起清：留着一个已删搭子的 id，讨论前的
                    # 闸门会以为"角色已配齐"，然后在轮到它发言时找不到人
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
            # 删不掉**必须留痕**（文件可能被别的进程占着）。人格没删干净的话，
            # 用户下次建一个同 id 的搭子会继承旧人设 —— 到那时谁都不会想到是
            # "今天这个目录没删掉"
            logger.warning("删除搭子人格目录失败 id=%s: %s", assistant_id, exc)

    # 告诉所有窗口"清单变了"。两条删除路径（设置页按钮 / 总管技能）共用这一份，
    # 也就都拿到了实时刷新；少了它，另一个窗口要等手动刷新才看不到这个搭子。
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
    """把返回值写成一句**给用户看**的话（含连带影响，一条都不省）。"""
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
