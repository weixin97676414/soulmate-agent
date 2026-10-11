---
name: quant-risk-dashboard
description: 量化交易风险仪表盘：RiskDashboard 计算 VaR/CVaR/最大回撤/Sharpe 等指标，做仓位限额、敞口监控、压力测试、告警与 Dash 可视化报告。触发：用户要组合风险监控、压力测试、风险指标可视化、回撤预警或合规风险报告。
author: Soulmate Agent团队成员：岸
---

# 量化交易风险仪表盘


## 适用场景

- 量化交易组合的实时风险管理：VaR/CVaR、压力测试、仓位限额、敞口监控、回撤预警、风险指标可视化。
- 用途：实盘风险监控、回测后风险分析、多策略组合风险、合规风险报告、策略风险画像。

## 边界

本技能只做组合层面的量化风险仪表盘（VaR/CVaR/回撤/敞口/限额/压力测试/告警）。个人持仓买卖点、止盈止损与仓位心理指导不在本技能范围。

## 功能

1. **风险指标**：VaR（历史/参数/蒙特卡洛）、CVaR（期望损失）、最大回撤（当前与历史）、波动率（已实现/隐含）、Beta、Sharpe/Sortino/Calmar。
2. **仓位管理**：实时持仓与盈亏、个股与总仓位限额、集中度风险（单仓最大%）、行业敞口。
3. **敞口监控**：多空比与净敞口、行业配置、因子敞口（价值/成长/动量）、市值/地区敞口。
4. **压力测试**：历史情景（2008 崩盘、2020 疫情等）、自定义冲击、情景对比、恢复时间估计。
5. **告警**：回撤阈值告警、仓位越限告警、波动率飙升、自定义规则。
6. **报告**：每日风险报告（PDF/HTML）、风险归因（盈亏的因子解释）、合规报告、自定义报告。

## 安装

```bash
pip install pandas numpy scipy plotly dash
```

## 使用

### 初始化

```python
from quant_risk import RiskDashboard

dashboard = RiskDashboard(
    initial_capital=1000000,
    var_confidence=0.95,
    max_position_pct=0.15,
    max_drawdown_pct=0.20
)
```

### 添加持仓

```python
dashboard.add_position(symbol='600519', shares=1000, entry_price=1800.0, current_price=1850.0)
dashboard.add_position(symbol='000858', shares=5000, entry_price=45.0, current_price=48.0)
```

### 取风险指标

```python
metrics = dashboard.get_risk_metrics()
print(f"VaR (95%): {metrics['var_95']:,.2f}")
print(f"CVaR (95%): {metrics['cvar_95']:,.2f}")
print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
print(f"Total Exposure: {metrics['total_exposure']:,.0f}")
```

### 压力测试

```python
scenarios = {'2008 Crash': -0.50, '2020 Covid': -0.30, 'Rate Hike': -0.15, 'Custom': -0.25}
results = dashboard.stress_test(scenarios)
for name, result in results.items():
    print(f"{name}: P&L = {result['pnl']:,.2f}")
```

### 启动 Web 仪表盘

```python
dashboard.start_dashboard(port=8050)
# 访问 http://localhost:8050
```

## API 参考

| 分类 | 方法 | 说明 |
|------|------|------|
| 核心 | `add_position(symbol, shares, entry, current)` | 加仓 |
| 核心 | `remove_position(symbol)` | 平仓 |
| 核心 | `update_price(symbol, price)` | 更新市价 |
| 核心 | `get_positions()` | 取全部持仓 |
| 核心 | `get_risk_metrics()` | 计算风险指标 |
| 风险分析 | `calculate_var(method='historical')` | 计算 VaR |
| 风险分析 | `calculate_cvar()` | 计算 CVaR |
| 风险分析 | `stress_test(scenarios)` | 压力测试 |
| 风险分析 | `factor_exposure()` | 因子敞口 |
| 风险分析 | `sector_allocation()` | 行业分布 |
| 告警 | `add_alert(condition, message)` / `get_alerts()` / `clear_alerts()` | 告警管理 |
| 报告 | `generate_report(format='pdf')` / `get_daily_summary()` | 报告 |

## 指标释义

- **VaR**：给定置信度下的最大预期损失。「95% VaR = 50,000」= 95% 概率损失 < 50,000。
- **CVaR**：VaR 阈值之外的平均损失，比 VaR 更保守。
- **Sharpe**：风险调整收益，>1.0 好，>2.0 优秀。
- **Max Drawdown**：峰谷最大跌幅，越小越好。
- **Sortino**：只惩罚下行波动的风险调整收益。

## 配置

### 风险限额

```python
limits = {
    'max_position_pct': 0.15,    # 单仓位 15%
    'max_sector_pct': 0.30,      # 单行业 30%
    'max_leverage': 1.5,         # 1.5 倍杠杆
    'max_drawdown': 0.20,        # 20% 止损
    'max_var_pct': 0.05,         # 5% VaR 限额
}
```

### 告警阈值

```python
alerts = {
    'drawdown_warning': 0.10,    # 10% 回撤预警
    'drawdown_critical': 0.15,   # 15% 严重
    'var_warning': 0.03,         # 3% VaR 预警
    'volatility_spike': 2.0,     # 2 倍正常波动
}
```

## 可视化

```python
dashboard.start_dashboard()          # 实时持仓表、P&L 图、风险仪表、行业饼图、回撤曲线、因子敞口柱
chart = dashboard.plot_pnl_history()
chart = dashboard.plot_risk_attribution()
chart = dashboard.plot_scenarios()
```

## 集成

### 对接交易系统（定时刷新）

```python
import asyncio

async def update_positions():
    while True:
        positions = await trading_system.get_positions()
        for pos in positions:
            dashboard.update_price(pos.symbol, pos.current_price)
        await asyncio.sleep(60)      # 每分钟更新

asyncio.run(update_positions())
```

### Webhook 告警

```python
def on_alert(alert):
    send_webhook(url=os.getenv('ALERT_WEBHOOK'), message=f"Risk Alert: {alert['message']}")

dashboard.set_alert_callback(on_alert)
```

## 输入 / 输出

- **输入**：初始资金、VaR 置信度、仓限额、回撤限额；持仓（代码/股数/成本/现价）；压力情景字典。
- **输出**：风险指标 dict；压力测试各情景 P&L；Dash Web 仪表盘（本地端口）；PDF/HTML 报告。

## 注意事项

- 依赖 pandas / numpy / scipy / plotly / dash。
- Web 仪表盘在本地端口启动（默认 8050）。
- Webhook URL 走环境变量（如 `ALERT_WEBHOOK`），勿硬编码。
- 指标仅为风险度量，不构成投资建议。

## 资源

| 文件 | 用途 |
|---|---|
| `scripts/quant_risk.py` | RiskDashboard 实现（持仓、VaR/CVaR、压力测试、可视化、报告） |

## 可复用示例

**示例 1（组合风险体检）**
> 输入：持仓列表（600519 1000 股 @1800→1850；000858 5000 股 @45→48）
> 流程：`RiskDashboard(initial_capital=1000000, var_confidence=0.95)` → `add_position` 逐条 → `get_risk_metrics()` 输出 VaR/CVaR/Sharpe/MaxDD/敞口。

**示例 2（压力测试）**
> 输入：「看看我这组合遇到 2008 级别崩盘会怎样」
> 流程：`stress_test({'2008 Crash': -0.50, '2020 Covid': -0.30, 'Rate Hike': -0.15})` → 逐情景输出 P&L 与恢复时间。
