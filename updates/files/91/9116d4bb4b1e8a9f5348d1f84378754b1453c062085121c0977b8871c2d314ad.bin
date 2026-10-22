---
name: competitive-research
description: "竞品调研：体验八维 + 战略四件套双轨分析，含可溯源证据库、一次性竞品分析报告与竞品变化监控，产出 HTML/Markdown 报告。触发场景：竞品调研、对标分析、和 XX 比差在哪、竞品材料、赛道里该学谁、竞品监控、功能对比、定价对比、SWOT。"
author: Soulmate Agent团队成员：岸
---

# 竞品调研（体验对标 + 战略诊断）

## 适用场景

- 竞品对标、差异化策略、SWOT/五力/PESTLE、评审前材料。
- 触发词：竞品调研、对标分析、和 XX 比差在哪、benchmark X against Y、竞品材料、赛道里该学谁、竞品策略、能看懂的竞品 HTML 报告。
- 不适用：拍脑袋市场规模、纯概念战略、违规采集、替用户拍板。

## 步骤

```
1) 提交调研需求 → 2) 信息采集清单 → 3) 问题对齐 + 证据建库
→ 4) 双轨分析（体验八维 + 战略四件套） → 5) 按用户选择生成 HTML / Markdown 报告
```

1. **最小可用输入**：调研目标 + 至少 1 个明确竞品（只有 1 个时先问是否补第 2 个；不补则用"我方方案/行业常见做法"作对照并标注口径）。可兼容一句话需求、截图/链接/碎片材料、中英混合输入。
2. **信息采集清单（10 项，预填 + 待补充，可说"跳过，直接生成"）**：调研目标 / 对标对象（≥1，推荐 ≥2）/ 我方现状 / 核心场景 / 行业 / 补充材料 / 战略模块（格局·SWOT·五力·PESTLE）/ 报告用途（内部·对外脱敏）/ 输出格式（HTML·Markdown）/ 约束条件。
3. **采集交互**：**必须复用** `assets/intake-form.html`，不得临时重写表单 UI；上下文预填为 `prefill` URL 参数（URI 编码 JSON），推断值不得伪装成用户确认值，**输出格式保持未选**。宿主支持内嵌 HTML 时直接展示，否则复制资产到输出目录用浏览器打开。回传统一用 `{schema_version:"1.0", skill, action, data}`，优先 `window.codex.submitForm`，兼容 `window.openai.sendFollowUpMessage`，最后复制 JSON。仅当宿主无法展示/打开 HTML 时才退回文本清单；格式未确认不得生成。
4. **双轨分析**：体验轨八维 D1–D8（先拆最小操作节点）；战略轨四项（格局·SWOT·五力·PESTLE，可按需 N/A）。详规见 `assets/research-playbook.md`。
5. **证据建库**：每条关键结论挂 `SRC-xxx`（U 用户 / P 公开 / H 经验须标验证）。
6. **生成报告**：HTML 严格使用 `assets/report-template-pro.html`；Markdown 用同一分区结构。

## 输入输出

- 输入：调研目标、对标对象、我方现状、核心场景、行业、材料、战略模块、用途、格式、约束。
- 输出：报告必含「对标表 · Key Findings · 路线图（Owner/优先级）· Source Index · 免责声明」。对外分享须脱敏。

## 注意事项

- **硬约束**：信息优先（禁止编造、缺失标注、推断透明、清单追问优于脑补）；关键结论至少 1 个 `SRC-xxx`；HTML 公开来源 `SRC-xxx` 必须可点击直接打开对应 URL（同单元格多来源分别生成链接，禁止合并成一个不可点击标签）；无 URL 的用户材料/行业推断/缺口链接到 Source Index 并标注类型；体验轨与策略轨不重复；输出具名、具数、具动作，必有执行建议。
- **优先级**：信息优先 > 格式锁 > playbook > 文风护栏。
- **Rigid（不可跳过）**：SRC-xxx 证据标注 · 信息采集清单先行（用户说"跳过"才可省略）· 报告必含对标表 + Key Findings + 路线图 + Source Index + 免责声明。
- **Flexible**：战略模块选择 · 体验八维可合并相近维度 · 报告格式外的补充附录。
- **失败路径**：清单追问 ≤3 轮未响应 → 标注缺失，以保守假设继续；公开证据不足 → 记录 `SRC-GAP`，不写具体数字，给下一步补证动作；输入很碎 → 先整理为参数与证据索引；无目标无对象且无法推断且用户拒绝补充 → 明确告知无法出具有效报告。
- 表单回归测试：`python scripts/test_intake_form.py`（需本地 Chrome 与 `websocket-client`）。

## 一次性竞品分析报告（功能 / 定价 / SWOT）

