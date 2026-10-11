"""**出厂技能**：随客户端分发的那几百个技能，首次启动时播种进用户技能目录。

## 它解决什么问题

那批第三方技能是**内容**，不是代码：它们在技能页里、能被勾给搭子。如果只把它们
"导入到开发机"（落进 `%APPDATA%`），打包分发给别人时**一个都不会出现** ——
新用户装完打开，技能页是空的。

所以出厂技能走的是**随包资源**那条路：技能包放在
`core/src/my_agent/resources/factory_skills/<分类>/…`，由
`core/build/agent-core.spec` 收进 PyInstaller 的 ``datas``，随安装包一起发出去，
首启时再播种到用户技能目录。

## 两个不能省的设计（都是踩过的坑）

**① 版本 marker，而不是"每次启动补一遍"。**
技能定义存在 ``custom_skills.json`` 里，用户能在技能页把它删掉。每次启动都补的话，
用户删掉的出厂技能下次开机就自己回来了 —— 本项目在 MCP 播种那里已经踩过这个坑
（见 `config/loader.py` 的注释）。这里的做法照抄 `loader.py::_align_persona_pack`：
标记文件里记着"播过哪个版本"，版本没变就什么都不做。

**② 绕开 `skill/install.py::install_defs`。**
它内部的 ``unique_id`` 会把"已被占用的 id"改名成 ``-2`` 后缀。而用户本机**已经装着
这 254 个同 id 的技能**（开发机就是这种情况），走那条路会当场变成第二套卡、
技能页直接翻倍。出厂播种**以 id 为准 upsert**：id 相同就是同一个技能，更新它。

## 不做什么

- **不写任何搭子的 `enabled_skills`**：播种只管"装进技能库"，要不要勾给某个搭子是
  用户的事。顺手勾上会把首启的提示词撑爆（实测勾 254 个时，光文件清单就占了
  十八万字里的三分之一）。
- **不碰 ``index.json`` 里 ``excluded`` 的技能**（那几条是用户明确不要的，
  理由记在 `scripts/sync_factory_skills.py` 的 ``EXCLUDED_IDS`` 旁边）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..utils import resources
from .install import unpack_for
from .package import bind_script_commands, parse_directory

logger = logging.getLogger(__name__)

#: 标记文件（落在用户数据目录），内容 = 已经播种过的资源版本号。
MARKER_NAME = ".factory-skills-seeded"

#: 资源目录名（与 `scripts/sync_factory_skills.py` 的 `DEST` 必须一致）。
RESOURCE_DIR = "factory_skills"


def resource_root() -> Path:
    """出厂技能资源目录的绝对路径（开发态与打包后都由 `resources_dir()` 决定）。"""
    return Path(resources.resources_dir()) / RESOURCE_DIR


def read_factory_index() -> dict[str, Any] | None:
    """读资源里的 ``index.json``；**没有这份资源时返回 None**。

    ⚠️ 开发态（还没跑同步脚本）、或将来做"精简构建"时都可能没有它 ——
    那**不该让客户端起不来**，安静跳过即可。同理，索引坏了也只是本次不播种，
    不能抛出去把启动流程打断。
    """
    # ⚠️ 走 `resource_root()`（而不是 `resources.read_text(...)`）：两者最终都落在
    # `resources_dir()` 上，但走这一层**才能被测试替换**（monkeypatch `resource_root`）。
    # 这也是 `seed_factory_skills` 读技能目录时用的同一个入口，两边不该有两套路径算法。
    try:
        raw = (resource_root() / "index.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.error("读出厂技能索引失败（本次不播种）：%s", exc)
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("出厂技能索引不是合法 JSON（本次不播种）：%s", exc)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        logger.error("出厂技能索引结构不对（本次不播种）")
        return None
    return data


def seeds_needed(data_dir: Path, version: str) -> bool:
    """这个资源版本播过没有（没播过或读不出标记都算"要播"）。"""
    marker = data_dir / MARKER_NAME
    if not marker.is_file():
        return True
    try:
        return marker.read_text(encoding="utf-8").strip() != version
    except OSError as exc:
        # 读不出来就当没播过：重播一次是幂等的（upsert），比"该播没播"安全
        logger.warning("读出厂技能标记失败（按未播种处理）：%s", exc)
        return True


def write_marker(data_dir: Path, version: str) -> None:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / MARKER_NAME).write_text(f"{version}\n", encoding="utf-8")
    except OSError as exc:
        # 必须让人知道：否则下次启动会再播一遍，用户在两次启动之间删掉的出厂技能会回来
        logger.error("写出厂技能标记失败（下次启动会重新播种一遍）：%s", exc)


def seed_factory_skills(runtime: Any) -> dict[str, Any]:
    """把出厂技能播种进用户技能目录：**每个资源版本只做一次**。

    返回 ``{"seed", "installed", "failed", "version", "reason"}``，给启动日志用。
    """
    index = read_factory_index()
    if index is None:
        return {"seed": False, "installed": 0, "failed": 0, "version": "", "reason": "无索引"}

    version = str(index.get("version") or "")
    data_dir = Path(runtime.paths.data_dir)
    if not seeds_needed(data_dir, version):
        return {"seed": False, "installed": 0, "failed": 0, "version": version, "reason": "已播过"}

    excluded = {str(item) for item in (index.get("excluded") or ())}
    base = resource_root()
    config = runtime.custom_skills
    installed = 0
    missing = 0
    failed = 0

    for entry in index["skills"]:
        if not isinstance(entry, dict):
            continue
        domain = str(entry.get("domain") or "")
        source = base / domain
        if not source.is_dir():
            # ⚠️ **不算 `failed`**（独立核查发现的）。
            # `failed` 会阻止写 marker，而 marker 不写就意味着**每次启动都重播一遍**那 254 个技能 ——
            # 十几秒的开机开销，天天白付。而"资源里少了一个分类目录"是**打包/同步时的配置问题**，
            # 不是运行期偶发故障，重试一万次也不会自己好。
            # 所以只告警（这条日志就是唯一的排查线索）并照常推进到写 marker。
            logger.warning("出厂技能的分类目录不存在（跳过这一类，请检查资源与 index.json）：%s", source)
            missing += 1
            continue
        try:
            # ⚠️ 必须**按分类整体解析**（这正是 `sync_factory_skills.py` 写索引时的口径）。
            # 逐技能目录解析会算出**不一样的 id**：重名技能在整批解析时会被
            # `formats._dedupe_names` 改成 `<父目录名>/<名字>`，逐目录解析永远不触发，
            # 于是同一个技能在两边是两个 id。实测 `营销/copywriting` 与
            # `营销/marketing-playbooks` 里那个 `copywriting` 就是这种情况
            # （整体解析 → `copywriting-copywriting`，与用户机上一致）。
            parsed = parse_directory(source, domain)
        except Exception as exc:  # noqa: BLE001 - 一个分类坏掉不该毁掉整次播种
            logger.error("出厂技能分类「%s」解析失败：%s", domain, exc)
            failed += 1
            continue

        for defn in parsed.defs:
            if defn.id in excluded:
                continue
            try:
                # 以 id 为准 upsert（**不经 unique_id**）：id 相同就是同一个技能，
                # 出厂态覆盖它，而不是另开一张 `-2` 的卡。
                #
                # ⚠️ `domain` 必须在这里补上：`parse_directory` 只看包内、看不到
                # "这个包是从 `营销/` 目录出来的"，分类本来就靠调用方传（与 `install_package`
                # 的 `prepare` 同一个道理）。漏了它，出厂技能在技能页会**没有小分类**，
                # 「通用技能」栏的分类按钮里也会少掉它们。
                defn = defn.model_copy(update={"origin": "factory", "domain": domain})
                summary = unpack_for(runtime, defn, parsed.members.members, "出厂技能")
                if not summary.get("count"):
                    # 没落盘任何文件时也要如实说：这类技能在技能页里点开是空的
                    logger.warning("出厂技能「%s」没有落盘任何文件", defn.id)
                defn = bind_script_commands(defn, runtime.paths.skills_dir / defn.id)
                config.upsert(defn)
                installed += 1
            except Exception as exc:  # noqa: BLE001 - 单条失败继续，其余照装
                logger.error("出厂技能「%s」安装失败：%s", defn.id, exc)
                failed += 1

    if installed:
        # 落盘之后要把**返回值**挂回 runtime：`save_custom_skills` 是 pydantic 写的，
        # 返回的是新对象；不换回去的话，后面 `sync_custom_skills` 注册的还是旧的
        # `runtime.custom_skills`（少掉刚播进去的那批），要等下次重启才生效。
        runtime.custom_skills = runtime.config_store.save_custom_skills(config)
    # 即使一条都没装上也要写标记吗？—— **要**，但只在"没有失败"时写。
    # 有失败就意味着资源或磁盘出了问题，下次启动应该再试一次（重播是幂等的）。
    if not failed:
        write_marker(data_dir, version)
    logger.info(
        "出厂技能播种完成：装 %s 个，缺分类 %s 个，失败 %s 个，资源版本 %s",
        installed,
        missing,
        failed,
        version or "(未标注)",
    )
    return {
        "seed": True,
        "installed": installed,
        "missing": missing,
        "failed": failed,
        "version": version,
        "reason": "",
    }


__all__ = [
    "MARKER_NAME",
    "RESOURCE_DIR",
    "read_factory_index",
    "resource_root",
    "seed_factory_skills",
    "seeds_needed",
    "write_marker",
]
