---
name: budget-vs-actual
description: 月度/季度预算 vs 实际（BvA）差异分析：建差异表（金额/百分比/有利-不利/重要性标记）、下钻根因、按 WHAT/WHY/ACTION/OUTLOOK 写管理层评论、更新滚动重预测。触发：用户要「跑 X 月/季度预算 vs 实际」「解释这个月差异」「为什么收入没达标/EBITDA 未达预期」「准备董事会 BvA」，或「按实际更新滚动预测/重新预测全年」。
author: Soulmate Agent团队成员：岸
---

# 月度/季度预算 vs 实际差异分析（BvA）


## 适用场景

- 做期末预算 vs 实际分析：拉实际数、对比预算、算差异、定位根因、写管理层评论、更新滚动预测。
- 触发：「跑一下 X 月/季度的预算 vs 实际」「解释这个月的差异」「为什么收入没达标/超了」「准备 X 期的管理层报告」「按实际数更新滚动预测」「董事会议需要 BvA 评论」「是什么驱动了 EBITDA 未达预期」「重新预测全年」。
- **不用于**：从零做预算（用财务建模类技能）；报税；实时记账/交易分类；多主体合并抵消；多年战略规划（LRP）。

## 核心概念

### 差异类型

| 类型 | 公式 | 含义 |
|---|---|---|
| 绝对差异 | 实际 − 预算 | 金额差 |
| 百分比差异 | (实际 − 预算) / 预算 × 100 | 相对预算的幅度 |
| 有利（F） | 收入：实际 > 预算 / 费用：实际 < 预算 | 好于计划 |
| 不利（U） | 收入：实际 < 预算 / 费用：实际 > 预算 | 差于计划 |

### 重要性阈值（默认，可按项目定制）

```
收入行:   ≥ $5,000 或 ≥ 预算行 5%   → 需调查
费用行:   ≥ $2,500 或 ≥ 预算行 10%  → 需调查
总 EBITDA: ≥ $10,000 或 ≥ 预算 EBITDA 5% → 需董事会评论
YTD 累计:  月度差异结转；YTD 超全年重要性阈值时标记
```

### 差异根因分类

- **收入**：量差（单位/客户数）、价差（ASP/定价）、结构差（产品/分部组合）、时点差（跨期成交）、新客 vs 老客。
- **费用**：人员时点（早/晚入职）、外包/供应商、一次性项目、随量变动（COGS、销售佣金）、涨价/通胀。

## 步骤

### Step 1：收集输入

```
必需：
□ 期间（月、季度、YTD）
□ 预算/预测文件（CSV、Sheets 或直接录入）
□ 实际数文件或 QBO 导出（同期、同科目映射）
□ 会计科目表映射（预算与实际用不同标签时）
□ 重要性阈值（未指定用默认）
□ 受众（内部管理层、董事会、投资人）
可选：
□ 上期实际数（趋势语境）
□ 去年同期（YoY 语境）
□ 上期叙事
```

### Step 2：归一化数据

把实际数映射到预算行。标准 P&L 映射：

```
预算标签            → 实际数（QBO）对应
Revenue             → Total Income
COGS                → Cost of Goods Sold / Direct Costs
Gross Profit        → （计算）
Sales & Marketing   → Advertising, Sales Commissions, Marketing Expenses
R&D / Engineering   → Contract Labor (tech), Software Tools
G&A                 → Payroll (admin), Legal, Accounting, Insurance
Total OpEx          → （上列之和）
EBITDA              → Gross Profit − Total OpEx
```

### Step 3：计算差异

```python
for each line_item:
    absolute_var = actual - budget
    pct_var = (actual - budget) / abs(budget) * 100   # 处理预算为 0 的边界
    if is_revenue_line:
        favorable = actual > budget
    else:  # expense line
        favorable = actual < budget
    flag = abs(pct_var) >= threshold_pct or abs(absolute_var) >= threshold_dollar
```

### Step 4：构建差异表

