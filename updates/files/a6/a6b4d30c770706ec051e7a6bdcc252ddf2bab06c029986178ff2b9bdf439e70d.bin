---
name: equity-valuation
description: 价值投资估值分析（护城河 / 财务健康 / DCF）：十分钟测试 + 五步护城河 + 六危险信号 + DCF 安全边际 + 投资决策矩阵，含同业对比与 Watchlist 目标价监控。触发：用户要评估一只股票（A 股/港股）的投资价值、护城河、内在价值/DCF、安全边际、管理层质量或行业结构。
author: Soulmate Agent团队成员：岸
---

# 价值投资估值分析（护城河 / 财务健康 / DCF）


## 适用场景

- 综合评估一只股票的投资价值；评估经济护城河与竞争优势；检查财务健康与会计质量；用 DCF 算内在价值；评估管理层质量；分析行业结构与动态；整合出投资决策。
- 覆盖 A 股与港股（港股通标的支持较好）。
- 触发：分析某股票投资价值、护城河、内在价值、DCF、安全边际、管理层评估、行业结构。

## 边界

本技能只做定量估值（DCF、倍数、安全边际）与配套的财务健康检查、决策矩阵。管理层与护城河的定性尽调不在本技能范围，相关定性判断只作为估值输入假设。

## 数据准备

- 优先基于公司最新财报数据：建议上传**年度报告**（首选）、中期报告、业绩公告/演示文稿。
- 若无财报数据：用公开数据源（AKShare 等）获取最新财务数据，并明确标注数据来源与时效性；重要决策建议等最新财报发布后复核。
- 财报为 PDF 格式时，先用可用的 PDF 文本提取工具抽出财务数据，再录入分析。

## 步骤

### 场景 1：全面分析一家新公司

```bash
# Step 1: 获取基础数据（估值快照：实时 PE/PB/股息率及历史分位）
python scripts/valuation_snapshot.py <代码> [--market A|HK]

# Step 2: 护城河分析 - 五步检验法（见 assets/估值_护城河分析.md）

# Step 3: 财务健康检查 - 六个危险信号（见 assets/估值_财务健康检查.md）

# Step 4: DCF 估值
python scripts/dcf_calculator.py --fcf <FCF亿> --growth "<5年增速,逗号分隔>" \
  --terminal <永续增速> --discount <折现率> --net-debt <净负债亿> \
  --shares <总股本亿股> --current-price <当前股价>

# Step 5: 综合评分与决策（见 assets/估值_投资决策整合框架.md）
```

### 场景 2：快速筛选潜在标的

```bash
python scripts/watchlist_manager.py check          # 估值预警
```

护城河与财务红旗可单独跑：

```bash
# 护城河评分
python scripts/moat_analyzer.py --company "<公司名>" \
  --fcf-margin 0.05 --net-margin 0.15 --roe 0.15 --roa 0.07 \
  [--years 5] [--sources "<来源>"] [--width wide|narrow|none] [--industry "<备注>"] [--json]

# 财务危险信号检查
python scripts/red_flag_checker.py --company "<公司名>" \
  --revenue-current <亿> --revenue-prior <亿> \
  --net-income-current <亿> --net-income-prior <亿> \
  --operating-cf-current <亿> --operating-cf-prior <亿> \
  --receivables-current <亿> --receivables-prior <亿> \
  --inventory-current <亿> --inventory-prior <亿> \
  [--nonrecurring-count N] [--acquisition-count N] [--market-cap 100] \
  [--cfo-departure] [--auditor-change] [--json]
```

### 场景 3：定期监控持仓

```bash
python scripts/watchlist_manager.py check          # 估值预警
```

### 场景 4：同业对比

```bash
python scripts/industry_compare.py --industry 白酒 --stock 000858        # 内置行业映射
python scripts/industry_compare.py --codes "000858,000568,600519,600809" --stock 000858
```

### Watchlist 管理

```bash
python scripts/watchlist_manager.py add <代码> --name <名称> \
  --pe-low <买入PE> --pe-high <卖出PE> --notes "备注"
python scripts/watchlist_manager.py list
python scripts/watchlist_manager.py check
```

### DCF 示例（五粮液）

```bash
python scripts/dcf_calculator.py \
  --fcf 250 --growth "0.12,0.10,0.08,0.06,0.05" \
  --terminal 0.03 --discount 0.09 --net-debt -100 \
  --shares 38.8 --current-price 142
```

## 十分钟测试（进入深度分析前）

用 10 分钟回答 9 个问题，**全部通过**才进入深度分析：

1. 公司一直不断地赚取营业利润吗？（盈利持续性）
2. 公司能从经营活动中持续不断地产生现金流吗？（现金流质量）
3. 净资产收益率能保持 10% 以上，并且有合理的财务杠杆吗？（资本效率）
4. 盈利增长是协调一致还是飘忽不定？（增长稳定性）
5. 资产负债表清白吗？（财务风险）
6. 这家公司产生自由现金流吗？（真实现金创造）
7. 还有多少「其他」？（利润质量/非经常性损益）
8. 发行在外的股票数量在过去几年明显增长了吗？（股本稀释）
9. 做一个大致的折现现金流估值。（估值吸引力）

## 关键阈值速查

