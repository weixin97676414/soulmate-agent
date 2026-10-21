#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path

SAFE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")

def slug(text: str) -> str:
    value = SAFE.sub("-", text.strip()).strip("-").lower()
    return value[:48] or "content-project"

def main() -> int:
    parser = argparse.ArgumentParser(description="Create a WeChat content project.")
    parser.add_argument("title")
    parser.add_argument("--root", default="projects")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    root = Path(args.root) / f"{slug(args.title)}-{now.strftime('%Y%m%d-%H%M%S')}"
    for name in ["00_brief","01_sources","02_facts","03_writing","04_visuals","05_layout","06_delivery","07_quality"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    project = {
        "project_id": root.name,
        "title": args.title,
        "stage": "brief",
        "created_at": now.isoformat(),
        "source_total": 0,
        "fact_status": "pending",
        "layout_status": "pending",
        "delivery_mode": "manual",
        "assets": [],
        "risks": []
    }
    (root / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "00_brief" / "brief.md").write_text(
        f"# {args.title}\n\n## 目标\n\n## 目标读者\n\n## 核心问题\n\n## 必须包含\n\n## 禁止事项\n", encoding="utf-8"
    )
    print(root.resolve())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
