---
name: weekly-research-report
description: A股每周金融投研报告生成器：AKShare 取数 → 技术分析（均线/RSI/MACD/KDJ/ATR）→ 券商风格 PDF（含市场概览、个股技术分析、交易信号、风险评估）。触发：用户要「生成周报/投研报告/A股研报」，或给股票代码要出本周投研周报。
author: Soulmate Agent团队成员：岸
---

# A股每周金融投研报告生成器


## 适用场景

- 需要生成 A 股每周金融投研报告（券商研报风格 PDF），含技术分析、交易信号、风险评估。
- 触发：生成周报、金融报告、投研报告、股票分析、A股研报。
- 参数提示：`股票代码(逗号分隔) [--date YYYY-MM-DD] [--author 名字]`。

## 快速开始

```bash
pip3 install -r scripts/weekly_report/requirements.txt

# 默认跳过全市场统计，更快
python3 scripts/weekly_report/generate_weekly_report.py --stocks 000001,600519,000858 --skip-breadth

# 完整报告（含全市场涨跌统计，约多 1 分钟）
python3 scripts/weekly_report/generate_weekly_report.py --stocks 000001,600519,000858

# 指定日期和作者
python3 scripts/weekly_report/generate_weekly_report.py --stocks 600519 --date 2026-03-14 --author 投研团队
```

CLI 参数：

| 参数 | 说明 |
|------|------|
| `--stocks` | 必填，股票代码，逗号分隔，如 `000001,600519,000858` |
| `--date` | 报告日期，默认今天，格式 `YYYY-MM-DD` |
| `--author` | 作者名称，默认「Soulmate Agent团队成员：岸」 |
| `--output` | 输出文件路径，默认 `output/周报_日期.md` |
| `--skip-breadth` | 跳过市场涨跌统计（较慢） |

## 工作原理（脚本自动完成）

1. 获取主要指数数据 —— 上证指数、深证成指、沪深300、创业板指。
2. 获取市场情绪 —— 全市场涨跌家数、涨停跌停统计（可选）。
3. 获取北向资金 —— 本周净流入/净流出。
4. 个股技术分析 —— 均线、RSI、MACD、KDJ、ATR、量价等。
5. 获取持仓新闻 —— 个股相关新闻 + 全球宏观要闻。
6. 生成 PDF 报告 —— HTML+CSS → weasyprint → Ghostscript 优化。

### 技术指标体系（见 `scripts/weekly_report/technical_analysis.py`）

| 类别 | 指标 | 说明 |
|------|------|------|
| 均线 | MA5, MA10, MA20 | 趋势与排列判断 |
| 动量 | RSI(14) | 相对强弱，超买 > 80 / 超卖 < 20 |
| 动量 | MACD(12,26,9) | 趋势强度，金叉/死叉 |
| 动量 | KDJ(9,3,3) | 超买超卖判断 |
| 波动率 | ATR(14) | 真实波动幅度 |
| 波动率 | 标准差(20日) | 价格离散度 |
| 量价 | 量比(5日) | 成交活跃度 |
| 量价 | 换手率 | 交易活跃程度 |

### 交易信号

- **买入信号**：MA5 金叉 MA10、价格突破 MA10、量价齐升、RSI 50–70、MACD 翻红。
- **卖出信号**：MA5 死叉 MA10、放量跌破 MA5、RSI > 80、5 日涨幅 > 15%、KDJ 超买。

### 风险控制

```
止损位 = min(前日低点 × 0.995, MA10 × 0.99, 入场价 × 0.95)
止盈位 = 当前价 + ATR × 2
仓位系数 = (10 - 风险评分) / 10
```

### 单标的分析输出样式（示例）

```
标的: 贵州茅台 (600519)
收盘价: ¥1,856.00  (+2.3%)
趋势: 多头排列 (MA5 > MA10 > MA20)
技术指标:
  RSI(14): 62.5 — 正常区间
  MACD: 金叉，柱状翻红
  KDJ: K=68, D=55, J=94
交易信号:
  🟢 买入信号 x3  |  🔴 卖出信号 x0
  信号强度: 强
风险评估:
  风险评分: 4/10
  止损位: ¥1,812.00
  止盈位: ¥1,920.00
  建议仓位: 60%
```

## 报告内容结构（A4）

1. 封面与投资要点 —— 核心观点、看多/看空/中性统计、数据来源。
2. 目录。
3. 市场概览 —— 大盘指数、涨跌家数、北向资金、持仓资讯、宏观要闻。
4. 个股技术分析 —— 价格走势图、MACD+RSI 图表。
5. 交易信号汇总 —— 买入/卖出信号、信号强度。
6. 风险评估与仓位建议 —— 风险评分、止损止盈、仓位系数。
7. 风险提示与免责声明。

## 数据来源

数据通过 AKShare 开源接口获取：

| 数据类型 | 来源 |
|----------|------|
| A 股日线行情（前复权） | 新浪财经 |
| 主要指数日线数据 | 新浪财经 |
| 个股实时行情与名称 | 新浪财经 |
| 全市场涨跌统计 | 新浪财经 |
| 北向资金数据 | 东方财富 |
| 个股相关新闻 | 东方财富 |
| 全球财经要闻 | 东方财富 |

## 输入 / 输出

- **输入**：股票代码（逗号分隔）；可选日期、作者、输出路径、是否跳过全市场统计。
- **输出**：报告文件保存到 `output/`，文件名格式 `周报_YYYY-MM-DD.pdf`；样式为券商研报（红色主题、专业表格、技术图表）；末尾附风险提示与免责声明。

## 系统依赖

- `python3` 在 PATH。
- `pango`（macOS: `brew install pango`）—— weasyprint 渲染依赖。
- `ghostscript`（macOS: `brew install ghostscript`）—— PDF 兼容性优化。
- Python 包：见 `scripts/weekly_report/requirements.txt`（akshare / pandas / numpy / weasyprint / matplotlib）。

## 注意事项

- 数据来自公开接口，部分数据可能有 15 分钟延迟。
- 行业板块资金流向受网络环境限制可能不可用。
- 全市场涨跌统计（`--skip-breadth` 可跳过）约需 1 分钟。
- 本技能不执行交易操作，所有建议仅供参考，不构成投资建议。

## 资源

| 文件 | 用途 |
|---|---|
| `scripts/weekly_report/generate_weekly_report.py` | 主入口，串起取数→分析→出报告 |
| `scripts/weekly_report/data_fetcher.py` | AKShare 数据获取 |
| `scripts/weekly_report/technical_analysis.py` | 技术指标与交易信号 |
| `scripts/weekly_report/chart_generator.py` | 图表生成 |
| `scripts/weekly_report/report_generator.py` | HTML/CSS→PDF 报告渲染 |
| `scripts/weekly_report/requirements.txt` | Python 依赖 |

## 可复用示例

**示例 1（快速周报）**
> 输入：「给 000001、600519、000858 出个本周投研周报」
> 流程：`pip3 install -r scripts/weekly_report/requirements.txt` → `python3 scripts/weekly_report/generate_weekly_report.py --stocks 000001,600519,000858 --skip-breadth` → 从 `output/` 取 PDF。

**示例 2（带日期/作者）**
> 输入：「生成 2026-03-14 的周报，作者写投研团队，只看 600519」
> 流程：`python3 scripts/weekly_report/generate_weekly_report.py --stocks 600519 --date 2026-03-14 --author 投研团队`。