| 指标 | 优秀 | 一般 | 危险 |
|------|------|------|------|
| ROE | > 15% 连续 5 年+ | 10–15% | < 10% |
| FCF/销售额 | > 5% | 0–5% | < 0% |
| 毛利率 | > 40% | 20–40% | < 20% |
| 负债/权益 | < 1.0 | 1.0–1.5 | > 1.5 |
| 安全边际 | > 20% | 10–20% | < 10% |
| 流动比率 | > 1.5 | — | < 1.0 |
| 已获利息倍数 | > 5 | — | < 3 |

### 买入前清单（一页纸版）

- 护城河：历史盈利能力达标（FCF/销售 > 5%、ROE > 15% 连续 5 年+）、来源清晰（网络效应/转换成本/品牌/成本优势）、宽度为「宽」或「极宽」。
- 财务：无六个危险信号；负债/权益 < 1.0，流动比率 > 1.5；毛利率/净利率稳定或提升。
- 估值：DCF 算内在价值；安全边际 ≥ 20%（好公司）/ ≥ 40%（一般公司）。
- 管理层：资本配置记录良好、无诚信红旗。
- 综合：评分 ≥ 4.0（好公司）/ ≥ 3.5（一般公司）。

### 卖出信号

股价 > 内在价值（无安全边际）；护城河被侵蚀；财务健康恶化（3+ 危险信号）；管理层诚信问题；发现明显更优机会。

## DCF 参数（晨星标准）

| 参数 | 好公司（强护城河） | 一般公司 | 高风险公司 |
|------|-------------------|----------|-----------|
| 折现率 | 9% | 10.5% | 13–15% |
| 永续增速 | 3% | 3% | 2% |
| 预测期 | 10 年 | 10 年 | 10 年 |

折现率 6 个调整因素：公司规模（小 +1–2%）、财务杠杆（高负债 +1–2%）、周期性（周期股 +1–2%）、管理层可信度（有问题 +1%）、竞争优势（弱 +1–2%）、业务复杂性（复杂 +1%）。

安全边际：

```
安全边际 = (内在价值 - 当前股价) / 内在价值 × 100%
```

| 公司类型 | 安全边际要求 | 操作建议 |
|----------|-------------|----------|
| 强竞争优势稳定公司 | 20% | 打折买入 |
| 一般公司 | 30–40% | 等待更好价格 |
| 高风险公司 | 60% | 只有深度低估才考虑 |

## 护城河 / 财务健康要点（详见 assets）

- **护城河五步检验**：评估历史盈利能力 → 识别来源（产品差异化/品牌/成本优势/转换成本/网络效应/进入壁垒）→ 评估宽度（宽 10–20 年 / 窄 5–10 年 / 无）→ 行业竞争结构（CR5、平均毛利率、进入壁垒）。详见 `assets/估值_护城河分析.md`。
- **六个危险信号**：现金流衰退；连续非经常性费用（3 年 ≥ 2 次）；连续收购；CFO/审计师离职；应收账款增速 > 收入增速；赊销条件变更。详见 `assets/估值_财务健康检查.md`。

## 输入 / 输出

- **输入**：股票代码 + 市场（A/HK）；最新财报数据或 PDF；DCF 假设（FCF、增速、折现率、净负债、股本、现价）。
- **输出**：估值快照、DCF 内在价值与安全边际、同业对比、护城河评分、财务红旗清单、综合评分与买卖决策矩阵；可落盘到 Watchlist 做目标价监控。

## 注意事项

- 免费数据源 AKShare 偶尔不稳定，关键决策前交叉验证。
- 历史分位用价格分位近似估值分位；个股历史 PE/PB 需付费数据源。
- 港股通标支持较好，纯港股数据可能不完整。
- DCF 内在价值对假设高度敏感，建议做乐观/中性/悲观情景分析。
- 本技能结果仅供参考，不构成投资建议。

## 资源

| 文件 | 用途 |
|---|---|
| `scripts/valuation_snapshot.py` | 实时 PE/PB/股息率及历史分位 |
| `scripts/dcf_calculator.py` | DCF 内在价值 |
| `scripts/industry_compare.py` | 同业估值横向对比 |
| `scripts/watchlist_manager.py` | 目标价监控与预警 |
| `scripts/moat_analyzer.py` | 护城河评分 |
| `scripts/red_flag_checker.py` | 财务危险信号检查 |
| `scripts/requirements-valuation.txt` | 依赖（akshare/pandas/numpy/rich/tabulate/requests/python-dateutil） |
| `assets/估值_护城河分析.md` | 五步检验法 |
| `assets/估值_财务健康检查.md` | 六步健康检查与会计质量 |
| `assets/估值_管理层评估.md` | 能力/诚信/股东导向三维 |
| `assets/估值_行业分析.md` | 生命周期定位与行业指标 |
| `assets/估值_投资决策整合框架.md` | 综合评分与买卖决策矩阵 |
| `assets/估值_使用指南.md` | 详细使用指南 |

## 可复用示例

**示例 1（全面分析）**
> 输入：「分析一下五粮液的投资价值」
> 流程：`valuation_snapshot.py 000858` → 十分钟测试 → 护城河五步 → `red_flag_checker.py` 六危险信号 → `dcf_calculator.py --fcf 250 --growth "0.12,0.10,0.08,0.06,0.05" --terminal 0.03 --discount 0.09 ...` → `industry_compare.py --industry 白酒 --stock 000858` → 按投资决策框架给评分与结论。

**示例 2（监控持仓）**
> 输入：「帮我盯着这几个票的估值，到目标价提醒我」
> 流程：`watchlist_manager.py add` 逐只设买入/卖出 PE 与备注 → 定期 `check` 触发预警。
