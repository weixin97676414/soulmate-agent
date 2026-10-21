---
name: ecom-rfm-segmentation
description: RFM 客户分群与分群营销：按 R/F/M 打分分层，给出每群留存与激活活动矩阵。触发：RFM／客户分群／客户分层／Champions／客户流失预警／复购分层。
author: Soulmate Agent团队成员：岸
---

# RFM 客户分群与分群营销

配套文件：`assets/output-template.md`、`segment-action-playbook.md`、`scoring-methodology.md`、`checklist.md`。

## 适用场景

- 按 R（最近购买）/ F（频次）/ M（金额）给客户打分分层，识别 Champions、Loyal、At Risk、Churned 等，给每群配针对性留存/激活活动。
- 解决：无差别打折伤毛利、流失盲区、留存预算错配、过度触达活跃客、激活靠猜、LTV 预测、忠诚计划设计。
- 触发词：RFM、客户分群、客户分层、Champions、客户流失预警、复购分层。

## 步骤

1. **导出并清洗订单数据**：客户 ID（或邮箱）、订单日期、订单金额（退款后净额）。分析窗口建议滚动 24 个月（服装/季节品 12 个月）。剔除测试单、内部单、批发账号。
2. **算 R/F/M 原始值**：R=距最近一次订单的天数；F=窗口内订单数；M=窗口内净收入。
3. **打 1-5 分**：每个维度按五分位给分（5 最好）。<500 客户用四分位（1-4）。
   - R 分：最近买=5，最久=1；F 分：订单最多=5，单次购买=1；M 分：花费最高=5，最低=1。
4. **组合打分 → 分群**：
   | 分群 | R | F | M |
   |------|---|---|---|
   | Champions | 4-5 | 4-5 | 4-5 |
   | Loyal Customers | 3-5 | 3-5 | 3-5 |
   | Potential Loyalists | 4-5 | 2-3 | 2-3 |
   | New Customers | 4-5 | 1 | any |
   | Promising | 3-4 | 1-2 | 1-2 |
   | Needs Attention | 2-3 | 2-3 | 2-3 |
   | About to Sleep | 2-3 | 1-2 | 1-2 |
   | At Risk | 1-2 | 3-5 | 3-5 |
   | Can't Lose Them | 1 | 4-5 | 4-5 |
   | Hibernating | 1-2 | 1-2 | 1-2 |
   | Lost | 1 | 1-2 | 1-2 |
5. **校验分群规模**（成熟店健康分布）：Champions 5-15%；Loyal 10-20%；At Risk+Can't Lose 10-20%（最需关注）；New+Potential 15-25%（增长管道）；Hibernating+Lost 20-40%（正常）。Champions >30% → 窗口太窄；Lost >60% → 拉新快于留存。
6. **按群建活动**：每群定信息、优惠、渠道、节奏（见 `assets/segment-action-playbook.md` 与 `output-template.md`）。
7. **设复盘节奏**：每 30-90 天重跑（快消更短、耐用品更长）；跟踪分群迁移（Needs Attention→At Risk 是警示；Promising→Loyal 是成功）。

## 输入 / 输出

- 输入：客户级订单导出（ID、日期、净额）。
- 输出：RFM 分群报告 + 分群活动矩阵（每群的触达信息/优惠/渠道/节奏）+ 预计收入影响。

## 关键输出示例（服装品牌 2,400 活跃客）

- Champions 187（7.8%）：新品早享 + 私人造型服务，不给折扣，目标提 AOV。
- At Risk 203（8.5%）：挽回序列"我们想你"→10% offer→最后机会，目标激活 25%。
- Can't Lose Them 89（3.7%）：电话/SMS 触达，VIP 激活（20%+免运）。
- New 445（18.5%）：聚焦第二单的引导序列（服装 LTV 最关键节点）。

## 常见错误

用全周期数据而非滚动窗口；不按购买周期调整 recency；M 用毛收入（高退货客可能净额为负）；200 客户硬拆 11 群（小数据应收敛到 5-6 群）；不剔除批发/B2B；只跑一次不更新；对所有非 Champions 用同一折扣；忽视分群迁移；不按群跟踪效果；把 RFM 当唯一分层。

## 注意事项

- 运行前用 `assets/checklist.md` 做准确性自检。
- 优惠只给真正需要的群（At Risk / Can't Lose / Lapsed），别给会自然复购的 Champions。
- RFM 说"做了什么"，不说"为什么"；可结合品类或问卷补全画像。

## 可复用示例

> "用这份订单数据做 RFM 分群，并给出每群的留存/激活活动。"
