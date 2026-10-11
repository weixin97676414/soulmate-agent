---
name: strategy-backtesting
description: 股票策略回测（本地脚本）：在历史 OHLCV CSV 上回测 SMA 交叉/RSI 均值回归/突破策略，输出胜率、收益、CAGR、回撤、夏普与交易明细，含研究纪律与常见陷阱。触发：用户要「回测股票策略胜率/测收益率/比较两个策略/从历史价格生成绩效汇总」。
author: Soulmate Agent团队成员：岸
---

# 股票策略回测（本地脚本）


## 适用场景

- 在历史 OHLCV 数据上回测股票交易策略，输出胜率、收益、CAGR、回撤、夏普比率与交易明细。
- 评估或比较策略规则（SMA 交叉、RSI 均值回归、突破）；量化交易成本影响；调参；从 CSV 生成绩效汇总。
- 触发：「回测股票策略胜率」「测收益率」「compare two strategy backtests」「build a strategy report from historical prices」。

## 快速开始

1. 准备 CSV，至少含 `Date` 与 `Close` 两列（`Open/High/Low` 缺失时回退用 `Close`）。
2. 跑基线回测：

```bash
python scripts/backtest_strategy.py \
  --csv /path/to/prices.csv \
  --strategy sma-crossover \
  --fast-window 20 --slow-window 60
```

3. 导出带成本假设的结果：

```bash
python scripts/backtest_strategy.py \
  --csv /path/to/prices.csv \
  --strategy rsi-reversion \
  --rsi-period 14 --rsi-entry 30 --rsi-exit 55 \
  --commission-bps 5 --slippage-bps 2
```

## 步骤

1. **校验数据**：`Date` 可解析且升序；`Open/High/Low/Close` 为数值；缺 `Open/High/Low` 用 `Close` 回退。
2. **选择策略逻辑**：
   - `sma-crossover`：趋势跟随，快/慢均线交叉。
   - `rsi-reversion`：超卖买入，动量恢复卖出。
   - `breakout`：突破高点入场，跌破低点出场。
3. **设置现实假设**：始终设置 `--commission-bps` 与 `--slippage-bps`；不要把无成本回测当作可上线结果。
4. **对比变体**：一次只改一个参数块；同一日期区间、同一成本模型下比较。
5. **产出最终汇总**：报告 `total_return_pct`、`cagr_pct`、`win_rate_pct`、`max_drawdown_pct`、`sharpe_ratio`、`profit_factor` 与交易笔数；用交易明细 CSV 解释 alpha 来源。

## CLI 参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `--csv` | 含 `Date`、`Close` 的 CSV 路径（必填） | — |
| `--strategy` | `sma-crossover` / `rsi-reversion` / `breakout` | — |
| `--initial-capital` | 初始资金 | 100000.0 |
| `--commission-bps` | 佣金（基点） | 5.0 |
| `--slippage-bps` | 滑点（基点） | 2.0 |
| `--risk-free-rate` | 无风险利率 | 0.02 |
| `--fast-window` / `--slow-window` | SMA 快/慢窗口 | 20 / 60 |
| `--rsi-period` / `--rsi-entry` / `--rsi-exit` | RSI 周期/入场/出场 | 14 / 30 / 55 |
| `--lookback` | 突破回看窗口 | 20 |
| `--quiet` | 仅输出 JSON（供自动化管道） | — |

## 输入 / 输出

- **输入**：日线 OHLCV CSV；策略名与参数；成本假设。
- **输出**：stdout 输出 JSON 对象，含 `strategy`、`period`、`metrics`、`config`、`trades`。

## 注意事项（研究纪律）

1. **用样本外逻辑**：优先 walk-forward 验证，而非一次性调参。
2. **避免泄漏**：信号基于第 `t` 根 bar 计算，在第 `t+1` 根 open 执行。
3. **下行与上行一起报**：报收益必须同时给回撤与交易笔数。
4. **结果只是研究**：回测不构成保证，也不构成投资建议。
5. **避免过拟合**：参数搜索空间别太大；多标的、多市场状态验证。
6. **计入交易成本**：默认含佣金与滑点；可测试 0.02%/0.05%/0.1% 敏感性。
7. **防前视偏差**：指标只用历史数据，必要时 `shift(1)`。
8. **数据质量**：检查缺失 bar 与跳空；OHLC 一致性（high ≥ open/close ≥ low）；剔除异常（>10% 日波动通常为错误）。
9. **测试极端情形**：市场崩盘、低波动期、震荡市。
10. **常见陷阱**：前视偏差、幸存者偏差、过拟合、忽略成本、样本过小（<50 笔统计上不显著）、数据窥探。

## 资源

| 文件 | 用途 |
|---|---|
| `scripts/backtest_strategy.py` | 回测主脚本（三种策略、成本模型、JSON 输出契约） |
| `assets/回测_指标说明.md` | 指标定义（return/CAGR/win rate/drawdown/Sharpe/profit factor 等） |

## 可复用示例

**示例 1（SMA 基线）**
> 输入：「用 20/60 均线回测一下这段行情」
> 流程：准备 CSV → `python scripts/backtest_strategy.py --csv prices.csv --strategy sma-crossover --fast-window 20 --slow-window 60` → 解读 metrics 与 trades。

**示例 2（参数对比）**
> 输入：「比较一下 RSI 30/55 和 25/50 的效果」
> 流程：同一 CSV、同一成本下分别跑两次不同 `--rsi-entry/--rsi-exit`，比较 sharpe、win_rate、max_drawdown 与交易笔数。

**示例 3（自动化）**
> 输入：把回测接入管道
> 流程：加 `--quiet` 只取 JSON，供下游解析。
