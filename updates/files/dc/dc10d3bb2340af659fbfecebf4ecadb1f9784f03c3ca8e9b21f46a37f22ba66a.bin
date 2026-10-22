---
name: product-manager-workflow
description: 产品经理全流程咨询：十阶段主动式咨询（开口三问→检索→规划→方案对比→技术选型→需求确认→PRD→Mermaid 图→导出 md/docx→H5 原型）。触发场景：产品经理级支持、需求分析、产品设计、路线图、竞品分析、产品从 0 到 1、H5 原型、Mermaid 甘特图。
author: Soulmate Agent团队成员：岸
---

# 产品经理全流程咨询（从0到1 / 迭代）
## 适用场景

- 需要产品经理级别支持：需求分析、PRD 撰写、产品设计、路线图规划、竞品分析、数据分析
- 询问产品经理职责/如何成为产品经理/技能要求
- 需要产品架构图、流程图、时序图、甘特图等 Mermaid 图表
- 从 0 到 1 输出 PRD 并生成可交互 H5 原型图；把 PRD 导出为 Markdown/.docx
- 触发词：产品经理、PRD、产品需求文档、需求分析、产品设计、产品路线图、竞品分析、用户故事、敏捷开发、Scrum、产品从0到1、功能需求、非功能需求、Kano模型、RICE评分、MoSCoW、用户旅程、产品架构、产品迭代、数据分析、DAU、MAU、留存率、转化率、NPS、B端产品、C端产品、H5设计、Mermaid、甘特图

## 流程（十阶段）

1. **确认需求（开口三问）**：先确认理解，再问——① 产品方向（做什么、面向谁、解决什么核心问题）② 平台形态（APP/小程序/Web/多端，C 端还是 B 端）③ 成熟度（0 到 1 还是迭代、有无竞品参照）。
2. **多源资料搜索**：按需组合网络搜索 + 本地 RAG。网络搜索**禁止硬编码具体工具名**；降级触发（结果 ≤2 / >5s 无响应 / 报错）即换工具重试。RAG 按类型取 `assets/product-manager/docs/` 下文档：需求分析→`pm-responsibilities.md`、`sdlc-product-process.md`；产品设计→`prd-template.md`、`mermaid-guide.md`；竞品→`pm-framework.md`；数据→`pm-framework.md`；路线图→`pm-framework.md`、`sdlc-product-process.md`。
3. **产品规划**：产品定位一句话；MoSCoW 优先级（Must 1–3 / Should 2–4 / Could 2–3 / Won't）；MVP 范围；用户旅程简化版。
4. **方案对比（用户选择）**：出 2–3 个方案（简约/标准/增强），给对比表（功能范围/开发周期/技术复杂度/适用场景），等用户选或提意见。
5. **技术选型确认**：前端（React/Vue/纯H5）、后端（Node/Python/Java/Go）、数据库（MySQL/PostgreSQL/MongoDB）、部署；确认技术约束与第三方依赖。用户跳过则用合理默认值。
6. **需求确认**：输出「需求确认书」（产品名称/选定方案/平台形态 + 核心功能表 + 关键业务流程 + 目标指标表 + Mermaid 图表预览），用户确认后进 PRD。有调整回阶段三。
7. **PRD 文档整合输出**：**输出前必须先询问存放路径与文件命名**（如不保存则直接回复中输出全文）。模板见下。
8. **Mermaid 图表整合**：按产品类型选图——0→1：产品架构图、核心用户旅程图、MVP 甘特图；迭代：需求状态流转图、迭代甘特图、跨团队协作时序图；竞品：功能对比矩阵、竞品架构对比图；数据：AARRR 漏斗图、留存曲线。
9. **导出格式选择**（PRD 完成后主动询问）：`md` → 保存 .md（Mermaid 保留为代码块）；`docx` → 保存 .docx（Mermaid 自动渲染为 PNG 嵌入）；`不需要` → 跳过。
   ```bash
   python3 scripts/product-manager/prd_export.py PRD文档.md PRD文档.docx
   ```
   依赖：`python-docx`（docx 必需）、Node + 本地浏览器（Chrome/Edge/Firefox）+ puppeteer（Mermaid 渲染，脚本 `scripts/product-manager/mermaid_render_multi.js` 自动检测浏览器路径，脚本位于 `prd_export.py` 同目录）。
