#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demo 自检：是否真的「开箱即用」

用法:
    python check_demo.py <demo目录|单文件> [--min-comment 0.15] [--type auto|full|single]

检查项（ERROR 必须修完再交付）:
  1. 是否有构建文件 / 运行说明（可运行性）
  2. 依赖版本是否写死（禁止 latest / RELEASE / +）
  3. 注释率是否达标（默认 15%）
  4. 是否有 TODO / FIXME / 占位符
  5. 是否有验证步骤（跑完能观察到什么）
  6. 是否有入口（main / 测试类 / 启动脚本）
"""
import argparse
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules", "target", "build", "dist", ".idea",
             "__pycache__", ".venv", "venv", "out", ".gradle"}
CODE_EXT = {".java", ".kt", ".py", ".js", ".ts", ".go", ".rs", ".rb", ".cs",
            ".scala", ".jsx", ".tsx", ".vue"}
BUILD_FILES = {"pom.xml", "build.gradle", "build.gradle.kts", "package.json",
               "requirements.txt", "pyproject.toml", "go.mod", "Cargo.toml",
               "setup.py", "Makefile", "Dockerfile"}

TODO_PAT = re.compile(r"\b(TODO|FIXME|XXX|HACK|待补充|待实现|此处省略)\b")
FLOATING_VER = re.compile(
    r"""(?:"version"\s*:\s*"(?:latest|\*|next)")              # npm latest/*
        |(?:</?version>\s*(?:RELEASE|LATEST)\s*</version>)     # maven RELEASE
        |(?:\b[\w\.\-]+:[\w\.\-]+:\+)                          # gradle 动态版本 +
        |(?:\b[\w\.\-]+:[\w\.\-]+:latest\.release)
    """, re.X | re.I)
VERIFY_PAT = re.compile(r"(预期|期望|应看到|应返回|验证|运行后|输出应为|expected|"
                        r"assert|控制台.*显示|打印出)", re.I)
RUN_PAT = re.compile(r"(运行|启动|执行|mvn|gradle|npm|python|go run|cargo run|"
                     r"docker|make )", re.I)

COMMENT_LINE = {
    ".java": lambda s: s.strip().startswith(("//", "*", "/*")),
    ".kt": lambda s: s.strip().startswith(("//", "*", "/*")),
    ".js": lambda s: s.strip().startswith(("//", "*", "/*")),
    ".ts": lambda s: s.strip().startswith(("//", "*", "/*")),
    ".jsx": lambda s: s.strip().startswith(("//", "*", "/*")),
    ".tsx": lambda s: s.strip().startswith(("//", "*", "/*")),
    ".go": lambda s: s.strip().startswith("//"),
    ".rs": lambda s: s.strip().startswith("//"),
    ".cs": lambda s: s.strip().startswith(("//", "///", "*")),
    ".scala": lambda s: s.strip().startswith(("//", "*")),
    ".py": lambda s: s.strip().startswith("#"),
    ".rb": lambda s: s.strip().startswith("#"),
    ".vue": lambda s: s.strip().startswith(("//", "*", "<!--")),
}
ENTRY_PAT = {
    ".java": re.compile(r"(public\s+static\s+void\s+main|@Test\b|@SpringBootApplication)"),
    ".py": re.compile(r"(if\s+__name__\s*==|def\s+test_|@app\.(route|get|post))"),
    ".go": re.compile(r"func\s+main\s*\("),
    ".js": re.compile(r"(app\.listen|console\.log|module\.exports|export\s+default)"),
    ".ts": re.compile(r"(app\.listen|console\.log|export\s+default|describe\s*\()"),
}


def collect(path):
    """返回 (代码文件列表, 是否有构建文件, 文档文本, 全部文本)"""
    code_files, docs, all_text, has_build = [], [], [], False
    if os.path.isfile(path):
        code_files = [path] if os.path.splitext(path)[1] in CODE_EXT else []
        all_text.append(open(path, encoding="utf-8", errors="ignore").read())
        return code_files, has_build, "", "\n".join(all_text)

    for root, dirs, fs in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in fs:
            p = os.path.join(root, f)
            ext = os.path.splitext(f)[1].lower()
            if f in BUILD_FILES:
                has_build = True
            if ext in CODE_EXT:
                code_files.append(p)
            if ext in (".md", ".rst", ".txt") or f.lower().startswith("readme"):
                try:
                    docs.append(open(p, encoding="utf-8", errors="ignore").read())
                except Exception:
                    pass
            try:
                if ext in CODE_EXT or ext in (".xml", ".json", ".gradle",
                                              ".yml", ".yaml", ".properties", ".md"):
                    all_text.append(open(p, encoding="utf-8", errors="ignore").read())
            except Exception:
                pass
    return code_files, has_build, "\n".join(docs), "\n".join(all_text)


def check(path, min_comment, dtype):
    errors, warns, infos = [], [], []
    code_files, has_build, docs, blob = collect(path)
    is_single = os.path.isfile(path)

    if not code_files and not has_build:
        errors.append("目录下既无代码文件也无构建文件，无法判定为 Demo")
        return errors, warns, infos

    # 1. 可运行性
    if dtype in ("auto", "full"):
        if has_build:
            infos.append("检测到构建文件")
        elif not is_single:
            errors.append("完整工程缺少构建文件（pom.xml / build.gradle / "
                          "package.json / requirements.txt 等）")
    if is_single and not RUN_PAT.search(docs + blob):
        warns.append("单文件示例缺少运行说明，建议在文件头注释里写明执行命令")

    # 2. 依赖版本写死
    if not is_single:
        bad = FLOATING_VER.findall(blob)
        if bad:
            errors.append(f"存在浮动版本号 {len(bad)} 处（latest/RELEASE/+），"
                          "必须写死版本否则不可复现")
        elif has_build:
            infos.append("依赖版本均为固定值")

    # 3. 注释率
    total = comment = 0
    per_file = []
    for f in code_files:
        ext = os.path.splitext(f)[1].lower()
        pred = COMMENT_LINE.get(ext)
        if not pred:
            continue
        try:
            lines = open(f, encoding="utf-8", errors="ignore").readlines()
        except Exception:
            continue
        n = len([l for l in lines if l.strip()])
        c = len([l for l in lines if l.strip() and pred(l)])
        if n:
            total += n
            comment += c
            per_file.append((os.path.basename(f), c / n))
    if total:
        rate = comment / total
        infos.append(f"注释率 {rate:.0%}（{comment}/{total} 行，门槛 {min_comment:.0%}）")
        if rate < min_comment:
            warns.append(f"注释率 {rate:.0%} 低于门槛，关键 API 调用与配置项应有注释")
        low = [(n, f"{r:.0%}") for n, r in per_file if r < 0.08]
        if low:
            warns.append("注释偏少的文件: " + "、".join(f"{n}({r})" for n, r in low[:4]))
    else:
        warns.append("未统计到代码行")

    # 4. TODO / 占位符
    todos = TODO_PAT.findall(blob)
    if todos:
        errors.append(f"存在未完成的占位标记 {len(todos)} 处: "
                      + "、".join(sorted(set(todos))[:4]))

    # 5. 验证步骤
    if VERIFY_PAT.search(docs + blob):
        infos.append("含验证步骤/预期输出")
    else:
        warns.append("缺少验证步骤——应说明跑完能观察到什么（预期输出/断言/界面变化）")

    # 6. 入口
    has_entry = False
    for f in code_files:
        ext = os.path.splitext(f)[1].lower()
        pat = ENTRY_PAT.get(ext)
        if pat:
            try:
                if pat.search(open(f, encoding="utf-8", errors="ignore").read()):
                    has_entry = True
                    break
            except Exception:
                pass
    if has_entry:
        infos.append("检测到可执行入口（main / 测试 / 启动类）")
    else:
        warns.append("未检测到入口（main 方法 / 测试类 / 启动脚本），无法直接运行验证")

    # 7. 目录/文档
    if not is_single and not docs.strip():
        warns.append("缺少 README/说明文档，建议写明：能跑出什么、怎么跑、怎么改")

    return errors, warns, infos


def main():
    ap = argparse.ArgumentParser(description="Demo 自检")
    ap.add_argument("path", help="demo 目录或单文件")
    ap.add_argument("--min-comment", type=float, default=0.15, help="注释率门槛")
    ap.add_argument("--type", default="auto", choices=["auto", "full", "single"])
    a = ap.parse_args()

    if not os.path.exists(a.path):
        sys.stderr.write(f"[错误] 路径不存在: {a.path}\n")
        sys.exit(1)

    errors, warns, infos = check(a.path, a.min_comment, a.type)
    print("=" * 62)
    print(f"Demo 自检 · {os.path.basename(os.path.abspath(a.path))}")
    print("=" * 62)
    for i in infos:
        print(f"INFO  {i}")
    for w in warns:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print("-" * 62)
    if errors:
        print(f"结论：{len(errors)} 个 ERROR，不符合「开箱即用」，修完再交付。")
        return 1
    print("结论：无 ERROR，可以交付。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
