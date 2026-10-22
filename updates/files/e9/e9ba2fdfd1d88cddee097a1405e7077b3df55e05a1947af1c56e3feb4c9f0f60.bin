#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shared/deliverable_mining.py · 时段内交付物挖掘（v1.1）

输入：客户代号 + 时间窗
输出：3 类分桶
  - main: 主交付物（外发给甲方的正式 docx/xlsx/pptx）
  - intermediate: 工作中间产出物（V1/V2/草稿/工作底稿）
  - independent_items: 我方独立完成事项（切片 §3 标"我司独立交付"行）

数据源 4 个：
  1. outputs/{客户}/ 目录下真实 .docx/.xlsx/.pptx（按 mtime 过滤时段）
  2. 切片 frontmatter 字段 `相关产出物` 列表
  3. 切片 §3 行动项跟踪表 "我方角色" 列含 "我司独立交付/联合主导" 的行
  4. outputs/{客户}/_files/ 项目过程文件（如有）

调用：
    from deliverable_mining import scan_deliverables
    result = scan_deliverables(
        project_root="/path/to/project",   # 含 outputs/ 和 memory/ 的根目录
        client_code="甲方B",
        start="2025-11-01",
        end="2025-11-30",
    )
    # result = {"main": [...], "intermediate": [...], "independent_items": [...]}