10. **H5 可交互原型图**（可选，导出后主动询问）：**纯 HTML + CSS + 原生 JS，不用任何框架**；所有页面**集成在同一个 HTML 文件**，用 `showPage()` 切换 `section` 显隐，不依赖多文件或服务器；文件名 `{产品名称}_prototype.html`；图标用内联 SVG；字体用系统默认。**默认做法是直接引用 Tailwind CDN** `<script src="https://cdn.tailwindcss.com"></script>`（跨平台零配置，但需要联网）；若要求离线可开，改用本地内联样式并注意不要内联 ~350KB 的 tailwind.css。

## PRD 文档模板（七节）

```
# [产品名称] 产品需求文档 v0.1
## 1. 概述        1.1 背景 1.2 产品定位 1.3 目标用户 1.4 成功标准 1.5 竞品分析 1.6 参考资源
## 2. 用户与场景   2.1 用户画像 2.2 用户旅程 2.3 核心用例
## 3. 功能需求     3.1 功能列表 3.2 详细说明 3.3 验收标准
## 4. 非功能需求
## 5. 数据埋点
## 6. 风险与依赖
## 7. 附录
```

模板全文：`assets/product-manager/docs/prd-template.md`。

## 知识速查

- **需求优先级三剑客**：MoSCoW（快速分类）、RICE（量化评分）、Kano（满意度）。详见 `assets/product-manager/docs/pm-framework.md`。
- **AARRR 海盗模型** 与 **产品 KPI 体系**（DAU/MAU/留存/转化/NPS）：见 `data-analysis-metrics.md`、`pm-framework.md`。
- **Agile/Scrum** 速查：`assets/product-manager/docs/agile-dev.md`。
- **Mermaid 速查**（登录流程、订单状态流转、迭代甘特图、注册时序图、系统架构图、ER 图、用户旅程图）：`assets/product-manager/docs/mermaid-guide.md`。
- **Tailwind H5 速查**（布局/移动适配/颜色/边框阴影/定位/交互态/常用 H5 组件）：安装说明见 `assets/product-manager/docs/tailwind-installation.md`；更细的速查文档未随本技能提供，需要时另行查阅。
- **避坑指南**（十大常见误区、PRD 写作常见错误）：相关清单未随本技能提供，需要时另行整理。
- 其他文档：`pm-skills.md`、`pm-career-path.md`、`pm-responsibilities.md`、`sdlc-product-process.md`、`h5-mobile-best-practices.md`、`icon-sources.md`、`browser-support.md`。

## 输入输出

- **输入**：产品想法/迭代诉求；行业与竞品；技术约束。
- **输出**：产品规划与方案对比、技术选型确认、需求确认书、PRD（.md/.docx）、Mermaid 图、H5 原型（可选）。

## 注意事项

- 本技能是**主动式咨询流程**，不是单向问答；每个用户决策点都要等确认（方案选择、需求确认、存放路径、导出格式、是否出原型）。
- `docx` 导出依赖 `python-docx`；不装不影响纯 Markdown 输出。
- `mermaid_render_multi.js` 动态查找 puppeteer-core（优先用 `@mermaid-js/mermaid-cli` 的 bundled 版本）；WSL 用户需能访问 `/mnt/c` 以检测 Windows 浏览器路径。
- 网络搜索走环境中最可靠的工具，禁止硬编码工具名。
- **未验证**：原型用 Tailwind CDN 依赖联网，离线场景需自行替换为内联样式。

## 可复用示例

```
用户：我想做一个装修 APP
→ 阶段1 三问（方向/形态/成熟度）
→ 阶段2 搜索「装修APP用户痛点」「住小帮 齐家网 土巴兔 功能对比」+ 读 pm-framework
→ 阶段3 定位一句话 + MoSCoW 优先级 + MVP
→ 阶段4 出「简约版/标准版/增强版」三方案对比表，等选择
→ 阶段5 技术选型确认 → 阶段6 需求确认书 → 阶段7 PRD（先问存放路径）
→ 阶段8 架构图+用户旅程图+甘特图 → 阶段9 问 md/docx → 阶段10 问是否出 H5 原型
```
