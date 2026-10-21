#!/usr/bin/env python3





from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

TYPE_ALIASES = {
    "asmr": "短视频手艺展示", "手艺": "短视频手艺展示", "布线": "短视频手艺展示",
    "监控": "短视频手艺展示", "收纳": "短视频手艺展示",
    "talk": "口播观点", "干货": "口播观点", "观点": "口播观点",
    "brand": "品牌故事", "企业": "品牌故事", "叙事": "品牌故事",
    "doc": "人物纪录", "访谈": "人物纪录", "人物": "人物纪录",
    "mix": "热点混剪", "混剪": "热点混剪", "盘点": "热点混剪",
    "platform": "平台规则", "规则": "平台规则", "查重": "平台规则",
    "general": "通用", "通用": "通用",
}
VALID_TYPES = ["短视频手艺展示", "口播观点", "品牌故事", "人物纪录", "热点混剪", "平台规则", "通用"]


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def normalize_type(value: str) -> str:
    key = value.strip()
    normalized = TYPE_ALIASES.get(key) or TYPE_ALIASES.get(key.lower())
    if not normalized:
        raise SystemExit(f"Unsupported type: {value}. Use one of: {', '.join(VALID_TYPES)}")
    return normalized


def sanitize(value: str) -> str:
    return " ".join(value.replace("\n", " ").replace("\r", " ").split()).strip()


def ensure_accumulated_sections(text: str) -> str:
    if "## Accumulated Lessons" in text:
        return text
    sections = ["", "## Accumulated Lessons", ""]
    for t in VALID_TYPES:
        sections.extend([f"### {t}", ""])
    return text.rstrip() + "\n" + "\n".join(sections)


def append_lesson(path: Path, vtype: str, bullet: str) -> bool:
    text = path.read_text(encoding="utf-8")
    text = ensure_accumulated_sections(text)
    if bullet in text:
        return False
    heading = f"### {vtype}"
    idx = text.find(heading)
    if idx == -1:
        marker = "## Accumulated Lessons"
        marker_idx = text.find(marker)
        if marker_idx == -1:
            text = ensure_accumulated_sections(text)
            idx = text.find(heading)
        else:
            insert_at = marker_idx + len(marker)
            text = text[:insert_at] + f"\n\n{heading}\n" + text[insert_at:]
            idx = text.find(heading)
    next_idx = text.find("\n### ", idx + len(heading))
    insert_at = len(text) if next_idx == -1 else next_idx
    prefix = text[:insert_at].rstrip()
    suffix = text[insert_at:]
    updated = prefix + "\n" + bullet + "\n" + suffix
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Record reusable dissect lesson")
    parser.add_argument("--type", required=True, help="asmr/口播观点/品牌故事/人物纪录/热点混剪/平台规则/通用")
    parser.add_argument("--lesson", required=True, help="Reusable lesson learned")
    parser.add_argument("--evidence", default="", help="Observed evidence or failure context")
    parser.add_argument("--action", default="", help="Recommended next-time action")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--file", default="", help="Override target markdown file")
    args = parser.parse_args()

    vtype = normalize_type(args.type)
    target = Path(args.file).expanduser() if args.file else skill_root() / "references" / "dissect-lessons.md"
    if not target.exists():
        raise SystemExit(f"Target file not found: {target}")

    parts = [f"- {sanitize(args.date)} / 类型: {vtype} / lesson: {sanitize(args.lesson)}"]
    if args.evidence:
        parts.append(f"evidence: {sanitize(args.evidence)}")
    if args.action:
        parts.append(f"action: {sanitize(args.action)}")
    bullet = " / ".join(parts)

    changed = append_lesson(target, vtype, bullet)
    status = "appended" if changed else "duplicate-skipped"
    print(f"{status}: {target} -> {vtype}: {bullet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
