---
name: finance-report-generator
description: 上传财务文件生成可视化报告：Excel/CSV/PDF → HTML 基底（内联 SVG 趋势迷你图）并转换为 PDF/DOCX/Markdown。触发：用户上传本地财务数据文件，要生成公司财务分析报告、可视化报告。
author: Soulmate Agent团队成员：岸
---

# 上传文件生成财务分析报告（含趋势迷你图）


## 适用场景

- 用户上传 Excel/CSV/PDF 财务数据。
- 用户要求做财务分析或公司报告。
- 用户想要从财务报表生成可视化报告。
- 用户提到股票代码 + 财务分析。

## 步骤

### Step 1：获取数据文件

使用用户提供的本地文件（Excel/CSV/PDF）。

### Step 2：生成报告

```bash
python3 scripts/generate_report.py input.xlsx -o pdf \
  --company "公司名" --ticker "000001.SZ" --output-dir /tmp/reports
```

CLI 参数：

| 参数 | 说明 |
|------|------|
| `input`（位置参数） | 输入 Excel 文件路径 |
| `-o, --output-format` | 输出格式：`pdf`（默认）/ `doc` / `md` / `html` |
| `--output-dir` | 输出目录，默认当前目录 |
| `--company` | 公司名称 |
| `--ticker` | 股票代码 |

**HTML 始终生成**作为基底，其它格式由 HTML 转换而来：

| `-o` 值 | 输出 | 依赖 |
|---------|------|------|
| `html` | 仅 HTML | 内置 |
| `pdf` | HTML + PDF（默认） | wkhtmltopdf 或 chromium |
| `doc` | HTML + DOCX | pandoc |
| `md` | HTML + Markdown | pandoc 或 markdownify |

### Step 3（可选）：联网补充行业基准

```
web_search("{company} 行业对比 市场份额 {year}")
```

### Step 4：交付文件

报告生成在本地输出目录，交付时提供文件路径（接收端能直接读取）。

## 报告特性

- **迷你趋势图**：每个指标行带内联 SVG 趋势（实线=实际，虚线=预测）。
- **预测标记**：预测值用 ⟡ 和黄色背景标记。
- **配色**：绿=正向，红=负向。
- **响应式**：手机与桌面均可用；含打印样式。

## 输入 / 输出

- **输入**：本地 Excel/CSV/PDF 财务数据文件；公司名、股票代码（可选）。
- **输出**：报告目录下的 HTML（始终）+ PDF/DOCX/Markdown（按 `-o`）。

## 注意事项

- PDF 需本机有 wkhtmltopdf 或 chromium；DOCX/MD 需 pandoc（或 markdownify）。
- 指标口径见 `assets/财报分析报告_指标定义.md`。
- 交付时确认接收端能直接读取输出目录中的文件路径。

## 资源

| 文件 | 用途 |
|---|---|
| `scripts/generate_report.py` | 报告生成主脚本（HTML/SVG 迷你图 + 多格式转换） |
| `assets/report-theme.css` | 报告主题样式 |
| `assets/财报分析报告_指标定义.md` | 财务指标计算公式定义 |

## 可复用示例

**示例 1**
> 输入：上传 `2025Q3.xlsx` + 「生成一份百济神州的分析报告，要 PDF」
> 流程：确认文件可得 → `python3 scripts/generate_report.py /tmp/data.xlsx -o pdf --company "百济神州-U" --ticker "688235.SH" --output-dir /tmp/reports` → 检查 HTML/PDF 生成 → 按需联网补行业基准 → 交付文件。
