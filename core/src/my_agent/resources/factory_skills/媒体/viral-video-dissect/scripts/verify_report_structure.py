








































from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _friendly_error as _fe  


RESULT_START = "=== VSD_REPORT_STRUCTURE_START ==="
RESULT_END = "=== VSD_REPORT_STRUCTURE_END ==="



REQUIRED_SECTIONS = [
    "结论摘要",        
    "运行证据",        
    "ASR",             
    "台账",            
    "拍摄脚本",        
    "语气与表情",      
    "钩子与核心观点",  
    "内容结构框架",    
    "量化评分",        
    "二创方向草案",    
]


EXPECTED_SCORE_COLUMNS = ["维度", "得分", "说明"]


EXPECTED_DIMENSIONS = [
    "钩子强度",
    "信息结构清晰度",
    "情绪曲线",
    "节奏与完播设计",
    "信息密度",
    "互动/转化设计",
    "可复制性",
    "适用赛道与边界",
]


SOFT_CHECK_SCORE_COLUMNS = ["证据"]  
SOFT_CHECK_TABLES = {
    "拍摄脚本": ["镜号", "时间", "景别", "运镜", "画面内容", "台词", "字幕", "BGM", "备注"],
}


def log(msg: str) -> None:
    print(f"[verify_report_structure] {msg}", file=sys.stderr, flush=True)


def emit(payload: dict) -> None:
    print(RESULT_START, flush=True)
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    print(RESULT_END, flush=True)


def _norm(s: str) -> str:







    if not s:
        return ""
    s = s.replace("·", "/").replace("／", "/")
    s = s.lower()
    s = re.sub(r"\s+", "", s)
    return s


def _cell_has(cells: list[str], expected: str) -> bool:

    ne = _norm(expected)
    return any(ne in c for c in cells)


def read_content(src: str) -> "str | None":
    if src == "-":
        try:
            return sys.stdin.read()
        except Exception as e:  
            _fe.print_error(e, context="读取 stdin", hints=[
                "如用 PowerShell 管道，确认上一步命令正常输出",
                "若 .md 文件很大，可直接传文件路径而非 stdin",
            ])
            return None
    p = Path(src).expanduser()
    if not p.exists() or not p.is_file():
        _fe.print_error(
            FileNotFoundError(str(p)),
            context="读取报告",
            hints=[
                "确认 --report / -r 后跟的是 .md 文件路径",
                "如使用相对路径，确认当前命令行工作目录",
                "路径含空格或中文时建议加引号：「\"我的报告.md\"」",
            ],
        )
        return None
    try:
        return p.read_text("utf-8")
    except UnicodeDecodeError as e:
        _fe.print_error(e, context="读取报告（编码异常）", hints=[
            "把 .md 另存为 UTF-8 编码（记事本 → 另存为 → 编码选 UTF-8）",
            "如从 Office / Word 复制，先粘贴到记事本再去格式",
        ])
        return None
    except Exception as e:  
        _fe.print_error(e, context="读取报告")
        return None


def _heading_re() -> re.Pattern:
    
    return re.compile(r"^[^\S\n]*##[^\S\n]+(?P<title>.+?)[^\S\n]*$", re.MULTILINE)


def _find_sections(content: str) -> dict:

    positions = {}
    for m in _heading_re().finditer(content):
        title = m.group("title").strip()
        for key in REQUIRED_SECTIONS:
            if key not in positions and key in title:
                positions[key] = m.start()
    return positions


def _section_block(content: str, start: int) -> str:

    after = content[start:]
    nl = after.find("\n")
    body = after[nl + 1:] if nl != -1 else ""
    m = re.search(r"^[^\S\n]*##[^\S\n]+\S", body, re.MULTILINE)
    if m:
        body = body[: m.start()]
    return body


def _split_table_rows(block: str) -> list[list[str]]:

    rows = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.rstrip().endswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r"[\s:\-]*", c) for c in cells):
            continue
        rows.append(cells)
    return rows