```
PERIOD: March 2026 | Budget vs. Actual

Line Item          | Budget    | Actual    | $ Var     | % Var  | F/U | Flag
REVENUE            |           |           |           |        |     |
  Product Revenue  | $120,000  | $108,500  | ($11,500) | -9.6%  |  U  |  ⚠️
  Service Revenue  |  $30,000  |  $34,200  |  $4,200   | +14.0% |  F  |  ⚠️
  Total Revenue    | $150,000  | $142,700  |  ($7,300) | -4.9%  |  U  |
COGS               |  $45,000  |  $43,100  |  $1,900   | +4.2%  |  F  |
Gross Profit       | $105,000  |  $99,600  |  ($5,400) | -5.1%  |  U  |  ⚠️
Gross Margin %     |   70.0%   |   69.8%   |   -0.2pp  |        |     |
OPERATING EXPENSES |           |           |           |        |     |
  S&M              |  $25,000  |  $27,400  |  $2,400   | +9.6%  |  U  |  ⚠️
  R&D              |  $20,000  |  $18,500  | ($1,500)  | -7.5%  |  F  |
  G&A              |  $15,000  |  $16,200  |  $1,200   | +8.0%  |  U  |
  Total OpEx       |  $60,000  |  $62,100  |  $2,100   | +3.5%  |  U  |
EBITDA             |  $45,000  |  $37,500  |  ($7,500) | -16.7% |  U  |  🚨
EBITDA Margin      |   30.0%   |   26.3%   |   -3.7pp  |        |     |
```

### Step 5：根因分析

对每条被标记的差异下钻。

收入未达标示例（Product Revenue −$11,500 / −9.6%）：
```
- 量：成交 8 单 vs 预算 10 单 = −2 单
- 价：均价 $13,563 vs 预算 $12,000 → 每单 +$1,563（结构有利）
- 净：2 单 × $12,000 ASP = −$24,000 量差
      + 8 单 × $1,563 价/结构溢价 = +$12,500 抵消
      = 报告净额 ($11,500) ✓
判断：量的问题、非定价问题；销售管道滑期，2 单移到 4 月。
```

S&M 超支示例（$2,400 / +9.6% 不利）：
```
- 计划：$15k 广告 + $10k 薪酬
- 实际：$15k 广告 + $10k 薪酬 + $2,400 会议注册（未编预算）
- 分类：一次性 / 非经常性 —— 下月不会重复
判断：良性；明年编入预算即可，无需动作。
```

### Step 6：管理层评论（每条重要差异按此结构）

```
[LINE ITEM] — [VARIANCE DIRECTION] by $[AMOUNT] ([PERCENT]%)
WHAT:   [用大白话说这个数字说明什么]
WHY:    [具体根因，不要泛泛而谈]
ACTION: [我们正在做什么，或为什么无需动作]
OUTLOOK:[对全年预测的影响]
```

示例：

> **EBITDA — 不利 $7,500（-16.7%）**
>
> WHAT: 3 月 EBITDA $37,500，比 $45,000 预算少 $7,500，主要由收入缺口造成，部分被 R&D 少花抵消。
> WHY: 产品收入少 $11,500，因 2 单企业合同滑到 4 月（管道已确认、非丢单）。S&M 超预算 $2,400 来自一次性会议注册。R&D 有利 $1,500，因一个外包项目启动晚。
> ACTION: 2 单滑期合同预计 4 月签（均在终稿阶段）。会议注册已费用化，不重复。R&D 外包已到位，预计 4 月起满负荷。
> OUTLOOK: Q2 预测前移这 2 单；全年 EBITDA 预测维持 $540,000 不变。

### Step 7：更新滚动预测

```
重预测逻辑：
1. 锁定已结期间的实际情况（不要重编历史预算）
2. 滚动：区分永久性与时点性差异
   - 时点性：移到下一期（合同滑期、晚入职）
   - 永久性：调整全年假设（市场走弱、新常态运行率）
3. 更新全年合计：YTD 实际 + 剩余预算（调整后）；如适用重算跑道/现金
4. 标记相对上次预测的变化：收入 ±$X、EBITDA ±$X、年末现金 ±$X
```

```
                   | Original  | Prior     | Current   | Change
                   | Budget    | Forecast  | Forecast  | (vs Prior)
Full-Year Revenue  | $1,800,000| $1,750,000| $1,762,000| +$12,000
Full-Year EBITDA   |  $540,000 |  $510,000 |  $512,500 |  +$2,500
Year-End Cash      |  $850,000 |  $790,000 |  $793,000 |  +$3,000
```

## 输入 / 输出

- **输入**：期间、预算/预测、实际数（或 QBO 导出）、科目映射、重要性阈值、受众；可选上期/去年同期实际。
- **输出**：三种形态 ——
  1. **管理层报告**（叙述 + 表）：差异表、根因、重预测，供 CFO/CEO/董事会。
  2. **快速 Flash（1 页）**：头部 KPI（收入/毛利率/EBITDA/现金，各一行实际 vs 预算）+ Top 3 差异各一句解释 + 相对上次预测的重预测变化。
  3. **结构化 JSON**（供下游处理），字段示例：

