---
name: business-data-analysis
description: 自动化财务与业务数据分析：脚本化完成数据 profile、清洗、差异/趋势/相关性/KPI 计算，并生成 Markdown/HTML 报表。触发：用户提供财务报表或业务数据（CSV/Excel）要做分析、数据挖掘、出报表、算 KPI、看趋势/同比环比/差异分析、数据质量检查。
author: Soulmate Agent团队成员：岸
---

# 自动化财务与业务数据分析


## 适用场景

- 用户提供财务报表（利润表、资产负债表、现金流量表）、业务数据（销售/运营/客户/成本），或要求做数据分析、数据挖掘、报表生成、KPI 计算、趋势分析、差异分析、同比环比、多维分析、数据清洗。
- 触发词：分析数据、财务分析、业务分析、做报表、数据挖掘、看看数据、分析一下、出报告、KPI、趋势、同比、环比、差异分析、数据质量、收入分析、成本分析、客户分析、运营分析。

## 边界

本技能只做业务/财务数据的 KPI 流水线：清洗 → 差异/趋势/KPI 计算 → 报表输出。统计假设检验与学术研究类分析不在本技能范围。

## 步骤

### 1. 理解需求

明确（缺则确认）：数据来源（文件路径/格式，CSV/Excel，或数据结构描述）、分析目标（盈利/增长/效率/风险）、时间范围、对比基准（上期/预算/行业）。

### 2. 数据加载与质量评估

```bash
python3 scripts/auto_data_analysis/analyze.py profile {文件路径}
```

关注行数、字段类型、空值率、数值范围是否合理；发现异常数据立即告知用户。

### 3. 数据清洗

```bash
python3 scripts/auto_data_analysis/analyze.py clean {文件路径} -o {输出路径}
```

- 空值：数值列用中位数填充，分类列用众数填充（可 `--fill-numeric median|mean`、`--fill-categorical mode|drop`）。
- 全空列自动删除；清洗后向用户确认数据量变化。
- 可选 `--sheet` 指定 Excel sheet。

### 4. 核心分析（按场景选择）

```bash
# 差异分析（环比、同比、分组对比）
python3 scripts/auto_data_analysis/analyze.py variance {文件} --value {数值列} --period {时间列} --group {分组列}

# 趋势分析（--freq D|W|M|Q|Y）
python3 scripts/auto_data_analysis/analyze.py trend {文件} --date {日期列} --value {数值列} --freq M

# 相关性分析
python3 scripts/auto_data_analysis/analyze.py correlate {文件} --columns {列1} {列2} ...
```

通用输出选项：`--format json|markdown`、`--output {路径}`、`--sheet {名称}`。

#### KPI 计算

准备配置 JSON，然后执行：

```bash
python3 scripts/auto_data_analysis/analyze.py kpi {文件} --config {kpi_config.json}
```

```json
{"kpis": [
  {"name": "总收入", "formula": "sum(revenue)"},
  {"name": "平均毛利率", "formula": "mean(gross_margin_pct)"},
  {"name": "订单数", "formula": "count(order_id)"}
]}
```

### 5. 深度分析参考（按场景加载）

- 财务数据：`assets/业务分析_财务指标.md`（指标体系与公式）。
- 业务数据：`assets/业务分析_分析模式.md`（分析场景与方法论）。
- 生成报表：`assets/业务分析_报表模板.md`（结构与格式规范）。

### 6. 生成报表

```bash
python3 scripts/auto_data_analysis/report_generator.py {report_config.json} -o {输出路径} --format markdown
```

```json
{
  "title": "2025年度财务分析报告",
  "metadata": {"period": "2025-01 至 2025-12", "author": "..."},
  "sections": [
    {"title": "执行摘要", "content": "核心发现概要...", "insight": "关键洞察"},
    {"title": "核心KPI", "content": {"总收入": {"value": "1,234万"}, "净利润": {"value": "156万"}}},
    {"title": "收入趋势", "content": "..."}
  ]
}
```

支持输出 Markdown 和 HTML 两种格式。

## 分析原则

1. **先概览再深挖**：先了解全貌，再针对重点展开。
2. **结论驱动**：每个分析模块结束总结 1–3 条结论。
3. **数据说话**：用具体数字支撑观点。
4. **标注异常**：发现偏离预期的数据点主动提示风险。
5. **可操作性**：输出应包含明确行动建议。

## 输入 / 输出

- **输入**：CSV/Excel 文件（可指定 sheet）；分析参数或 KPI/报表配置 JSON。
- **输出**：数据概览/清洗结果、差异/趋势/相关性/KPI 分析（JSON 或 Markdown）、Markdown/HTML 报表。

## 注意事项

- pandas、numpy 为必需依赖，运行前确认已安装。
- 大数据集（> 100MB）建议先采样再全量。
- 敏感财务数据注意脱敏提示。
- 预测类分析需明确告知置信区间与局限性。

## 资源

| 文件 | 用途 |
|---|---|
| `scripts/auto_data_analysis/analyze.py` | profile/clean/variance/trend/kpi/correlate 子命令 |
| `scripts/auto_data_analysis/report_generator.py` | 报表生成（Markdown/HTML） |
| `assets/业务分析_财务指标.md` | 财务指标体系与公式 |
| `assets/业务分析_分析模式.md` | 业务分析场景与方法论 |
| `assets/业务分析_报表模板.md` | 报表结构与格式规范 |

## 可复用示例

**示例 1（环比差异分析）**
> 输入：销售数据表 + 「看看这个月收入跟上次比差多少」
> 流程：`profile` 概览 → `clean` 清洗 → `variance --value revenue --period month` → 总结 1–3 条结论 + 行动建议。

**示例 2（KPI + 报表）**
> 输入：年度财务数据 + 「出一份年度财务分析报告」
> 流程：配置 KPI JSON → `kpi --config` → 组织 report_config.json → `report_generator.py ... --format markdown` → 交付报表。
