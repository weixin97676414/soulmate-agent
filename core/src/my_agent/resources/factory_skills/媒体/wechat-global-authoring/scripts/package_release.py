#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="Build a manual/authorized WeChat delivery package.")
    parser.add_argument("project")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()
    root = Path(args.project)
    out = Path(args.output) if args.output else root / "06_delivery" / "release"
    out.mkdir(parents=True, exist_ok=True)
    for rel in ["project.json", "03_writing", "04_visuals", "05_layout", "07_quality"]:
        src = root / rel
        dst = out / src.name
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    payload = {
        "project": root.name,
        "status": "ready-for-manual-or-authorized-publish",
        "generated_files": sorted(p.name for p in out.iterdir()),
    }
    (out / "delivery-manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out.resolve())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