def verify(content: str) -> dict:
    missing_sections = []
    missing_columns = {}
    missing_dimensions = []
    soft_issues = []
    issues = []

    positions = _find_sections(content)

    
    for key in REQUIRED_SECTIONS:
        if key not in positions:
            missing_sections.append(key)

    section_count = len(positions)

    
    if "量化评分" in positions:
        block = _section_block(content, positions["量化评分"])
        rows = _split_table_rows(block)
        if not rows:
            missing_columns["量化评分"] = EXPECTED_SCORE_COLUMNS[:]
            issues.append("「量化评分」节缺少评分表格")
        else:
            header_cells = [_norm(c) for c in rows[0]]
            missing = [
                e for e in EXPECTED_SCORE_COLUMNS
                if not _cell_has(header_cells, e)
            ]
            if missing:
                missing_columns["量化评分"] = missing
                issues.append("「量化评分」表头缺少列：" + "、".join(missing))
            dim_cells = [_norm(r[0]) for r in rows[1:] if r]
            missing_dimensions = [
                d for d in EXPECTED_DIMENSIONS
                if _norm(d) not in set(dim_cells)
            ]
            if missing_dimensions:
                issues.append("8 维评分缺少维度行：" + "、".join(missing_dimensions))
            
            if not any(_cell_has(header_cells, c) for c in SOFT_CHECK_SCORE_COLUMNS):
                soft_issues.append("「量化评分」表头建议补充「证据」列（P1⑤ 目标）")
    elif "量化评分" not in missing_sections:
        pass  

    
    for sec, expected in SOFT_CHECK_TABLES.items():
        if sec not in positions:
            continue
        block = _section_block(content, positions[sec])
        rows = _split_table_rows(block)
        if not rows:
            soft_issues.append(f"「{sec}」节缺少表格（建议补镜头表）")
            continue
        header_cells = [_norm(c) for c in rows[0]]
        missing = [
            e for e in expected
            if not _cell_has(header_cells, e)
        ]
        if missing:
            soft_issues.append(f"「{sec}」表头建议包含列：{'、'.join(missing)}")

    
    for key in REQUIRED_SECTIONS:
        if key not in positions:
            continue
        block = _section_block(content, positions[key]).strip()
        if not block:
            issues.append(f"「{key}」节内容为空")

    ok = not (missing_sections or missing_columns or missing_dimensions or issues)
    
    human_readable = _humanize(missing_sections, missing_columns, missing_dimensions, issues, soft_issues)
    return {
        "ok": ok,
        "section_count": section_count,
        "missing_sections": missing_sections,
        "missing_columns": missing_columns,
        "missing_dimensions": missing_dimensions,
        "soft_issues": soft_issues,
        "issues": issues,
        "human_readable": human_readable,
    }


