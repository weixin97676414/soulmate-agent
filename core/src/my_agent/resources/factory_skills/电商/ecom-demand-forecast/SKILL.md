---
name: ecom-demand-forecast
description: 销量预测与补货：清洗历史销售数据、选模型预测未来销量，给出补货参数与大促备货系数。触发：预测／补货／销量预测／需求预测／库存预测／大促备货／季节性／断货预警。
author: Soulmate Agent团队成员：岸
---

# 销量预测与补货（Forecast & Replenishment）

配套：脚本 `scripts/data-cleaner.py`、`forecast-runner.py`；文件 `assets/forecast-models.md`、`replenishment-params.md`、`promo-coefficients.md`。

## 适用场景

- 根据历史销售数据预测未来销量并生成补货建议，防断货与积压。
- 备战大促、分析库存风险、生成补货计划。
- 触发词：预测、补货、销量预测、需求预测、库存预测、大促备货、季节性、销售曲线、备货计划。

## 步骤

1. **数据准备**：
   必需字段：`date`、`sku`、`quantity`。
   可选字段：`current_stock`、`in_transit`、`lead_time_days`、`safety_days`。
   清洗：
   ```bash
   python3 scripts/data-cleaner.py clean --input raw_sales.csv --output clean_sales.csv
   python3 scripts/data-cleaner.py detect-outliers --input sales.csv
   ```
2. **执行预测**：
   ```bash
   # 单 SKU
   python3 scripts/forecast-runner.py single --sku SKU-001 --input sales.csv \
     --days 30 --stock 500 --lead-time 14 --safety-days 7
   # 批量
   python3 scripts/forecast-runner.py batch --input sales.csv \
     --output forecast_result.csv --days 30
   ```
3. **生成报告**：
   ```bash
   python3 scripts/forecast-runner.py report --forecast forecast_result.csv
   ```
4. **评估准确率（可选）**：
   ```bash
   python3 scripts/forecast-runner.py evaluate --forecast last_month_forecast.csv \
     --actual last_month_actual.csv
   ```

## 预测模型（脚本按数据特征自动选择）

- 移动平均：平稳型商品。
- 指数平滑：有趋势的商品。
- Holt-Winters：有季节性的商品。
- Prophet（可选）：复杂季节性 + 节假日效应。
详见 `assets/forecast-models.md`。

## 补货参数（默认，可覆盖）

| 品类 | 安全库存 | 补货周期 |
|-----|---------|---------|
| 快消品 | 7 天销量 | 14 天 |
| 服装鞋帽 | 14 天销量 | 30 天 |
| 电子产品 | 21 天销量 | 45 天 |

覆盖示例：`--lead-time 20 --safety-days 10`。详见 `assets/replenishment-params.md`。

## 促销活动预测

```
活动预测销量 = 基准日均销量 × 拉升系数 × 活动天数
```
常见系数（详见 `assets/promo-coefficients.md`）：双 11 5x-8x；618 3x-5x；日常满减 1.3x-1.8x。手动算，或自行扩展脚本加 `--promo-factor 6.0` 参数。

## 输入 / 输出

- 预测结果字段：`daily_avg_forecast`、`total_forecast`、`lower_bound`/`upper_bound`、`model_used`。
- 补货建议字段（提供库存参数时）：`reorder_point`、`available_stock`（含在途）、`days_of_stock`、`replenishment_qty`、`priority`（🔴 紧急 / 🟡 正常 / 🟢 可延后）。

## 注意事项

- 数据量建议 ≥30 天，90 天以上更佳。
- 促销期间需标注，否则影响基准预测；预测是概率性的，需结合业务判断。
- 新品无历史数据时，参考同类品系数 × 0.7。
- 依赖安装：`pip install pandas numpy scikit-learn`；`pip install prophet`（可选）。

## 可复用示例

> "这是我 90 天的 SKU 销售数据，预测未来 30 天销量并给补货建议。"
> "双 11 备货该备多少？" / "哪些 SKU 有断货风险？"
