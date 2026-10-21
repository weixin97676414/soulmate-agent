---
name: statistics-tests
description: 基于 pywayne 的 37+ 统计检验统一接口（正态性/位置/相关/时间序列/模型诊断），返回统一 TestResult，并给出贝叶斯/机器学习/精算等方法选择。触发：假设检验、A/B 测试、显著性检验、回归诊断、多重比较校正。
author: Soulmate Agent团队成员：岸
---

# 统计检验与建模

## 适用场景

- 假设检验、A/B 测试、数据质量检查、时间序列分析、回归模型诊断。
- 需要统一接口返回 p 值、统计量、置信区间、效应量的检验库。
- 需要选择频率派 / 贝叶斯 / 机器学习框架，并用不确定性量化报告结果。

## 步骤

1. **澄清问题**：假设是什么、结局是什么、数据结构如何。
2. **选择框架**：频率派 vs 贝叶斯 vs 机器学习（给出理由）。
3. **检查假设**：正态性、方差齐性、独立性等（参数检验前必做）。
4. **执行检验**：按类别调用方法，读取统一 `TestResult`。
5. **报告结果**：不确定度（CI/可信区间）、效应量、临床/业务意义，并声明局限。
6. **多重检验**：多次检验时做 p 值校正。

## 检验方法速查

### 正态性 `NormalityTests`
`shapiro_wilk`（n≤5000）、`ks_test_normal`、`ks_test_two_sample`、`anderson_darling`（尾部敏感）、`dagostino_pearson`、`jarque_bera`（大样本/回归残差）、`chi_square_goodness_of_fit`、`lilliefors_test`。

### 位置 `LocationTests`
`one_sample_ttest`、`two_sample_ttest`、`paired_ttest`、`one_way_anova`、`mann_whitney_u`、`wilcoxon_signed_rank`、`kruskal_wallis`。

### 相关 `CorrelationTests`
`pearson_correlation`、`spearman_correlation`、`kendall_tau`、`chi_square_independence`、`fisher_exact_test`、`mcnemar_test`。

### 时间序列 `TimeSeriesTests`
`adf_test`、`kpss_test`、`ljung_box_test`、`runs_test`、`arch_test`、`granger_causality`、`engle_granger_cointegration`、`breusch_godfrey_test`。

### 模型诊断 `ModelDiagnostics`
`breusch_pagan_test`、`white_test`、`goldfeld_quandt_test`、`durbin_watson_test`、`variance_inflation_factor`、`levene_test`、`bartlett_test`、`residual_normality_test`。

## 输入输出

- 输入：`np.ndarray` 或 list；回归诊断额外传自变量矩阵 X。
- 输出：统一 `TestResult` 对象：
  `test_name`、`statistic`、`p_value`、`reject_null`、`critical_value`、`confidence_interval`、`effect_size`、`additional_info`。

## 常用代码

```python
from pywayne.statistics import NormalityTests, LocationTests, CorrelationTests, TimeSeriesTests, ModelDiagnostics
import numpy as np

nt = NormalityTests(); lt = LocationTests()
r = nt.shapiro_wilk(np.random.normal(0, 1, 100))
print(r.p_value, not r.reject_null)

# A/B 测试：先查正态，再选参数/非参数
if nt.shapiro_wilk(control).p_value > 0.05:
    res = lt.two_sample_ttest(control, treatment)
else:
    res = lt.mann_whitney_u(control, treatment)
print(res.test_name, res.p_value, res.reject_null, res.effect_size)

# 回归诊断
md = ModelDiagnostics(); resid = y - model.predict(X)
md.breusch_pagan_test(resid, X).reject_null
md.durbin_watson_test(resid).statistic
max(md.variance_inflation_factor(X))

# 多重检验校正
from statsmodels.stats.multitest import multipletests
p = [r.p_value for r in results]
rejected, p_corrected, _, _ = multipletests(p, alpha=0.05, method='fdr_bh')

# 辅助
from pywayne.statistics import list_all_tests, show_test_usage
print(list_all_tests()); show_test_usage('shapiro_wilk')
```

## 方法选择指南

| 条件 | 参数方法 | 非参数方法 |
|------|----------|-----------|
| 正态 | t 检验、ANOVA | — |
| 非正态 | — | Mann-Whitney U、Kruskal-Wallis |
| 配对 | 配对 t 检验 | Wilcoxon signed-rank |

正态性检验选择：n<30 → Shapiro-Wilk；30≤n≤300 → Shapiro-Wilk / D'Agostino-Pearson；n>300 → Jarque-Bera / K-S。

## 扩展方法范围

- 贝叶斯：先验设定、MCMC（PyMC/ArviZ）、贝叶斯因子、可信区间、后验预测检验、分层模型、贝叶斯生存分析（小样本、有先验、自适应试验、真实世界证据）。
- 蒙特卡洛：MCMC、积分、Bootstrap（参数/非参数）、不确定性传播、概率敏感性分析（PSA）；需报告模拟次数与收敛诊断。
- 机器学习：随机森林、梯度提升（XGBoost）、SVM、弹性网、聚类、PCA/UMAP、生存 ML、LASSO/Boruta/SHAP、交叉验证与校准。
- 深度学习：医学影像 CNN、临床 NLP Transformer、组学自编码器、小样本迁移学习。
- 多重比较：Bonferroni、Holm-Bonferroni、Benjamini-Hochberg(FDR)、置换检验。
- 精算与卫生经济：生命表、竞争风险、CEA/CUA、ICER/NNT/NNH/QALY/DALY、疾病进展 Markov、预算影响。
- 经典生物统计：生存分析（KM/Cox/AFT）、混合效应、Meta 分析（含网络 Meta）、倾向评分（匹配/IPTW）、样本量估算、诊断试验（ROC/AUC/DeLong）。

## 注意事项

- **始终报告置信/可信区间**，不只报 p 值；始终先检查假设；区分统计显著与临床显著。
- 贝叶斯必做先验敏感性分析；ML 必报样本外表现，不能只报训练指标；不要为好看而过拟合。
- 环境：本机 `python3` 具备 numpy/pandas/scipy/scikit-learn/statsmodels/lifelines/arviz/matplotlib/seaborn；完整 PyMC 需另行安装。
- ⚠️ `pywayne.statistics` 为第三方库（包名 `pywayne`），本机**未验证**是否可安装/可用；使用前先确认导入成功。

## 可复用示例

```python
# 数据质量检查
def data_quality_check(data):
    nt = NormalityTests()
    n = nt.shapiro_wilk(data)
    Q1, Q3 = np.percentile(data, [25, 75]); IQR = Q3 - Q1
    outliers = data[(data < Q1 - 1.5*IQR) | (data > Q3 + 1.5*IQR)]
    return {'size': len(data), 'is_normal': not n.reject_null,
            'p_value': n.p_value, 'outliers': len(outliers)}
```
