---
name: product-listing-copy
description: 多平台商品描述生成（listing 层）：按 FABE 与平台规则产出标题／要点／描述／后台关键词，支持跨境多平台多语种 A/B 多版本、本地化与合规检查。触发：写产品 listing／商品描述生成／关键词埋词／优化标题描述／FABE／跨境文案／多语种 listing／A/B 测试文案／小语种商品描述。
author: Soulmate Agent团队成员：岸
---

# 多平台商品描述生成（FABE + 平台规则 + 关键词打分 + 跨境多语种 A/B）

配套脚本：`scripts/cross_border_copywriter.py`（配置说明 `scripts/requirements.txt`，部署自检 `scripts/start.sh`）。

## 适用场景

- 为任意电商平台生成/优化商品标题、要点、描述、后台关键词。
- 分析竞品为何排名靠前，或改进表现不佳的 Listing。
- 支持平台：Amazon、eBay、Walmart、Shopify/DTC、Etsy、TikTok Shop、Lazada/Shopee、SHEIN、Temu。
- 跨境多语种：en/zh/bilingual/es/fr/de/ja/ar；需要 A/B 测试多版本、小语种适配、合规检查、字符长度自动适配。
- 触发词：写产品 listing、商品描述生成、关键词埋词、优化标题描述、FABE、跨境文案、多语种 listing、A/B 测试文案、多版本标题、小语种商品描述。
- **边界**：只做 listing 层文案（标题／要点／描述／后台关键词）与竞品埋词分析，支持跨境多平台多语种 A/B；国内平台的详情页七模块文案与整店视觉不在范围内。

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
   - SHEIN / Temu：标题 ≤80；短描述 ≤100；详情页单段 ≤300；卖点单条 ≤80。

## 跨境多语种生成（A/B 多版本 + 合规 + 字符适配）

适用于 Amazon、SHEIN、Temu、Shopee、TikTok Shop 的多平台、多语种、多风格商品文案。

### 输入参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| product_name | 字符串 | 是 | 商品名（小语种生成时自动翻译适配） |
| category | 字符串 | 否 | 3C/服装/家居/美妆/户外/家电/饰品等 |
| platform | 字符串 | 否 | Amazon/Shopee/Temu/TikTok（默认 Amazon） |
| language | 字符串 | 否 | en/zh/bilingual/es/fr/de/ja/ar（默认 en） |
| keywords | 数组 | 否 | SEO 关键词（支持小语种，自动融入） |
| features | 数组 | 否 | 卖点（材质/功能/尺寸等） |
| tone | 字符串 | 否 | professional/marketing/luxury/casual（默认 professional） |
| length | 字符串 | 否 | short(标题)/medium(短描述)/long(详情)（默认 long） |
| ab_version | 数字 | 否 | A/B 版本数 1-5（默认 1） |
| ab_diff_type | 字符串 | 否 | keyword/tone/structure/content（默认 keyword） |

### 处理流程

1. **生成文案**：关键词自然植入 → 平台风格适配 → 卖点结构化为 bullet points → 多语种输出。
2. **A/B 多版本**：按 `ab_diff_type` 只在指定维度变化（keyword 词序 / tone 风格 / structure 结构 / content 侧重点），保留核心卖点与关键词一致。
3. **小语种本地化**：阿拉伯语适配从右到左；日语适配敬语；西/法/德适配当地营销话术并避免文化禁忌。
4. **合规检查**：内置侵权词/违禁词库扫描并同义替换；无法替换时提示用户修改；覆盖多语种（如欧盟 CE 表述、阿语宗教禁忌）。
5. **字符长度适配**：按平台各模块字符上限自动压缩/扩充，小语种调整计数逻辑。

### 输出结构（JSON）

```json
{
  "ab_version_count": 2,
  "ab_diff_type": "keyword",
  "versions": [
    {
      "version": "A",
      "title": "...", "short_description": "...", "long_description": "...",
      "bullet_points": ["..."], "tags": ["..."],
      "language": "de", "platform_fit": "Amazon",
      "compliance_check": {"status": "通过", "suggestion": ""},
      "character_adaptation": {"title": "138字符（≤200字符，符合Amazon要求）"}
    }
  ]
}
```

### 运行方式

```bash
# 直接运行（执行测试代码，输出示例文案）
python3 scripts/cross_border_copywriter.py
```
```python
from cross_border_copywriter import CrossBorderCopywriter
params = {"product_name":"便携式无线蓝牙耳机","category":"3C数码","platform":"Amazon",
          "language":"de","keywords":["drahtlose Ohrhörer","Bluetooth 5.3"],
          "features":["降噪","长续航"],"ab_version":2,"ab_diff_type":"keyword"}
result = CrossBorderCopywriter().generate_copy(params)
print(result)
```
运行环境：Python 3.7+，无额外依赖库（原生库）。调整平台字符上限可改脚本内 `platform_char_limit` 配置。

## 输入 / 输出

- 输出：可直接复制的 Title / Bullets / Description / Tags + 诊断报告（关键词优先级表、覆盖地图、被排除的竞品品牌）；多语种/多版本时输出上述 JSON 结构（含合规检查与字符适配信息）。

## 注意事项

- 只用公开数据；无实时搜索量与精确数据时明确说明。
- Amazon 专精请走 `references/amazon-optimization.md`。
- 缺输入时先补齐必填项再产出。
- `product_name` 必填；小语种生成时确保 `language` 取值正确（es/fr/de/ja/ar）。
- 合规词库需按平台规则定期更新；A/B 版本数建议 ≤5 以保证变量清晰。
- 交付的多版本文案均已同步适配合规与字符限制。

## 可复用示例

> "为我的瑜伽垫在 eBay UK 建 listing，竞品链接：…，规格：6mm TPE 防滑，含背带，品牌 ZenMat。"
> "优化这个 Shopify listing 并超越这些竞品：…"
> "生成德语 Amazon 站蓝牙耳机文案，A/B 两个版本，差异按关键词顺序，风格 professional。"
