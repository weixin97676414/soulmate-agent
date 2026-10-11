---
name: credit-risk-modeling
description: 数字金融风控策略建模：数据预处理 → WOE/IV 分箱 → 决策树建模 → 生成风控规则与评分卡。触发：用户要做信用风险/风控建模、评分卡、特征分箱、WOE/IV 与变量筛选、规则引擎，或关注逾期率/坏账率/欺诈检测。
author: Soulmate Agent团队成员：岸
---

# 数字金融科技与风控策略建模


## 适用场景

- 用 Python 处理金融数据、构建风控模型（决策树、分箱）、做特征工程与分箱、分析信用风险、生成风控规则、构建评分卡。
- 触发词：风控、信用评分、风险评估、决策树、分箱、WOE、IV、特征工程、变量筛选、评分卡、规则引擎、逾期率、坏账率、欺诈检测。

## 核心能力

- **Python 数据分析**：pandas、numpy 做数据处理与统计分析。
- **机器学习建模**：决策树、随机森林等算法构建风控模型。
- **特征工程**：WOE 编码、IV 值计算、特征分箱与选择。
- **风控策略**：生成决策规则、构建评分卡、风险分层。

## 工作流程

### 1. 数据预处理

```python
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

# 数据加载与清洗
def load_and_clean_data(file_path):
    df = pd.read_csv(file_path)
    df = df.fillna(df.median())
    for col in numeric_cols:
        q1, q3 = df[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        df = df[(df[col] >= q1 - 1.5*iqr) & (df[col] <= q3 + 1.5*iqr)]
    return df
```

### 2. 特征分箱（WOE/IV）

```python
def calculate_woe_iv(df, feature, target, bins=10):
    df['bin'] = pd.qcut(df[feature], q=bins, duplicates='drop')
    grouped = df.groupby('bin')[target].agg(['sum', 'count'])
    grouped.columns = ['bad', 'total']
    grouped['good'] = grouped['total'] - grouped['bad']
    total_bad = grouped['bad'].sum()
    total_good = grouped['good'].sum()
    grouped['woe'] = np.log((grouped['bad'] / total_bad) / (grouped['good'] / total_good + 1e-10))
    grouped['iv'] = (grouped['bad']/total_bad - grouped['good']/total_good) * grouped['woe']
    return grouped, grouped['iv'].sum()
```

### 3. 决策树建模

```python
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import roc_auc_score

def build_decision_tree_model(X_train, X_test, y_train, y_test, max_depth=5):
    dt = DecisionTreeClassifier(max_depth=max_depth, min_samples_split=50,
                                min_samples_leaf=25, class_weight='balanced')
    dt.fit(X_train, y_train)
    auc = roc_auc_score(y_test, dt.predict_proba(X_test)[:, 1])
    return dt, auc
```

### 4. 风控规则生成

```python
from sklearn.tree import export_text

def generate_risk_rules(tree_model, feature_names):
    return export_text(tree_model, feature_names=feature_names)
```

## 常用指标阈值

| 指标 | 阈值建议 |
|------|---------|
| KS 值 | > 0.2 可接受 |
| AUC | > 0.7 较好 |
| IV 值 | > 0.3 强特征 |
| PSI | < 0.1 稳定 |

## 输入 / 输出

- **输入**：含特征列与目标（good/bad）标签的 CSV；分箱数、树深等超参。
- **输出**：WOE/IV 分箱表与 IV 值；训练好的模型与 AUC/KS；导出的文本决策规则（可转评分卡）。

## 注意事项

- 目标变量需为二分类（如 0/1 好坏标签）；WOE 前须先分箱。
- WOE 计算分母加了 `1e-10` 防止除零，实现时注意。
- IV 高不一定可用，需结合业务可解释性与 PSI（稳定性）判断；PSI ≥ 0.1 说明分布漂移。
- AUC/KS 仅衡量区分度，上线前需评估规则可解释性与合规。
- 本技能无内置脚本，代码需按上例自行落地；示例为可直接套用的骨架，实际运行前需补全 `numeric_cols`、特征与标签列名等。

## 资源

本功能无随附脚本/模板文件，所需代码见上方示例。

## 可复用示例

**示例 1（特征筛选）**
> 输入：含特征与好坏标签的信贷 CSV
> 流程：`load_and_clean_data` 清洗 → 对每个候选特征 `calculate_woe_iv` 算 IV → 保留 IV > 0.3 的强特征 → `build_decision_tree_model` 训练并看 AUC/KS。

**示例 2（规则生成）**
> 输入：训练好的决策树
> 流程：`generate_risk_rules(dt, feature_names)` → 得到可读 if-else 规则，用于规则引擎或评分卡映射。
