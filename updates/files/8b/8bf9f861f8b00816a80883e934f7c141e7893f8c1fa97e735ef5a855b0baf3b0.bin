---
name: amazon-ppc-campaign
description: 亚马逊 PPC 广告：搭建活动结构、按 ACoS 框架调出价、做否定词与搜索词优化。触发：亚马逊广告／PPC／ACoS／Sponsored Products／广告活动结构／否定关键词／搜索词报告。
author: Soulmate Agent团队成员：岸
---

# 亚马逊 PPC 广告（搭建 / 优化）

配套脚本：`scripts/fetch-competitor.sh`。

## 适用场景

- 新品搭建亚马逊 PPC 结构；审计现有活动与 ACoS；优化出价与否定词。
- 触发词：亚马逊广告、PPC、ACoS、Sponsored Products/Brands、广告活动结构、否定关键词、搜索词报告。

## 两种模式

| 模式 | 何时用 | 输入 | 输出 |
|------|--------|------|------|
| A — Build | 新品开始投广告 | 商品信息 + 关键词 + 毛利 | 完整活动蓝图 + 关键词分组 + 初始出价 |
| B — Optimize | 改善现有活动 | 活动数据 + 搜索词报告 + 当前 ACoS | 优化计划 + 出价调整 + 否定词清单 |

## 关键公式

- **Break-even ACoS** = 广告前利润率。例：售价 $40、扣各项成本后利润 $25 → 62.5%，花到这个 ACoS 即打平。
- **Target ACoS** = Break-even ACoS − 目标利润率。例：62.5% − 25% = 37.5%。
- **Max CPC** = Selling Price × Target ACoS × Conversion Rate。转化率未知时用类目基准（10-15%）。
- **关键词漏斗**：
  ```
  Auto（发现新词） --2+ 订单--> Manual Broad（更宽匹配测试） --2+ 销售--> Manual Exact（精准放大）
  每一步把迁移词在原活动中设为 Neg，防止重复花费与自我竞争。
  ```

## 步骤（模式 A）

1. **收商品信息**：ASIN、售价、落地成本、月广告预算、平台费（约 15% referral + FBA）。关键：成本、月预算、关键词或竞品 ASIN。
2. **算 ACoS 框架**：Break-even / Target（成熟 30%、launch 50%）/ Max CPC。
3. **收关键词**（三选一或组合）：自备关键词词表；竞品 ASIN 跑 `scripts/fetch-competitor.sh <ASIN>` 提取；用户自备词表。可扩词用 Amazon autocomplete：
   ```bash
   curl -s "https://completion.amazon.com/api/2017/suggestions?mid=ATVPDKIKX0DER&alias=aps&prefix=<URL编码关键词>" \
     | python3 -c "import sys,json; [print(s['value']) for s in json.load(sys.stdin).get('suggestions',[])]"
   ```
4. **建 4 个活动**：P1 Auto Discovery（必选）、P2 Manual Exact（10-15 词，必选）、P3 Manual Broad（必选）、P4 Product Targeting（有竞品 ASIN 时）。预算紧先 P1+P2，一周后加 P3、再有竞品 ASIN 加 P4。
5. **初始出价**：Exact = Amazon 建议出价或 Max CPC 取低；Broad = Exact 的 70-80%；Auto / Product = Exact 的 50-70%。7 天或 20+ 点击后再调。
6. **否定词种子**：① 跨活动否定（把 Exact 词加入 Broad/Auto 否定）；② 不相关词（错材质/错产品/错意图）；③ 通用浪费修饰词（free/cheap/used/DIY/review/reddit/how to）。
7. **产出蓝图** + 启动排期（Day1 建 P1+P2；Day3 看曝光；Day7 加 P3+P4 并否词；Day14 迁移 2+ 订单词；Day21 按 20+ 点击调出价）。

## 步骤（模式 B）

1. 收数据：活动名与类型、整体 ACoS、月花费与广告销售额、利润率（关键）；搜索词报告加分。
2. 五维审计：财务健康、活动效率（🔴🟡🟢）、关键词表现、预算分配、漏掉的机会。
3. 漏斗分析：2+ 订单 → 上迁到 Exact 并在原活动否定；10+ 点击 0 销售 → 否定；<20 点击 → 观察名单。
4. 出价调整（20+ 点击才统计显著）：
   - ACoS >200%：降 30-50%；100-199%：降 20%；target+10%~99%：降 10-15%；
   - 在 target ±10%：不变；低于 target：升 10-20%；10+ 点击 0 销售：暂停。
5. 输出优先行动：① 今日否定词 ② 本周迁移 ③ 本周调价 ④ 下周预算再分配 + 4 周逐周计划。

## 输入 / 输出

- 输出：可直接在 Seller Central 落地的活动蓝图 / 优化报告（含预算汇总、启动排期、周计划）。

## 注意事项

- 无 API：不能直连 Seller Central、不能拉实时竞价、不能自动改活动。
- Amazon 建议出价 > Max CPC 时，要提示取舍（可接受亏损抢排名 / 提价 / 放弃该词）。
- 完整数据缺失时给出方向性判断并标注假设，不承诺 ROAS 提升。
- 投放顺序：先备好关键词词表（自备，或用 Amazon autocomplete / 竞品 ASIN 扩词）→ 检查 listing 质量 → 再投广告；listing 文案要点可参照 `references/listing-copy.md`。

## 可复用示例

> "我上一个便携榨汁机，$39.99，成本 $8+运费 $3+平台费 $7.5，关键词：portable blender, personal blender, smoothie maker。帮我建 PPC 结构。"
> "我 ACoS 58%、目标 30%，3 个活动 Auto/Broad/Exact，利润率 54%，怎么优化？"
> "这是本周搜索词报告 [粘贴数据]，帮我找浪费、该否定什么、该迁移什么。"
