# 多平台商品描述生成（FABE + 平台规则 + 关键词打分）


## 适用场景

- 为任意电商平台生成/优化商品标题、要点、描述、后台关键词。
- 分析竞品为何排名靠前，或改进表现不佳的 Listing。
- 支持平台：Amazon、eBay、Walmart、Shopify/DTC、Etsy、TikTok Shop、Lazada/Shopee。
- 触发词：写产品 listing、商品描述生成、关键词埋词、优化标题描述、FABE。

## 两种模式

| 模式 | 何时用 | 输入 |
|------|--------|------|
| A — Create | 从零写新 listing | 商品规格 + 可选竞品 URL |
| B — Optimize | 优化已有 listing | 现有 listing/URL + 可选竞品 URL |

## 步骤

1. **收集商品信息**：`product_name`、`platform`、`brand`、`key_features`、`specs` 必填；`target_audience`、`use_cases`、`competitor_urls`、`tone`（Professional 默认 / Friendly / Luxury / Urgent）选填。
2. **采集关键词**：
   - 有竞品 URL：`web_fetch` 每个页面，提取标题/要点/描述/价格/评论数/品牌；失败时 `web_search "[标题]" site:[platform].com` 兜底。
   - 无竞品 URL：`web_search` 找同类 top 结果并提取。
   - 关键词分类：产品类型词 / 功能词 / 使用场景词 / 人群词 / 属性词。
   - ⚠️ 必须剔除所有竞品品牌名。
3. **关键词打分（1-9）**：
   | 维度 | 计分 |
   |------|------|
   | 频次 | 3+ 竞品标题=3 / 1-2=2 / 仅要点=1 |
   | 相关性 | 核心描述=3 / 功能=2 / 边缘=1 |
   | 机会 | 少数竞品用=3 / 多数用=2 / 全用=1 |
   分层：🔴 Primary(7-9)→标题；🟡 Secondary(4-6)→要点；🟢 Tertiary(2-3)→描述；⚪ Backend(1)→标签/Search Terms。
4. **（模式 B）差距分析**：列出已有/缺失关键词与建议放置位置，给出覆盖率（目标 ≥90%）。
5. **生成文案（FABE）**：每条要点按 Feature→Advantage→Benefit→Evidence，**先讲利益**。
   - 反例："Made with BPA-free Tritan plastic"
   - 正例："SAFE FOR YOUR FAMILY — BPA-free Tritan plastic means no harmful chemicals leaching into your smoothies, even after 1000+ uses"
6. **按平台规则产出**：
   - Amazon（Cosmo）：Title ≤200；5 Bullets ≤500 each；Desc ≤2000；Backend ≤250 bytes；用情景化语言（when/where/why），覆盖多使用场景。
   - eBay（Cassini）：标题前部放精确匹配词，≤80；描述自然重复 top3 关键词，含规格 HTML 表。
   - Walmart：标题 ≤75；短描述 ≤150；10 条属性要点，一事实一条。
   - Shopify/DTC（Google SEO）：SEO 标题 ≤60；Meta 描述 ≤160；描述用 `<h2>/<ul>/<strong>` 做站内 SEO。
   - Etsy：标题长尾词组优先，≤140；描述前 160 字符=meta；13 个标签 ≤20 字符，与标题短语精确匹配。
   - TikTok Shop：标题 ≤255 以痛点/欲望开头；描述 ≤1000，Hook→痛点→方案→3 要点→CTA，可带 emoji。
   - Lazada/Shopee：标题 ≤120 品牌+产品+型号+材质+属性；5 条要点；描述=参数表+使用场景。

## 输入 / 输出

- 输出：可直接复制的 Title / Bullets / Description / Tags + 诊断报告（关键词优先级表、覆盖地图、被排除的竞品品牌）。

## 注意事项

- 只用公开数据；无实时搜索量与精确数据时明确说明。
- Amazon 专精请走 `references/amazon-optimization.md`。
- 缺输入时先补齐必填项再产出。

## 可复用示例

> "为我的瑜伽垫在 eBay UK 建 listing，竞品链接：…，规格：6mm TPE 防滑，含背带，品牌 ZenMat。"
> "优化这个 Shopify listing 并超越这些竞品：…"
