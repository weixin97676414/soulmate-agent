---
name: onequant-platform
description: OneQuant 4.0 本地量化交易系统：本地 Flask 平台 + 102 个 REST API，支持 Web/API/CLI/批量脚本/Docker 五种调用方式，做回测、选股、模拟交易、风控与导出。触发：用户要本地量化平台（回测/选股/模拟交易/导出交易记录/风险概览），或用 MA/RSI 策略回测 A 股。
author: Soulmate Agent团队成员：岸
---

# OneQuant 4.0 本地量化交易系统


## 适用场景

- A股个人投资者策略验证、量化学习入门、Python 数据分析师批量研究。
- 触发示例：「帮我回测贵州茅台 MA 策略」「筛选今天涨停的股票」「查看自选股风险概览」「导出交易记录 Excel」。
- **不适用**：高频交易（HFT）；实盘自动下单（需自行对接券商）；期货期权（仅 A 股）；港美股深度分析（有限支持）。

## 系统架构

```
OneQuant 4.0
├── run.py                    # Flask 主入口（102 个 API）
├── frontend/                 # SPA 单页应用（14 个功能 Tab，ECharts，涨红跌绿配色）
├── backend/
│   ├── data/                 # 6 个数据源适配器
│   │   ├── akshare_adapter.py  # AkShare（免费，默认）
│   │   ├── jq_adapter.py       # JQData（聚宽，付费）
│   │   ├── rq_adapter.py       # RQData（米筐，付费）
│   │   ├── ths_adapter.py      # 同花顺 iFinD（预留）
│   │   ├── itick_adapter.py    # iTick WebSocket 实时行情
│   │   └── dual_adapter.py     # 双数据源融合/降级
│   ├── broker/               # 券商对接（工厂模式）
│   │   ├── mock_broker.py      # 模拟券商（默认）
│   │   ├── mini_qmt_adapter.py # 华泰 miniQMT
│   │   ├── ifind_adapter.py    # 同花顺 iFinD
│   │   └── eastmoney_adapter.py# 东方财富掘金
│   ├── risk_manager.py       # 风控引擎
│   ├── conditional_order.py  # 条件单引擎
│   └── data_store.py         # JSON 文件持久化
└── scripts/                  # CLI + 批量工具
```

## 快速开始

```bash
pip install flask flask-cors pandas akshare openpyxl
python run.py
# 访问 http://127.0.0.1:5001

# Docker
docker build -t onequant .
docker run -d -p 5001:5001 --name onequant onequant
```

### 安装验证（四项全 `"success": true` 即成功）

```bash
curl http://127.0.0.1:5001/health
curl http://127.0.0.1:5001/api/system/version
curl "http://127.0.0.1:5001/api/stock/info?code=600519"
curl "http://127.0.0.1:5001/api/market/kline?symbol=600519&frequency=daily"
```

## 调用方式（5 种）

| # | 方式 | 适用人群 | 难度 | 典型场景 | 响应 |
|---|------|---------|------|---------|------|
| ① | Web 界面 | 所有人 | ⭐ | 看行情、K线、手动交易 | GUI |
| ② | REST API | Python 开发者 | ⭐⭐ | 批量回测、策略研究、系统集成 | JSON |
| ③ | CLI 命令行 | 终端用户 | ⭐⭐ | 快速查询、脚本自动化 | 文本 |
| ④ | 批量脚本 | 量化研究员 | ⭐⭐⭐ | 多股票并行回测、定时任务 | Excel/Markdown |
| ⑤ | Docker | DevOps/服务器 | ⭐⭐⭐ | 部署到服务器 | Web API |

### ② REST API

所有 API 返回标准 JSON：`{"success": true, "data": {...}, "message": "ok"}`

```bash
curl "http://127.0.0.1:5001/api/market/kline?symbol=600519&frequency=daily"
curl "http://127.0.0.1:5001/api/backtest/ma?symbol=600519&short=5&long=20"
curl "http://127.0.0.1:5001/api/market/industry_rank"
```

```python
import requests
BASE = "http://127.0.0.1:5001"
r = requests.get(f"{BASE}/api/backtest/ma", params={"symbol": "600519", "short": 5, "long": 20})
print(r.json()["data"]["total_return"])
```

### ③ CLI

```bash
python scripts/cli.py health
python scripts/cli.py stock 600519
python scripts/cli.py kline 600519 --freq daily --count 30
python scripts/cli.py backtest 600519 --strategy ma --short 5 --long 20
python scripts/cli.py select --strategy limit_up --limit 20
python scripts/cli.py export trades
```

### ④ 批量回测

```bash
python scripts/batch_backtest.py --input watchlist --strategy ma --output report.md
python scripts/batch_backtest.py --input 600519,000858,601012 --strategy rsi --output results.json
```

配合 Windows 计划任务或 Linux cron，可每日自动批量回测并生成报告。

### ⑤ Docker

```bash
docker run -d -p 5001:5001 -v ~/onequant_data:/app/data --name onequant onequant:4.0
```

## 功能模块与 API 索引（14 模块 / 102 端点）

