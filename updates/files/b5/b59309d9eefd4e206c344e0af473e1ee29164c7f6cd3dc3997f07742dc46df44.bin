#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from pathlib import Path

SECRET_PATTERNS = [
    re.compile(r"(?:api[_-]?key|appsecret|access[_-]?token|bearer)\s*[:=]\s*[^\s\"']+", re.I),
    re.compile(r"(?:cookie|session[_-]?token)\s*[:=]\s*[^\s\"']+", re.I),
]
EXPECTED = ["00_brief", "01_sources", "02_facts", "03_writing", "04_visuals", "05_layout", "06_delivery", "07_quality", "project.json"]

def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a content project.")
    parser.add_argument("project")
    args = parser.parse_args()
    root = Path(args.project)
    errors, warnings = [], []
    for item in EXPECTED:
        if not (root / item).exists():
            errors.append(f"missing: {item}")
    if (root / "project.json").exists():
        try:
            data = json.loads((root / "project.json").read_text(encoding="utf-8"))
            for key in ["project_id", "title", "stage", "created_at"]:
                if not data.get(key):
                    errors.append(f"project.json missing: {key}")
        except Exception as exc:
            errors.append(f"project.json invalid: {exc}")
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size >= 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                warnings.append(f"possible credential-like text: {path}")
                break
    print(f"PROJECT: {root.resolve()}")
    print(f"ERRORS: {len(errors)}")
    for item in errors: print(f"  - {item}")
    print(f"WARNINGS: {len(warnings)}")
    for item in warnings: print(f"  - {item}")
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
