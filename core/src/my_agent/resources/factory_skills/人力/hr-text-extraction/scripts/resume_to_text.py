#!/usr/bin/env python3
# -*- coding: utf-8 -*-



























import argparse
import re
import sys
from pathlib import Path







LONG_TOKEN_MIN_LEN = 15


Y_BIN = 3


def detect_watermark(words):









    charset = set()
    long_tokens = []
    for w in words:
        t = (w.get("text") or "").strip()
        
        if len(t) >= LONG_TOKEN_MIN_LEN and re.fullmatch(r"[A-Za-z0-9\-]+", t):
            long_tokens.append(t)
            charset.update(set(t))
    return charset, long_tokens


def clean_inner_watermark(text, charset):







    if not charset or not text:
        return text
    chars = list(text)
    n = len(chars)
    out = []
    for i, c in enumerate(chars):
        if c in charset:
            left = chars[i - 1] if i > 0 else ""
            right = chars[i + 1] if i < n - 1 else ""
            left_ascii = bool(left) and ord(left) < 128
            right_ascii = bool(right) and ord(right) < 128
            if not left_ascii and not right_ascii:
                continue  
        out.append(c)
    return "".join(out)


def rebuild_lines(words, charset, long_tokens):









    rows = {}
    for w in words:
        t = (w.get("text") or "").strip()
        if not t:
            continue
        
        if t in long_tokens:
            continue
        
        if (
            charset
            and len(t) <= 3
            and not re.search(r"[\u4e00-\u9fff]", t)
            and all(c in charset for c in t)
        ):
            continue
        
        if charset and re.search(r"[\u4e00-\u9fff]", t):
            t = clean_inner_watermark(t, charset)
        if not t.strip():
            continue

        key = round((w.get("top") or 0) / Y_BIN) * Y_BIN
        rows.setdefault(key, []).append((w.get("x0") or 0, t))

    lines = []
    for k in sorted(rows):
        line = " ".join(t for _, t in sorted(rows[k], key=lambda x: x[0]))
        line = line.strip()
        if line:
            lines.append(line)
    return lines


def extract_pdf_text(pdf_path):




    import pdfplumber

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages_text = []
            total_chars = 0
            for page in pdf.pages:
                words = page.extract_words()
                if words:
                    charset, long_tokens = detect_watermark(words)
                    lines = rebuild_lines(words, charset, long_tokens)
                    page_text = "\n".join(lines)
                else:
                    page_text = page.extract_text() or ""
                total_chars += len(page_text)
                if page_text.strip():
                    pages_text.append(page_text.strip())

            text = "\n\n".join(pages_text)
    except Exception as e:  
        print(f"❌ 无法解析 PDF：{e}", file=sys.stderr)
        print("  请确认文件是有效的 PDF（未损坏、非其他格式伪装）。", file=sys.stderr)
        print("  扫描版（无文字层）可加 --ocr 走 OCR。", file=sys.stderr)
        return ""

    if not text.strip():
        print("⚠️  未提取到文本层：这可能是扫描版 PDF（无文字层）。", file=sys.stderr)
        print("    请改用图片 OCR（见下方建议），或让对方发清晰文字版/截图。", file=sys.stderr)
    return text


def extract_with_markitdown(path):

    from markitdown import MarkItDown

    md = MarkItDown()
    result = md.convert(str(path))
    return result.text_content or ""


def main():
    if len(sys.argv) < 2:
        print("用法：python resume_to_text.py <简历文件路径> [-o 输出文件.md] [--ocr]", file=sys.stderr)
        print("示例：python resume_to_text.py 简历.pdf -o /tmp/resume.md", file=sys.stderr)
        print("      扫描版/图片加 --ocr（需 pip install 'markitdown[all]'）", file=sys.stderr)
        sys.exit(1)

    ap = argparse.ArgumentParser(description="简历 PDF/图片 → 干净文本")
    ap.add_argument("input", help="简历文件路径（.pdf / .png / .jpg 等）")
    ap.add_argument("-o", "--output", help="输出文件路径（默认打印到 stdout）")
    ap.add_argument("--ocr", action="store_true", help="用 markitdown 走 OCR（扫描版/图片）")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"❌ 文件不存在：{src}", file=sys.stderr)
        sys.exit(1)

    if args.ocr:
        try:
            text = extract_with_markitdown(src)
        except Exception as e:  
            print(f"❌ OCR 转换失败：{e}", file=sys.stderr)
            print("  建议：pip install 'markitdown[all]'，或让对方发文字版。", file=sys.stderr)
            sys.exit(1)
    elif src.suffix.lower() == ".pdf":
        text = extract_pdf_text(src)
    else:
        
        try:
            text = extract_with_markitdown(src)
        except Exception as e:  
            print(f"❌ 图片转换需要 markitdown：{e}", file=sys.stderr)
            print("  建议：pip install 'markitdown[all]'", file=sys.stderr)
            sys.exit(1)

    
    text = re.sub(r"(?m)^.*(pydub|RuntimeWarning|warn\().*$\n?", "", text)
    text = text.strip()

    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"✅ 已写入 {args.output}（{len(text)} 字符）", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