| 模块 | 关键端点 | 说明 |
|------|----------|------|
| 1 大盘分析 Market | `/api/market/overview`、`market_stat`、`industry_rank`、`northbound_flow`、`index_minute?idx=sh/sz/cyb`、`limit_up`、`realtime_quote?code=`、`concept_rank`、`dragon_tiger`、`stock_news?code=`、`stock_financials?code=` | 指数、涨跌、北向、龙虎榜等 |
| 2 K线分析 Kline | `/api/market/kline?symbol=&frequency=` | 周期：`1min/5min/15min/30min/60min/120min/daily/weekly/monthly` |
| 3 技术信号 Signal | `/api/signal/technical?symbol=&frequency=` | MACD/KDJ/RSI + 买卖点 |
| 4 量化选股 Selection | `/api/selection/list?strategy=` | `limit_up` 涨停板 / `ma_golden` 均线金叉 / `rsi_oversold` RSI 超卖 |
| 5 回测中心 Backtest | `/api/backtest/run`、`/ma`（`symbol/short=5/long=20`）、`/rsi`（`oversold=30/overbought=70`）、`list`、`save`、`detail?id=`、`delete`、`compare` | 回测入口与记录管理 |
| 6 股票信息 Stock | `/api/stock/info?code=`、`order_book?code=`、`order_book_10`、`financial?code=` | 基本信息/盘口/财务 |
| 7 交易中心 Trade | `/api/trade/holdings`、`buy`、`sell`、`buy_market`、`sell_market`、`history`、`account_summary`、`daily_pnl`、`reset_account`、`one_click_buy`、`one_click_sell`、`cancel_order` | 模拟交易 |
| 8 风控管理 Risk | `/api/risk/overview`、`risk/config`、`stop_loss/config?code=&stop_loss=&take_profit=` | 风险概览与止损止盈 |
| 9 策略管理 Strategy | `/api/strategy/list`、`add`、`delete`、`detail`、`toggle`、`backtest_history` | 策略 CRUD |
| 10 自选股 Watchlist | `/api/watchlist/list`、`add`、`delete`、`reorder`、`alert`、`alerts` | 自选与提醒 |
| 11 条件单 Conditional | `/api/conditional/list`、`create`、`cancel`、`check` | 条件单 |
| 12 券商对接 Broker | `/api/broker/list`、`connect`、`disconnect`、`status`、`account`、`positions`、`orders`、`trades`、`order`、`cancel`、`test` | 工厂模式，默认模拟券商 |
| 13 数据分析 Analysis | `/api/analysis/trend?symbol=`、`chip?code=` | 趋势（均线/布林带）、筹码分布 |
| 14 暗盘数据 Darkpool | `/api/darkpool/overview`、`bulk_detail?code=`、`fund_flow?code=` | 暗盘/资金流 |
| 系统管理 | `/api/system/version`、`status`、`logs?lines=`、`config/get`、`config/save`、`settings/*`、`notification/list`、`jqdata/test`、`rqdata/test`、`/api/docs`、`/health` | 版本/状态/配置 |
| 数据导出 Export | `/api/export/trades`、`backtest?symbol=&strategy=`、`holdings`、`strategy`、`watchlist` | 导出 Excel |
| 账户管理 | `/api/account/register`、`login`、`logout`、`profile` | 本地账户 |

> 完整请求/响应示例见 `assets/OneQuant_API示例.md`。

## 数据源

- 支持 AkShare（免费，默认）/ JQData（聚宽，付费）/ RQData（米筐，付费）三源热切换；配置见系统设置。
- 数据源适配器目录：`backend/data/`。
- 用户咨询 FAQ 见 `assets/OneQuant_FAQ.md`。

## 批量/自动化示例

```python
# 每天 15:30 自动回测自选股（配合 Windows 计划任务或 cron）
import requests
from datetime import datetime
BASE = "http://127.0.0.1:5001"
WATCHLIST = ["600519", "000858", "601318", "300750", "002594"]
for code in WATCHLIST:
    r = requests.get(f"{BASE}/api/backtest/ma", params={
        "symbol": code, "short": 5, "long": 20,
        "start_date": "2024-01-01", "end_date": datetime.now().strftime("%Y-%m-%d")
    }, timeout=15)
    if r.json().get("success"):
        d = r.json()["data"]
        print(f"{code}: 收益{d.get('total_return','?')}% 夏普{d.get('sharpe','?')}")
```

## 数据隐私与安全

- 所有交易记录、策略参数、持仓数据存本地 JSON 文件，不上传远程服务器。
- JQData/RQData 账号密码存本地 `config.json`，建议加入 `.gitignore`，勿分享。
- 导出需用户主动触发，系统不会自动外发；彻底删除数据即删除 `strategies.json` / `trades.json` / `watchlist.json` 及 `backend/data/` 缓存。
- 性能：GIL 限制下并发回测建议不超过 5 个并发。

## 注意事项

- 默认数据源为 AkShare（免费）；付费源需在配置中填写凭据。
- 实盘下单不内置，需自行对接券商。
- 数据质量/精度与更新频率有已知限制（见源文档「数据质量说明/精度保证矩阵/性能并发限制」）。
- 本地部署路径因机器而异，本文件不假定固定安装目录。

## 资源

| 文件 | 用途 |
|---|---|
| `assets/OneQuant_API示例.md` | 每个 API 的 curl/Python 示例、参数与响应样例 |
| `assets/OneQuant_FAQ.md` | 常见问题 |

## 可复用示例

**示例 1（回测）**
> 输入：「用 MA 金叉死叉策略回测 000858，区间 2019-01-01 到 2024-12-31，短 5 长 20」
> 流程：启动服务 → `curl "http://127.0.0.1:5001/api/backtest/ma?symbol=000858&short=5&long=20"`（或 CLI `backtest 000858 --strategy ma --short 5 --long 20`）→ 解读 total_return/sharpe/max_drawdown。

**示例 2（选股）**
> 输入：「筛选今天涨停的股票，列出前 10 只」
> 流程：`python scripts/cli.py select --strategy limit_up --limit 20`。

**示例 3（批量）**
> 输入：「批量回测我的自选股」
> 流程：`python scripts/batch_backtest.py --input watchlist --strategy ma --output report.md`。
