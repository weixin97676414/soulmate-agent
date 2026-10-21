---
name: data-analysis-workflow
description: 六阶段标准化统计与学术数据分析流程（导入→清洗→描述→推断→可视化→APA 报告），处理 CSV/Excel/JSON 数据，输出假设检验、效应量与置信区间。触发：数据分析、数据清洗、EDA、描述统计、假设检验、出分析报告。
author: Soulmate Agent团队成员：岸
---

# 标准化数据分析工作流

本技能聚焦统计/学术分析（假设检验、效应量与 APA 报告）；业务/财务 KPI 流水线分析不由本技能承担。

## 适用场景

- 从数据导入到结果报告的一条龙分析：实验数据、调查数据、探索性数据分析（EDA）。
- 需要 APA 格式统计报告、假设检验、效应量、出版级图表。
- 面向数据分析师、产品经理、运营的常规数据清洗与统计。

## 步骤（六阶段）

1. **数据导入与检查**（5–10 分钟）：维度、变量类型、缺失值、异常值检查。
2. **数据清洗与预处理**（15–30 分钟）：缺失值/异常值处理、变量转换、标准化。
3. **描述统计与探索**（20–40 分钟）：集中趋势、离散程度、分布形态、相关分析。
4. **推断统计分析**（30–60 分钟）：检验选择、假设条件检查、执行检验、效应量计算。
5. **可视化呈现**（20–40 分钟）：统计图表（seaborn）、定制图表（matplotlib）、出版级图表。
6. **结果报告**（15–30 分钟）：APA 格式报告、结果解释、图表整合。

## 输入输出

- 输入：数据文件（CSV/Excel/JSON/数据库/API），分析类型。
- 输出：分析报告（Markdown，可指定 APA 格式）、统计结果表、图表。

## 常用命令

```bash
# 完整流程
python scripts/data_analysis_workflow.py --file data.csv --type experimental

# 单阶段
python scripts/data_analysis_workflow.py --file data.csv --stage 3
python scripts/data_analysis_workflow.py --file data.csv --stage 4 --test anova
python scripts/data_analysis_workflow.py --file data.csv --stage 5 --plot boxplot

# 报告格式 / 批量 / 出版级
python scripts/data_analysis_workflow.py --file data.csv --output report.md --format APA
python scripts/data_analysis_workflow.py --input-dir data/ --output-dir results/
python scripts/data_analysis_workflow.py --file data.csv --publication-quality --journal nature
```

分析类型 `--type`：`experimental`（组间比较、前后测：t 检验/ANOVA/卡方；箱线/小提琴/带误差线柱状）、`survey`（相关、回归、因子分析；热力图/散点/直方图）、`exploratory`（描述统计、相关；pairplot/分布图/相关矩阵）。

## 实现参考（各阶段 pandas 代码）

```python
# 读取与预览
import pandas as pd
df = pd.read_csv('data.csv')          # 也支持 read_excel / read_json / read_sql
print(df.shape, df.columns, df.dtypes, df.info())
print(df.describe(include='all'))

# 清洗
df.isnull().sum(); df.dropna(); df.fillna(df.mean())
df['col'].fillna(df['col'].mode()[0])
df.duplicated().sum(); df.drop_duplicates(subset=['col'])
df['date'] = pd.to_datetime(df['date'])
Q1, Q3 = df['col'].quantile([0.25, 0.75]); IQR = Q3 - Q1
df = df[(df['col'] >= Q1 - 1.5*IQR) & (df['col'] <= Q3 + 1.5*IQR)]

# 描述 / 相关 / 分组
df['col'].mean(); df['col'].median(); df['col'].std(); df['col'].skew(); df['col'].kurt()
df.corr()['target']
df.groupby('category').agg({'sales': ['sum', 'mean', 'count']})
pd.crosstab(df['col1'], df['col2'])

# 时间序列
df = df.set_index(pd.to_datetime(df['date']))
df.resample('M').sum(); df['col'].rolling(window=7).mean(); df['col'].pct_change()
```

## 假设条件与 APA 报告模板

- **t 检验**（比较两组均值）：正态性、方差齐性、独立性。
  `进行独立样本 t 检验，结果显示两组之间存在显著差异，t(58) = 2.45, p = .017, d = 0.63, 95% CI [0.12, 1.14]。`
- **ANOVA**（三组及以上）：正态性、方差齐性、独立性。
  `进行单因素方差分析，结果显示三组之间存在显著差异，F(2, 87) = 5.67, p = .005, η² = 0.12。`
- **相关分析**：Pearson（连续+正态）/ Spearman（等级/非正态）。
  `Pearson 相关分析显示，变量 X 与变量 Y 呈显著正相关，r(98) = .45, p < .001, 95% CI [.28, .59]。`

## 注意事项

- **先探索后检验**：先做 EDA 了解数据特征，再选统计方法。
- **必查假设条件**，非参数数据不要用参数检验。
- **必须报告效应量与置信区间**，不只报 p 值。
- 避免 3D 饼图等不当可视化；相关不等于因果，谨慎解释。
- 大数据集注意内存；处理前备份数据；结果需业务验证。
- 数据质量参考：缺失值 <5% 优 / 5–10% 良 / >10% 需改进；异常值 <1% 优。

## 可复用示例

```bash
python scripts/data_analysis_workflow.py --file experiment_data.csv --type experimental --output experiment_report.md
python scripts/data_analysis_workflow.py --file survey_data.csv --type survey --output survey_report.md
python scripts/data_analysis_workflow.py --file data.csv --type exploratory --output eda_report.md
```
