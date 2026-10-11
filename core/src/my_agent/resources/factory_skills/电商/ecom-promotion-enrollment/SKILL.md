---
name: ecom-promotion-enrollment
description: 平台活动报名：对照多平台促销机制、评估报名资格、排时间线并规避常见被拒原因。触发：活动报名／Lightning Deal／Best Deal／Coupon／Prime Day／618／11.11／活动被拒。
author: Soulmate Agent团队成员：岸
---

# 平台活动报名助手（促销机制对照 · 资格 · 时间线）

配套脚本：`scripts/handler.py`。

## 适用场景

- 对比各平台促销机制、评估资格、规划报名时间线、规避常见报名错误。
- 覆盖：Amazon Lightning Deal/Best Deal/Coupon/Shoppable Holiday；TikTok Shop Promo Zone；Shopify Discount Rules；淘宝聚划算；京东 618 等。
- 触发词：活动报名、Lightning Deal、Best Deal、Coupon、Prime Day、618、11.11、Deal 资格、活动被拒。

## 步骤

1. **采集**：平台（Amazon/TikTok Shop/JD/淘宝/Shopify/小红书/通用）；促销类型；SKU 或类目语境（产品类型、价格带、评分、履约方式）；活动窗口；历史（过往拒审、通过率、活动表现）。
2. **映射资格启发式**：针对具体促销类型给出资格评估。
3. **建报名清单与时间线**：提交截止 → 审核 → 批准 → 上线。
4. **列出常见被拒原因与规避**。
5. **返回 Markdown 报名简报**。

## 输入 / 输出

- 输出简报含：促销类型说明与运作方式、资格评估、报名时间线（提交截止→审核→批准→上线）、清单（所需材料、价格约束、库存要求）、常见拒因与缓解、平台特例提示。

## 注意事项

- 无实时卖家后台/报名 API；资格评估为方向性，最终审批取决于平台审核。
- 不承诺必定报名成功或特定资源位。
- 定价与毛利决策归运营方。
- 不适合：实时报名状态跟踪或自动提交；复杂法律/合规的促销管理；内置库未覆盖的平台或类型。

## 可复用示例

> "帮我报名 Prime Day 的 Amazon Lightning Deal，SKU 是护肤类目。"
> "TikTok Shop 季中闪购该用哪种促销？"
> "帮我排一个京东 618 的报名时间线。"
> "怎么避免 Amazon 家居类目促销被拒？"
