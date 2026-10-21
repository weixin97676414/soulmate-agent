


































from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..utils import resources
from .install import unpack_for
from .package import bind_script_commands, parse_directory

logger = logging.getLogger(__name__)


MARKER_NAME = ".factory-skills-seeded"


RESOURCE_DIR = "factory_skills"


def resource_root() -> Path:

    return Path(resources.resources_dir()) / RESOURCE_DIR


def read_factory_index() -> dict[str, Any] | None:






    
    
    
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

    marker = data_dir / MARKER_NAME
    if not marker.is_file():
        return True
    try:
        return marker.read_text(encoding="utf-8").strip() != version
    except OSError as exc:
        
        logger.warning("读出厂技能标记失败（按未播种处理）：%s", exc)
        return True


def write_marker(data_dir: Path, version: str) -> None:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / MARKER_NAME).write_text(f"{version}\n", encoding="utf-8")
    except OSError as exc:
        
        logger.error("写出厂技能标记失败（下次启动会重新播种一遍）：%s", exc)


def seed_factory_skills(runtime: Any) -> dict[str, Any]:




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
            
            
            
            
            
            logger.warning("出厂技能的分类目录不存在（跳过这一类，请检查资源与 index.json）：%s", source)
            missing += 1
            continue
        try:
            
            
            
            
            
            
            parsed = parse_directory(source, domain)
        except Exception as exc:  
            logger.error("出厂技能分类「%s」解析失败：%s", domain, exc)
            failed += 1
            continue

        for defn in parsed.defs:
            if defn.id in excluded:
                continue
            try:
                
                
                
                
                
                
                
                defn = defn.model_copy(update={"origin": "factory", "domain": domain})
                summary = unpack_for(runtime, defn, parsed.members.members, "出厂技能")
                if not summary.get("count"):
                    
                    logger.warning("出厂技能「%s」没有落盘任何文件", defn.id)
                defn = bind_script_commands(defn, runtime.paths.skills_dir / defn.id)
                config.upsert(defn)
                installed += 1
            except Exception as exc:  
                logger.error("出厂技能「%s」安装失败：%s", defn.id, exc)
                failed += 1

    if installed:
        
        
        
        runtime.custom_skills = runtime.config_store.save_custom_skills(config)
    
    
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