def _humanize(missing_sections, missing_columns, missing_dimensions, issues, soft_issues) -> dict:

    
    SECTION_GUIDE = {
        "结论摘要": ("开篇 3 行人话结论，普通用户只看摘要就够", "在报告最前面加一段 ## 结论摘要，3 行内说清：① 为啥火 ② 最该偷师的 1 个手法 ③ 给用户的一条建议"),
        "运行证据": ("本次运行的可信度自检（输入/执行/降级/置信度），让用户一眼判断结论是否靠谱", "在 ## 结论摘要 之后加 ## 一、本次运行证据 节，按 输入路径/执行路径/降级原因/依赖齐备度/推测步骤清单/置信度总评 六子项写齐"),
        "ASR": ("语音转写 + 语义校正，反映原片真实口播内容", "加 ## 二、ASR 语义校正 节，给出逐段修正后的口播文本（重点修正同音字、行业词、断句）"),
        "台账": ("画面上的文字（字幕 / 题字 / 商品牌）逐帧整理，便于复用与核查", "加 ## 三、屏幕文字台账 节，用表格列出：时间码 / 画面位置 / 原文 / 含义 / 复用建议"),
        "拍摄脚本": ("基于真实镜头还原原片的拍摄方式，是借鉴与二创的基础", "加 ## 四、拍摄脚本 节，用镜头表：镜号 / 时间 / 景别 / 运镜 / 画面内容 / 台词 / 字幕 / BGM / 备注"),
        "语气与表情": ("把口头禅、表情、节奏这些「表演层」信号显式记录", "加 ## 五、语气与表情分析 节，从逐字稿和抽帧里抓口语标记词（其实/我跟你讲）、表情类型、停顿时长"),
        "钩子与核心观点": ("原片最炸的开头 3 秒 + 全文最值得偷的观点", "加 ## 六、钩子与核心观点 节，前 3 秒逐字稿 + 全文 3–5 个核心金句（含时间码与画面配合）"),
        "内容结构框架": ("把原片抽象为可复用的 3–5 段式骨架，是二创迁移的关键", "加 ## 七、内容结构框架 节，按时间轴拆成钩子 / 铺垫 / 转折 / 高潮 / 收尾 五段，每段写目的+手法+时长"),
        "量化评分": ("8 维量化评分（钩子 / 信息结构 / 情绪 / 节奏 / 密度 / 互动 / 可复制 / 赛道），把主观感受变成可校准的信号", "加 ## 八、量化评分 节，表格含「维度 / 得分 / 说明」三列，8 行：钩子强度 / 信息结构清晰度 / 情绪曲线 / 节奏与完播设计 / 信息密度 / 互动-转化设计 / 可复制性 / 适用赛道与边界"),
        "二创方向草案": ("3 个二创角度草案（教知识/聊观点/讲故事 等），用户从中选一个深入", "加 ## 九、二创方向草案 节，给 3 个差异化方向：受众 / 钩子 / 叙事类型 / 拍摄形式 / 预期爆点 / 风险点"),
    }
    fixes = []
    if missing_sections:
        fixes.append({
            "type": "missing_sections",
            "what": f"报告缺少 {len(missing_sections)} 个必含章节",
            "items": [
                {"key": s, "why": SECTION_GUIDE.get(s, ("", ""))[0], "how": SECTION_GUIDE.get(s, ("", ""))[1]}
                for s in missing_sections
            ],
        })
    if missing_columns:
        fixes.append({
            "type": "missing_columns",
            "what": f"8 维量化评分表头缺 {sum(len(v) for v in missing_columns.values())} 列",
            "items": [
                {"section": sec, "missing_columns": cols,
                 "how": "在「量化评分」节首行表格补齐列名（维度 / 得分 / 说明 三列硬要求）"}
                for sec, cols in missing_columns.items()
            ],
        })
    if missing_dimensions:
        fixes.append({
            "type": "missing_dimensions",
            "what": f"8 维评分缺 {len(missing_dimensions)} 行",
            "items": [
                {"dimension": d,
                 "how": "在「量化评分」表格中补齐该维度行（精确名称，参见固定 8 维）"}
                for d in missing_dimensions
            ],
        })
    if issues:
        fixes.append({
            "type": "issues",
            "what": f"另有 {len(issues)} 项细节问题",
            "items": [{"detail": i} for i in issues],
        })
    if not fixes and not soft_issues:
        return {"status": "ok", "summary": "✅ 报告结构达标，无需补写", "fixes": []}
    summary_lines = []
    if fixes:
        summary_lines.append("❌ 报告结构未达标，需补 " + str(sum(len(f.get('items', [])) for f in fixes)) + " 处")
    if soft_issues:
        summary_lines.append("⚠️ " + str(len(soft_issues)) + " 项软检查建议（非阻塞）")
    return {
        "status": "needs_fix" if fixes else "ok_with_warnings",
        "summary": " · ".join(summary_lines),
        "fixes": fixes,
        "soft_issues": soft_issues,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="拆解报告本地结构硬门禁（不达标退出码 12）")
    ap.add_argument("report", help="报告 Markdown 文件路径，或 '-' 从 stdin 读取")
    args = ap.parse_args()

    content = read_content(args.report)
    if content is None:
        emit({"ok": False, "error": "无法读取报告文件",
              "human_readable": {"status": "needs_fix",
                                 "summary": "❌ 读取报告失败，请按上面 stderr 提示操作",
                                 "fixes": [{"type": "input", "what": "无法读取报告文件"}]},
              "issues": ["输入错误"]})
        return _fe.EXIT_USER

    result = verify(content)
    emit(result)
    return 0 if result["ok"] else 12


if __name__ == "__main__":
    raise SystemExit(main())