```json
{
  "period": "2026-03", "period_type": "month", "generated_at": "2026-04-02",
  "summary": {
    "total_revenue_budget": 150000, "total_revenue_actual": 142700,
    "total_revenue_variance_abs": -7300, "total_revenue_variance_pct": -4.87,
    "ebitda_budget": 45000, "ebitda_actual": 37500,
    "ebitda_variance_abs": -7500, "ebitda_variance_pct": -16.67
  },
  "line_items": [
    {"name": "Product Revenue", "budget": 120000, "actual": 108500,
     "variance_abs": -11500, "variance_pct": -9.58, "favorable": false, "material": true,
     "root_cause": "2 enterprise deals slipped to April (pipeline confirmed)",
     "action": "Deals expected April close; no change to full-year forecast"}
  ],
  "reforecast": {
    "full_year_revenue_original": 1800000, "full_year_revenue_current": 1762000,
    "full_year_ebitda_original": 540000, "full_year_ebitda_current": 512500
  }
}
```

## QBO 集成流程（实际数来自 QuickBooks Online）

```
1. 导出：QBO → Reports → Profit & Loss（选期间，与前期对比）
2. 或走 API：GET /v3/company/{id}/reports/ProfitAndLoss?start_date=&end_date=&summarize_column_by=Month
3. 用 COA 映射表把 QBO 科目名映射到预算行
4. 校验合计：QBO 收入合计必须等于各明细行之和（抓映射错误）
5. 进入上面的差异计算
```

常见 QBO 映射坑：QBO 拆出的子类而预算里是合并的 → 向上合并；owner draws 不是费用 → 从 P&L 分析剔除；工资税可能单列 → 并入含税人力成本。

## 边界情形处理

- **预算为 0 但有实际发生**：绝不除零；`variance_pct = "N/A (no budget)"`；实际超金额阈值即视为重要；评论写「[科目] 未编预算支出 $X」。
- **前期重述**：显式标记重述；展示 原报 → 重述 → 差额；相应更新 YTD；在评论中留审计痕迹。
- **多部门/成本中心**：至少在公司合并层面跑；有成本中心再按部门跑；标注跨部门抵消（如 R&D 少花被 G&A 超支掩盖）。
- **季节性业务**：BvA 之外并行 YoY 对比（本月实际 vs 本月预算为主，本月实际 vs 去年同月为辅）；判断差异是季节性（预期内）还是结构性（新问题）。

## 术语表

| 术语 | 定义 |
|---|---|
| BvA | 预算 vs 实际 |
| F / U | 有利 / 不利 |
| pp | 百分点（用于毛利率比较） |
| YTD / QTD / MTD | 年初至今 / 季初至今 / 月初至今 |
| Reforecast | 基于已发生实际数对全年的更新预测 |
| Flash | 完整结账前的快速初步 BvA（可用估算） |
| Hard close / Soft close | 最终锁定实际 / 初步实际（或有计提调整） |

## 注意事项

- 时间点差异（滑期）与永久性差异要分开处理，否则全年预测失真。
- 未编预算的支出不除零计算百分比。
- 汇总层面看总数时，注意部门间一涨一跌相互抵消。

## 资源

本功能无随附脚本/模板文件；差异表与 JSON 结构见上文。

## 可复用示例

**示例 1（完整 BvA + 董事会评论）**
> 输入：「3 月已结账。预算收入 $150k、EBITDA $45k；实际收入 $142k、EBITDA $37.5k。产品少 $11.5k（两单企业合同滑期），服务超 $4.2k，S&M 会议超 $2.4k，R&D 少 $1.5k（外包晚启动）。出 BvA 表、根因摘要和董事会评论，并标出重预测影响。」
> 流程：建差异表（含 F/U 与重要性标记）→ 对标记行写根因 → 按 WHAT/WHY/ACTION/OUTLOOK 写评论 → 出重预测差额（区分时点/结构性）→ 需要时输出结构化 JSON。

**示例 2（一页 Flash）**
> 输入：「先给我一页纸的月度 Flash」
> 流程：输出头部 KPI（收入/毛利率/EBITDA/现金 实际 vs 预算）+ Top 3 差异各一句 + 相对上次预测的重预测变化。
