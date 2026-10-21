---
name: hr-text-extraction
description: 简历文件转干净文本：解析 PDF 文字层并按坐标重建行、过滤招聘平台斜向水印，扫描版 PDF / 简历截图走 OCR，Word(.docx) 抽取正文与表格。触发场景：拿到简历文件要提取正文、简历转文本、解析简历文件、扫描件或截图识别。
author: Soulmate Agent团队成员：岸
---

# 简历文件 → 干净文本

## 适用场景

- 候选人发来 PDF 简历
- BOSS 直聘等招聘平台导出的带斜向水印简历
- 扫描版 PDF（无文字层）或简历截图（图片）
- Word 简历（.docx）

## 步骤

1. 判断文件类型（.pdf / .png / .jpg / .docx）。
2. **PDF（有文字层）**：
   ```bash
   python scripts/resume_to_text.py "简历.pdf" -o /tmp/resume.md
   ```
   脚本按坐标重建行、过滤平台水印（长串 ID + 散落单字符碎片），输出逐行干净文本。
3. **扫描版 PDF / 图片（OCR）**：
   ```bash
   python scripts/resume_to_text.py "简历.jpg" --ocr -o /tmp/resume.md
   ```
   需先 `pip install 'markitdown[all]'`。
4. **DOCX**：
   ```bash
   python scripts/extract_docx.py "简历.docx" > /tmp/resume.txt
   ```
   脚本同时抽取正文段落与表格单元格文本。
5. 转换完成后**人工扫一眼**，确认姓名 / 学校 / 经历等核心信息完整，再进入下一步分析。

## 输入输出

- 输入：`.pdf` / `.png` / `.jpg` / `.docx` 简历文件
- 输出：干净文本（默认打印到 stdout，可用 `-o` 写入文件）

## 注意事项

- 依赖：PDF 文本层用 `pdfplumber`；图片 / 扫描版 OCR 用 `markitdown`；DOCX 用 `python-docx`。
- 老格式 `.doc` 无内置脚本处理，**未验证**；建议先另存为 `.docx`。
- 扫描版 PDF 无文字层时会提示「未提取到文本层」——改用 `--ocr`，或让对方发文字版 / 截图。
- 水印过滤不是 100% 无损：斜向水印的孤立字符在极端情况下可能残留碎片或误删孤立数字，必须人工快速核对。
- 图片 / 扫描版 OCR 由 `resume_to_text.py` 处理（Tesseract 引擎），无需额外脚本。

## 可复用示例

```bash
# 普通 PDF
python scripts/resume_to_text.py "$HOME/简历/张三.pdf" -o /tmp/zhangsan.md

# 扫描版 PDF / 图片
python scripts/resume_to_text.py "$HOME/简历/李四-截图.png" --ocr -o /tmp/lisi.md

# Word
python scripts/extract_docx.py "$HOME/简历/王五.docx" > /tmp/wangwu.txt
```
