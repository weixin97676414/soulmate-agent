#!/usr/bin/env python3
# -*- coding: utf-8 -*-
























import argparse
import json
import os
import sys
import zipfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


SUPPORTED = {
    ".xlsx": "Excel 表格", ".xlsm": "Excel 表格(宏)", ".xls": "Excel 旧格式", ".csv": "CSV 文本",
    ".docx": "Word 文档", ".doc": "Word 旧格式", ".wps": "WPS 文字",
    ".pptx": "PPT 演示", ".ppt": "PPT 旧格式",
    ".pdf": "PDF 文档",
    ".md": "Markdown", ".txt": "纯文本", ".json": "JSON", ".xml": "XML", ".log": "日志",
    ".png": "图片", ".jpg": "图片", ".jpeg": "图片", ".webp": "图片", ".bmp": "图片", ".tiff": "图片",
    ".mp3": "音频", ".wav": "音频", ".m4a": "音频", ".mp4": "视频",
}


OOXML_EXT = {".xlsx", ".xlsm", ".docx", ".pptx"}

LEGACY_EXT = {".xls", ".doc", ".ppt", ".wps"}


def human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def probe(path: str, max_mb: float):

    issues = []
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()

    if not os.path.exists(path):
        return "FAIL", ["文件不存在"], 0
    size = os.path.getsize(path)
    if size == 0:
        return "FAIL", ["文件为空"], 0

    status = "OK"

    if ext not in SUPPORTED:
        status = "FAIL"
        issues.append(f"不支持的格式（{ext or '无扩展名'}），需先转换")
        return status, issues, size

    if not os.access(path, os.R_OK):
        status = "FAIL"
        issues.append("无读取权限")
        return status, issues, size

    limit = max_mb * 1024 * 1024
    if size >= limit:
        status = "WARN" if status == "OK" else status
        issues.append(f"超过 {max_mb}MB（实际 {human(size)}），建议分片或分块读取")

    if ext in OOXML_EXT:
        if not zipfile.is_zipfile(path):
            status = "FAIL"
            issues.append("Office 文件结构损坏（不是有效的 zip 包）")
        else:
            try:
                with zipfile.ZipFile(path) as zf:
                    bad = zf.testzip()
                    if bad:
                        status = "FAIL"
                        issues.append(f"压缩包内损坏：{bad}")
            except zipfile.BadZipFile:
                status = "FAIL"
                issues.append("Office 文件无法打开（BadZipFile）")
    elif ext in LEGACY_EXT:
        issues.append("旧二进制格式，建议另存为 xlsx/docx/pptx 再处理，兼容性更稳")
        status = "WARN" if status == "OK" else status
    elif ext == ".csv":
        try:
            with open(path, "rb") as fh:
                head = fh.read(4096)
            for enc in ("utf-8", "gbk"):
                try:
                    head.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                status = "WARN"
                issues.append("编码无法识别为 UTF-8 或 GBK，可能需要指定编码")
        except OSError as exc:
            status = "FAIL"
            issues.append(f"读取失败：{exc}")

    return status, issues, size


def collect(path: str):
    if os.path.isfile(path):
        return [path]
    files = []
    for root, _dirs, fs in os.walk(path):
        for f in fs:
            if f.startswith("~$") or f == ".DS_Store":
                continue
            files.append(os.path.join(root, f))
    return sorted(files)


def main():
    ap = argparse.ArgumentParser(description="批量文件预检（只读，不修改任何文件）")
    ap.add_argument("path", help="文件或目录路径")
    ap.add_argument("--max-mb", type=float, default=50.0, help="单文件大小告警阈值，默认 50MB")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print(f"[FAIL] 路径不存在：{args.path}", file=sys.stderr)
        return 2

    files = collect(args.path)
    if not files:
        print("[FAIL] 未找到任何文件", file=sys.stderr)
        return 2

    results = []
    for fp in files:
        status, issues, size = probe(fp, args.max_mb)
        results.append({"file": fp, "name": os.path.basename(fp), "status": status,
                        "size": size, "size_h": human(size), "issues": issues})

    n_ok = sum(1 for r in results if r["status"] == "OK")
    n_warn = sum(1 for r in results if r["status"] == "WARN")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")

    if args.json:
        print(json.dumps({"summary": {"total": len(results), "ok": n_ok, "warn": n_warn, "fail": n_fail},
                          "files": results}, ensure_ascii=False, indent=2))
        return 2 if n_fail else (1 if n_warn else 0)

    print("=" * 74)
    print(f"文件预检报告（只读扫描，未修改任何文件）　阈值 {args.max_mb}MB")
    print("=" * 74)
    print(f"{'状态':<7}{'大小':>10}  {'文件'}")
    print("-" * 74)
    for r in results:
        print(f"{r['status']:<7}{r['size_h']:>10}  {r['name']}")
        for it in r["issues"]:
            print(f"{'':<7}{'':>10}  └─ {it}")

    print("-" * 74)
    print(f"合计 {len(results)} 个：通过 {n_ok}　警告 {n_warn}　失败 {n_fail}　"
          f"总大小 {human(sum(r['size'] for r in results))}")

    if n_fail:
        print("\n[FAIL] 存在无法直接处理的文件，请先转换格式或修复后再交给我。")
    elif n_warn:
        print("\n[WARN] 可以处理，但建议先按上面的提示处理一下，避免中途失败。")
    else:
        print("\n[OK] 全部通过，可以开工。")

    return 2 if n_fail else (1 if n_warn else 0)


if __name__ == "__main__":
    sys.exit(main())