与双轨分析互补的实战报告结构，用于快速产出结构化竞品分析（仅用公开信息）：

1. 调研每个竞品：产品概览、功能、定价与套餐、目标客群、定位话术、优势、劣势（常见抱怨）、近期变化。
2. 报告固定结构：
   - 执行摘要（3-5 句：格局 + 关键发现 + 最大机会 + 主要威胁）
   - 竞品档案（成立年份 / 总部 / 定位 / 目标市场 / 差异点）
   - 功能对比矩阵（≥10 项功能，✅/❌）
   - 定价分析（套餐对照 + 价格定位 + 结论）
   - SWOT（每个竞品，每象限 ≥3 点）
   - 市场定位图（价格 × 功能）
   - 机会与威胁
   - 战略建议（30 天 / 本季度 / 6-12 个月）
   - 附录（来源与方法）
3. 输出：`report.md`、`report.html`、`executive-summary.md`、`feature-matrix.csv`。

## 7×24 竞品变化监控（competitor-watch）

持续监控竞品官网 / 产品页 / 定价页 / 博客 / 社交，变化时告警。脚本见 `scripts/`。

### 初始化与添加竞品

```bash
scripts/setup.sh                                    # 初始化配置目录与数据文件
scripts/add-competitor.sh "Acme Corp" https://acme.com \
  --tier fierce --pages pricing,features,blog --tags "direct-competitor"
scripts/check.sh --dry-run                          # 试跑
```

### 定时运行

`check.sh` 每 30-60 分钟巡检；报告 `report.sh --daily-digest`（或 `--alert <change_id>` / `--list`）。

### 分层监控

| tier | 频率 | 监控页面 | 告警门槛 | 快照保留 |
|---|---|---|---|---|
| fierce | 每 30 分钟 | pricing/features/docs/blog/social | 任何有意义变化 | 90 天 |
| important | 每 2 小时 | pricing/features/blog | 中等以上变化 | 30 天 |
| watching | 每天 | homepage/blog | 仅重大变化 | 14 天 |
| adjacent | 每周 | blog/重大公告 | 重大转向或发布 | 7 天 |

### Diff 逻辑

过滤噪声（时间戳、session id、缓存参数、广告位、CMS 痕迹），突出信号（新增功能段、价格变更、导航增删、新博文、>200 字新增）。
分级：Minor（<5%，不告警）/ Medium（5-15%，Important+ 告警）/ Major（>15%、价格、新板块，必告警）/ Critical（含 "launching/announcing/now available" 等词，紧急告警）。

### 调度示例

```bash
*/30 * * * * /path/to/scripts/check.sh --tier fierce
0 */2 * * * /path/to/scripts/check.sh --tier important
0 9 * * * /path/to/scripts/report.sh --daily-digest
```

监控要点：只用公开数据；遵守 robots.txt 与频率限制，不抓取登录 / 付费内容，不做企业间谍；fierce 只留 2-3 家、设冷却期避免告警轰炸。

## B2B SaaS 垂直场景补充

按四维导航（行业垂直 / 公司阶段 / 主要市场 / 研究者角色），覆盖 24 个场景：
- **Section A Sales Tech**（Gong/Outreach/Salesloft；买家 Sales leaders/CRO/RevOps）
- **Section B HR Tech**（Culture Amp/Lattice/BambooHR）
- **Section C Fintech**（Razorpay/Happay/Stripe）
- **Section D Operations Tech**（物流/零售）
- 阶段路径：Series A / Series B-C / Series D+；市场：India-first / US-first / 全球。
适用于 B2B SaaS 建 battle card、涨价/上探市场、董事会市场格局、市场规模测算。全文见 `assets/b2b-saas-competitive-intelligence.md`。

## 可复用示例

输入（口语）：「我们这个功能和小红书/抖音比差在哪？」，或「帮我拉一版 XX 和 YY 的竞品对标」。
做法：先出采集清单（复用 intake-form）→ 用户确认格式 → 体验八维 + 战略轨分析 → 每条结论挂 `SRC-xxx` → 生成可点击溯源 URL 的 HTML 报告。

## 配套文件

- `assets/research-playbook.md`：双轨四层法详规 · 事实边界 · 格式锁 · 自检。
- `assets/report-template-pro.html`：HTML 报告模板。
- `assets/intake-form.html`：跨 Agent 可复用采集表 UI。
- `assets/b2b-saas-competitive-intelligence.md`：B2B SaaS 24 场景全文。
- `scripts/test_intake_form.py`：本地 Chrome 表单回归测试。
- `scripts/setup.sh`、`add-competitor.sh`、`check.sh`、`diff.sh`、`report.sh`、`config.example.json`：竞品变化监控（competitor-watch）的初始化、添加竞品、巡检、差异评分与告警。
