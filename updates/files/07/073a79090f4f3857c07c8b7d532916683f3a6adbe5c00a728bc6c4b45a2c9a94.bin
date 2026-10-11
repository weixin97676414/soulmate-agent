"""
build_docs.py — 拆解 / 八维报告「一次多格式」文档生成器（v2.22 新增）
========================================================================
由「短视频爆款8维拆解与反向二创」技能在步骤 9.5「文档交付选项」调用。

解决的问题：
  · 用户常要「Word + HTML 都要」（如放资料库多人编辑 + 浏览器速览），逐个跑三次脚本太碎；
  · 八维自分析线（归属②）与拆解二创线（归属①）共用同一套文档出口，避免归属② 只出 PDF。

能力：
  - 一份 Markdown 源 → 一次生成 PDF / HTML / Word 的任意组合（互不依赖，单份失败不影响其它）。
  - 复用既有 `build_pdf.py` / `build_html.py` / `build_docx.py`，不重复实现渲染逻辑。
  - 三格式共用同一份 Markdown 源：封面 + 目录 + 页码逻辑一致，结构完全对齐。
  - 报错统一走 `_friendly_error.py` 友好化层（v2.21 起），普通人能看懂。
  - 汇总回执：一次列出每份文档的 路径 / 大小 / 状态，便于 agent 转述给用户。

用法：
  python scripts/build_docs.py --md <报告.md> --formats pdf,html,docx
  python scripts/build_docs.py --md <报告.md> --formats all            # 三格式全出
  python scripts/build_docs.py --md <报告.md> --formats word,html      # 别名 word=docx
  python scripts/build_docs.py --md <报告.md> --formats docx --out-dir D:/reports

参数：
  --md            输入 Markdown 报告路径（必需）
  --formats       逗号分隔：pdf / html / docx(或 word) / all；默认 all
  --out-dir       输出目录（默认与 --md 同目录）
  --title         封面主题（默认取文件名去扩展名）
  --date          产出日期 YYYY-MM-DD（默认今天）
  --brand         封面打印品牌署名行（含联系方式）；默认不打印
  --yes           透传给子脚本：跳过依赖安装确认（非交互环境用）

退出码（沿用 _friendly_error 语义）：
  0  全部成功
  1  内部错误 / 参数不合法
  2  输入错误（md 不存在 / 格式名不认识）
  3  权限 / 设备异常
  10 部分格式失败（至少一份成功）
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _friendly_error as _fe  # noqa: E402

SKILL_NAME = "短视频爆款8维拆解与二创"

# 格式别名 → (规范名, 子脚本, 扩展名, 依赖说明)
FORMATS = {
    "pdf": ("pdf", "build_pdf.py", ".pdf", "reportlab"),
    "html": ("html", "build_html.py", ".html", "零依赖"),
    "docx": ("docx", "build_docx.py", ".docx", "python-docx"),
    "word": ("docx", "build_docx.py", ".docx", "python-docx"),
}

# 场景选型建议（供 agent 转述给用户，来源：SKILL.md 步骤 9.5 场景选型速查表）
SCENE_HINT = {
    "pdf": "存档 / 打印 / 对外转发（不可编辑）",
    "docx": "资料库入库 / 多人协作编辑 / 二次排版（可编辑，协作首选）",
    "html": "单文件速览 / 内网挂载 / 浏览器打印（零依赖，最轻）",
}


def parse_formats(raw: str) -> list[str]:
    """解析 --formats，返回规范名列表（去重、保序）。"""
    if not raw:
        raise ValueError("没有指定任何格式")
    raw = raw.strip().lower()
    if raw == "all":
        return ["pdf", "html", "docx"]
    out = []
    for token in raw.replace(" ", "").split(","):
        if not token:
            continue
        if token not in FORMATS:
            raise ValueError(
                "不认识的格式「%s」。可用：pdf / html / docx(word) / all" % token
            )
        name = FORMATS[token][0]
        if name not in out:
            out.append(name)
    if not out:
        raise ValueError("没有指定任何格式")
    return out


def build_one(md_path: str, fmt: str, out_path: str, title: str,
              date_str: str, brand: bool, yes: bool) -> tuple[bool, str]:
    """生成单份文档，返回 (是否成功, 说明)。"""
    _, script, _ext, dep = FORMATS[fmt]
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script)
    cmd = [sys.executable, script_path, "--md", md_path, "--out", out_path,
           "--title", title, "--date", date_str]
    if brand:
        cmd.append("--brand")
    # --yes 是「跳过依赖安装确认」开关，只对需要装依赖的子脚本透传。
    # build_html.py 纯标准库零依赖，不认该参数，透传会直接 argparse 报错退出（v2.23 修复）。
    if yes and dep != "零依赖":
        cmd.append("--yes")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    except Exception as e:
        return False, _fe.humanize(e, context="生成 %s" % fmt.upper(), show_tech=True)
    if proc.returncode == 0:
        size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
        return True, "%.1f KB" % (size / 1024)
    # 子脚本失败：把它的 stderr（已是友好化文案）透出来
    detail = (proc.stderr or proc.stdout or "").strip()
    if not detail:
        detail = "子脚本 %s 退出码 %d" % (script, proc.returncode)
    if len(detail) > 600:
        detail = detail[:597] + "..."
    return False, detail


def main() -> int:
    ap = argparse.ArgumentParser(
        description="拆解 / 八维报告一次生成多种格式文档（PDF / HTML / Word）")
    ap.add_argument("--md", required=True, help="输入 Markdown 报告路径")
    ap.add_argument("--formats", default="all",
                    help="逗号分隔：pdf / html / docx(word) / all；默认 all")
    ap.add_argument("--out-dir", default=None, help="输出目录（默认与 --md 同目录）")
    ap.add_argument("--title", default=None, help="封面主题（默认取文件名）")
    ap.add_argument("--date", default=None, help="产出日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--brand", action="store_true",
                    help="封面打印品牌署名行（含联系方式）；默认不打印")
    ap.add_argument("--yes", action="store_true",
                    help="透传给子脚本：跳过依赖安装确认（非交互环境用）")
    args = ap.parse_args()

    md_path = os.path.abspath(args.md)
    if not os.path.exists(md_path):
        _fe.print_error(
            FileNotFoundError(md_path),
            context="生成文档",
            hints=[
                "确认 --md 指向已落盘的 .md 报告",
                "如使用相对路径，确认当前命令行工作目录",
                "路径含空格或中文时建议加引号",
            ],
        )
        return _fe.EXIT_USER

    try:
        fmts = parse_formats(args.formats)
    except ValueError as e:
        _fe.print_error(e, context="解析 --formats", hints=[
            "可用值：pdf、html、docx（或 word）、all",
            "多个用英文逗号分隔，如：--formats pdf,docx",
        ], show_tech=False)
        return _fe.EXIT_USER

    out_dir = os.path.abspath(args.out_dir) if args.out_dir else os.path.dirname(md_path)
    if out_dir and not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            _fe.print_error(e, context="创建输出目录", hints=[
                "确认目标盘有写入权限",
                "路径不要太长（Windows 上限 260 字符）",
            ])
            return _fe.EXIT_PERMISSION

    stem = os.path.splitext(os.path.basename(md_path))[0]
    title = args.title or stem
    date_str = args.date or date.today().strftime("%Y-%m-%d")

    sys.stdout.write("📄 开始生成 %d 份文档（源：%s）\n" % (len(fmts), os.path.basename(md_path)))
    sys.stdout.write("   输出目录：%s\n" % out_dir)
    sys.stdout.write("   场景建议：%s\n\n" % "；".join(
        "%s=%s" % (f.upper(), SCENE_HINT[f]) for f in fmts))

    ok_list, fail_list = [], []
    for fmt in fmts:
        _, _script, ext, _dep = FORMATS[fmt]
        out_path = os.path.join(out_dir, stem + ext)
        sys.stdout.write("  → [%s] %s ... " % (fmt.upper(), os.path.basename(out_path)), )
        sys.stdout.flush()
        ok, info = build_one(md_path, fmt, out_path, title, date_str, args.brand, args.yes)
        if ok:
            ok_list.append((fmt, out_path, info))
            sys.stdout.write("✅ %s\n" % info)
        else:
            fail_list.append((fmt, out_path, info))
            sys.stdout.write("❌ 失败\n")

    sys.stdout.write("\n" + "=" * 56 + "\n")
    sys.stdout.write("📊 汇总：成功 %d / 失败 %d / 共 %d\n\n" %
                     (len(ok_list), len(fail_list), len(fmts)))
    for fmt, path, info in ok_list:
        sys.stdout.write("  ✅ %-5s %s （%s）\n" % (fmt.upper(), path, info))
    for fmt, path, info in fail_list:
        sys.stdout.write("\n  ❌ %-5s %s\n" % (fmt.upper(), path))
        for line in info.splitlines():
            sys.stdout.write("       %s\n" % line)

    if fail_list and not ok_list:
        sys.stdout.write("\n💡 全部失败：按上面每份的「怎么办」逐条处理后重跑。\n")
        return _fe.EXIT_INTERNAL
    if fail_list:
        sys.stdout.write(
            "\n💡 部分失败：其余 %d 份已正常生成，可先交付；"
            "失败项按上面提示处理后再单独补跑（--formats <失败格式>）。\n" % len(ok_list))
        return 10
    sys.stdout.write("\n✅ 全部生成完成。\n")
    return 0


def _check_isolated_venv():
    """拒绝在系统 Python 中执行，强制要求隔离 venv。"""
    if sys.prefix == sys.base_prefix:
        sys.stderr.write(
            "⛔ 必须在隔离 venv 内运行（拒绝系统 Python）。\n"
            "请使用：python\n"
        )
        raise SystemExit(4)


if __name__ == "__main__":
    _check_isolated_venv()
    raise SystemExit(main())
