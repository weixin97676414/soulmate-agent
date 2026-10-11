---
name: landing-page
description: "落地页生成：从 brief 生成自包含、高转化、响应式 HTML/CSS 落地页并附定制 README。触发场景：落地页、销售页、营销页、官网首屏页、预约通话页、下载页。"
author: Soulmate Agent团队成员：岸
---

# 落地页生成

## 适用场景

- 从产品/服务 brief 生成高转化、移动端自适应的落地页/销售页/营销页。
- 触发词：落地页、landing page、销售页、sales page、营销页、官网首屏页、预约通话页、下载页。

## 步骤

1. **分析 brief**：提取产品类型（SaaS/实物/服务/作品集/lead magnet/活动）、目标受众、主 CTA、价值主张、调性；收集价格、关键卖点、品牌色。
2. **选页面模板**（按产品类型定区块与长度）：
   | 类型 | 区块 | 长度 |
   |---|---|---|
   | SaaS | Hero, Features, How It Works, Pricing, Testimonials, FAQ, CTA | 长 |
   | 服务 | Hero, Services, Process, Portfolio, Testimonials, CTA | 中 |
   | 作品集 | Hero, Work Samples, About, Services, Contact | 中 |
   | Lead Magnet | Hero, Benefits, Social Proof, Form, CTA | 短 |
   | 电商 | Hero, Product Features, Gallery, Reviews, Buy CTA | 中 |
   | 活动 | Hero, Speakers/Details, Schedule, Tickets, FAQ | 中 |
3. **生成单个自包含 HTML**（内嵌 CSS，除 Google Fonts 外无外部依赖）：
   - **Hero**：标题（价值主张 ≤10 词）、副标题（≤25 词）、高对比 CTA 按钮（行动导向）、可选主图/背景、可选社会证明徽章。
   - **Features/Benefits**：3-4 张卡（Unicode/emoji 图标 + 名称 + 1-2 句讲结果不讲功能）；桌面 3 列、移动 1 列。
   - **Social Proof**：2-3 条评价卡（引语 + 姓名头衔公司 + 星级）；可选客户 logo 条。
   - **How It Works**：3 步编号流程 + 视觉连接。
   - **Pricing**：1-3 档卡片、高亮推荐档、功能对比、每档 CTA。
   - **FAQ**：4-6 问，用纯 CSS/HTML `<details>` 手风琴。
   - **Final CTA**：重复主 CTA + 紧迫感，换角度处理剩余异议，强对比背景。
4. **设计系统**：字体 `Inter`（Google Fonts）；标题 3rem/2rem/1.5rem/1.25rem；正文 1rem/1.6；最大行宽 65ch。默认色 `--primary:#2563eb`、`--primary-dark:#1d4ed8`、`--bg:#ffffff`、`--bg-alt:#f8fafc`、`--text:#1e293b`、`--text-light:#64748b`、`--accent:#f59e0b`。最大宽 1200px 居中；区块内边距 80px（移动 48px）；间距刻度 4/8/16/24/32/48/64/80。断点 1024+/768-1023/<768。
5. **转化优化**：首屏可见标题+CTA；单一主 CTA 重复 2-3 次；CTA 对比度 ≥ WCAG AA 4.5:1；无外部 JS、极少 CSS、不用真图（占位）；5 秒能理解；FAQ/评价处理异议；紧迫感只在真实时用。
6. **输出到 `output/landing-page/`**：`index.html`（自包含）+ `README.md`（客户定制指南：改 CSS 变量、替换占位内容、加真图、表单接入邮件服务、部署到 Netlify/GitHub Pages/任意静态托管）。
7. **向用户展示**：生成摘要、关键设计决策、文件位置、建议客户定制项。

## 输入输出

- 输入：产品/服务描述（类型、受众、主 CTA、价值主张、调性、价格、卖点、品牌色）。
- 输出：`output/landing-page/index.html` + `README.md`。

## 注意事项

- 质量清单：仅 Google Fonts 一个外部依赖；320/768/1200px 全响应式；所有 CTA 有 hover；WCAG AA 对比度；有 viewport meta；语义化 HTML；任何断点无横向滚动；FAQ 可交互；HTML < 50KB。
- 不编造客户评价、logo 或数据，占位内容要明确标为占位。
- 紧迫感/稀缺只在真实时使用（如"Limited beta spots"），不用假倒计时。

## 可复用示例

```
/landing-page-generator "远程团队用的 SaaS 项目管理工具，$29/月，免费试用"
/landing-page-generator "自由网页开发者作品集——预约通话 CTA"
```
输出单文件自包含落地页与定制 README。