"""
from __future__ import annotations
import os
import re
import datetime as dt
from pathlib import Path
from typing import Optional


# ============ 文件名分类规则 ============

# 主交付物特征：版本标 "正式版/外发版/定稿"，无 V1/V2/草稿
MAIN_HINTS = ["定稿", "正式版", "外发版", "终稿", "Final", "FINAL"]

# 中间产出物特征：含 V1/V2/草稿/共识稿/工作底稿
INTERMEDIATE_HINTS = ["V1", "V2", "V3", "V4", "草稿", "共识稿", "工作底稿", "讨论稿", "测算"]


def _classify_filename(name: str) -> str:
    """根据文件名特征分桶：main / intermediate / unclassified。"""
    if any(h in name for h in MAIN_HINTS):
        return "main"
    if any(h in name for h in INTERMEDIATE_HINTS):
        return "intermediate"
    # 默认走 unclassified——交给用户审时手动判
    return "unclassified"


# ============ 时段过滤 ============

def _in_window(ts: float, start: str, end: str) -> bool:
    """Unix 时间戳是否落在 [start, end] 之间（含两端）。"""
    s_y, s_m, s_d = (int(x) for x in start.split("-"))
    e_y, e_m, e_d = (int(x) for x in end.split("-"))
    s_ts = dt.datetime(s_y, s_m, s_d, 0, 0, 0).timestamp()
    e_ts = dt.datetime(e_y, e_m, e_d, 23, 59, 59).timestamp()
    return s_ts <= ts <= e_ts


# ============ 1. outputs/ 真实文件扫描 ============

def _scan_outputs_files(outputs_dir: Path, start: str, end: str) -> list:
    """扫描 outputs/{客户}/ 下的 docx/xlsx/pptx，按 mtime 过滤时段。"""
    items = []
    if not outputs_dir.exists():
        return items
    for f in outputs_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".docx", ".xlsx", ".pptx"):
            continue
        # 跳过临时文件
        if f.name.startswith("~$") or f.name.startswith("._"):
            continue
        st = f.stat()
        if not _in_window(st.st_mtime, start, end):
            continue
        mtime_dt = dt.datetime.fromtimestamp(st.st_mtime)
        items.append({
            "filename": f.name,
            "path": str(f),
            "mtime": mtime_dt.strftime("%Y-%m-%d"),
            "size_kb": round(st.st_size / 1024, 1),
            "bucket": _classify_filename(f.name),
            "source": "outputs/真实文件",
        })
    return items


# ============ 2. 切片 frontmatter 相关产出物 ============

_FM_PATTERN = re.compile(r'^---\s*\n(.*?)\n---', re.DOTALL)


def _parse_yaml_frontmatter(text: str) -> dict:
    """简化 yaml frontmatter 解析（不引 pyyaml 也能跑）。"""
    m = _FM_PATTERN.match(text)
    if not m:
        return {}
    try:
        import yaml
        return yaml.safe_load(m.group(1)) or {}
    except ImportError:
        # 兜底：只解析 list[str]
        fm = {}
        current_key = None
        for line in m.group(1).split("\n"):
            if not line.strip(): continue
            if line.startswith("  - "):
                if current_key:
                    fm.setdefault(current_key, []).append(line[4:].strip().strip('"').strip("'"))
            elif ":" in line:
                k, _, v = line.partition(":")
                v = v.strip()
                current_key = k.strip()
                if v:
                    fm[current_key] = v.strip('"').strip("'")
                else:
                    fm[current_key] = []
        return fm


def _scan_slice_deliverables(slices_dir: Path, start: str, end: str) -> list:
    """扫描客户切片的 frontmatter 中的"相关产出物"列表。"""
    items = []
    if not slices_dir.exists():
        return items
    for f in slices_dir.rglob("*.md"):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = _parse_yaml_frontmatter(text)
        if not fm:
            continue
        # 时段过滤——以 frontmatter `日期` 字段为准
        date_str = str(fm.get("日期") or fm.get("date") or "")
        if not date_str or len(date_str) < 7:
            continue
        # 兼容 "2025-11" / "2025-11-15" 两种
        if len(date_str) == 7:
            date_str = date_str + "-15"  # 月度切片用中间日
        try:
            slice_dt = dt.datetime.strptime(date_str[:10], "%Y-%m-%d")
            if not _in_window(slice_dt.timestamp(), start, end):
                continue
        except ValueError:
            continue

        for product in (fm.get("相关产出物") or []):
            if isinstance(product, str) and product.strip():
                items.append({
                    "filename": product,
                    "path": "",   # 来自 frontmatter，无确定路径
                    "mtime": date_str[:10],
                    "size_kb": None,
                    "bucket": _classify_filename(product),
                    "source": f"切片 frontmatter {f.name}",
                })
    return items


# ============ 3. 切片 §3 行动项"我司独立交付"扫描 ============

def _scan_independent_items(slices_dir: Path, start: str, end: str) -> list:
    """扫切片 §3 行动项跟踪表，找"我方角色 = 我司独立交付/联合主导"的行。"""
    items = []
    if not slices_dir.exists():
        return items
    for f in slices_dir.rglob("*.md"):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = _parse_yaml_frontmatter(text)
        date_str = str(fm.get("日期") or fm.get("date") or "")
        if not date_str or len(date_str) < 7:
            continue
        if len(date_str) == 7:
            date_str = date_str + "-15"
        try:
            slice_dt = dt.datetime.strptime(date_str[:10], "%Y-%m-%d")
            if not _in_window(slice_dt.timestamp(), start, end):
                continue
        except ValueError:
            continue

        # 简化：匹配含"我司"+"独立交付"或"主导"的表格行
        for line in text.split("\n"):
            if not line.startswith("|"):
                continue
            if "我司独立交付" in line or "我司联合主导" in line or "我司主导" in line:
                # 拆表格列
                cols = [c.strip() for c in line.split("|") if c.strip()]
                if len(cols) >= 2:
                    items.append({
                        "content": cols[0] if cols else "",
                        "full_row": cols,
                        "slice_path": str(f),
                        "date": date_str[:10],
                        "source": "切片 §3 我方角色列",
                    })
    return items


# ============ 主入口 ============

def scan_deliverables(
    project_root: str,
    client_code: str,
    start: str,
    end: str,
) -> dict:
    """挖掘指定客户 + 时段的交付物清单。

    Args:
        project_root: 项目本地实例根目录（含 outputs/ 和 memory/）
        client_code: 客户代号（如 "甲方B"）
        start: "YYYY-MM-DD"
        end:   "YYYY-MM-DD"

    Returns:
        {
          "main": [...],              # 主交付物
          "intermediate": [...],      # 中间产出物
          "unclassified": [...],      # 文件名未含明显特征——交用户审
          "independent_items": [...], # 我方独立完成事项（非文件类）
          "stats": {
            "outputs_count": N,
            "slice_products_count": M,
            "independent_count": K,
            "after_dedup": ...
          }
        }
    """
    root = Path(project_root)
    outputs_dir = root / "outputs" / client_code
    slices_dir = root / "memory" / "projects" / "clients" / client_code

    outputs_items = _scan_outputs_files(outputs_dir, start, end)
    slice_items = _scan_slice_deliverables(slices_dir, start, end)
    independent_items = _scan_independent_items(slices_dir, start, end)

    # 合并 outputs + slice 文件名，去重（按 filename normalized 去重）
    merged = {}
    for it in outputs_items + slice_items:
        key = re.sub(r'\s+', '', it["filename"]).lower().replace("《", "").replace("》", "")
        # 同名取 outputs（有实存路径）优先
        if key not in merged or it["path"]:
            merged[key] = it

    # 分桶
    result = {"main": [], "intermediate": [], "unclassified": [],
              "independent_items": independent_items,
              "stats": {
                  "outputs_count": len(outputs_items),
                  "slice_products_count": len(slice_items),
                  "independent_count": len(independent_items),
                  "after_dedup": len(merged),
              }}
    for it in merged.values():
        result[it["bucket"]].append(it)

    # 每桶内按 mtime 排序
    for b in ("main", "intermediate", "unclassified"):
        result[b].sort(key=lambda x: x.get("mtime", ""))

    return result


# ============ 格式化输出 ============

def format_as_markdown(result: dict, client_code: str, start: str, end: str) -> str:
    """把 scan_deliverables 的输出格式化为 markdown 清单。"""
    lines = [f"## {client_code} · {start} ~ {end} 交付清单"]
    s = result["stats"]
    lines.append(f"\n> 共扫到 outputs 真实文件 {s['outputs_count']} 份 + 切片产出物字段 {s['slice_products_count']} 项；"
                 f"去重后 {s['after_dedup']} 份；我方独立事项 {s['independent_count']} 条\n")

    if result["main"]:
        lines.append("### §1 主交付物（外发给甲方 · 含 定稿/正式版/终稿/Final 关键字）")
        for it in result["main"]:
            badge = f" [{it['mtime']} · {it['size_kb']} KB]" if it.get("path") else f" [{it['mtime']}]"
            name = it['filename'] if it['filename'].startswith("《") else f"《{it['filename']}》"
            lines.append(f"- {name}{badge} · 来源: {it['source']}")
    else:
        lines.append("### §1 主交付物")
        lines.append('- 暂无（本时段未出"定稿/正式版"类文件）')

    lines.append("")
    if result["intermediate"]:
        lines.append("### §2 工作中间产出物（V1/V2/草稿/工作底稿/测算）")
        for it in result["intermediate"]:
            badge = f" [{it['mtime']} · {it['size_kb']} KB]" if it.get("path") else f" [{it['mtime']}]"
            name = it['filename'] if it['filename'].startswith("《") else f"《{it['filename']}》"
            lines.append(f"- {name}{badge} · 来源: {it['source']}")
    else:
        lines.append("### §2 工作中间产出物")
        lines.append("- 暂无")

    lines.append("")
    if result["unclassified"]:
        lines.append("### §3 待分桶（项目组审时确认归类）")
        for it in result["unclassified"]:
            badge = f" [{it['mtime']} · {it['size_kb']} KB]" if it.get("path") else f" [{it['mtime']}]"
            name = it['filename'] if it['filename'].startswith("《") else f"《{it['filename']}》"
            lines.append(f"- {name}{badge} · 来源: {it['source']}")

    lines.append("")
    if result["independent_items"]:
        lines.append("### §4 我方独立完成事项（来自切片 §3 行动项 · 非文件类）")
        for it in result["independent_items"]:
            content_short = it['content'][:50] if len(it.get('content', '')) > 0 else "(无内容)"
            lines.append(f"- {content_short} · 来源切片：`{Path(it['slice_path']).name}`")
    return "\n".join(lines)


# ============ CLI ============

if __name__ == "__main__":
    import sys
    import argparse
    p = argparse.ArgumentParser(description="交付物挖掘")
    p.add_argument("--root", required=True, help="项目本地实例根目录")
    p.add_argument("--client", required=True, help="客户代号")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = p.parse_args()

    result = scan_deliverables(args.root, args.client, args.start, args.end)
    if args.format == "json":
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_as_markdown(result, args.client, args.start, args.end))
