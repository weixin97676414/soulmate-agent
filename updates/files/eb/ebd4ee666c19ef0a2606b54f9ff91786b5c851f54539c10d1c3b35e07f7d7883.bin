#!/usr/bin/env python3
"""Stitch WeChat compatible cover regions into one 1283x383 image."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError as exc:  # pragma: no cover - environment dependent
    raise SystemExit("缺少 Pillow：请使用带 PIL/Pillow 的 Python 环境运行。") from exc


LEFT_SIZE = (900, 383)
RIGHT_SIZE = (383, 383)
FINAL_SIZE = (1283, 383)


def fit_cover(path: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def stitch(left_path: Path, right_path: Path, output_path: Path) -> None:
    left = fit_cover(left_path, LEFT_SIZE)
    right = fit_cover(right_path, RIGHT_SIZE)
    canvas = Image.new("RGB", FINAL_SIZE, "white")
    canvas.paste(left, (0, 0))
    canvas.paste(right, (LEFT_SIZE[0], 0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    if canvas.size != FINAL_SIZE:
        raise SystemExit(f"输出尺寸错误：{canvas.size}，应为 {FINAL_SIZE}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", help="左侧 900x383 大封面图片")
    parser.add_argument("right", help="右侧 383x383 小封面图片")
    parser.add_argument("--output", required=True, help="输出 1283x383 拼接图")
    args = parser.parse_args()

    stitch(Path(args.left).expanduser().resolve(), Path(args.right).expanduser().resolve(), Path(args.output).expanduser().resolve())
    print(f"已生成：{Path(args.output).expanduser().resolve()}，尺寸：{FINAL_SIZE[0]}x{FINAL_SIZE[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
