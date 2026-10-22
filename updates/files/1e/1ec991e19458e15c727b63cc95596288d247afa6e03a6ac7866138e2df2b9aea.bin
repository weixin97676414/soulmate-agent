---
name: ui-ux-frontend
description: UI/UX 方案产出与前端设计质量：分诊后产出 UI 概念/UX 流程/设计系统/实现计划，配内置 BM25 检索脚本与设计系统生成器，并提供 /audit 类前端设计质量审查命令。触发场景：要 UI/UX 方案、设计令牌、前端实现规格、组件规格、无障碍、让设计更好看、审查设计质量、/audit /critique /polish 等命令。
author: Soulmate Agent团队成员：岸
---

# UI/UX 方案产出与前端设计质量
## 适用场景

- 用户要「设计一个界面」「优化这个页面的 UI/UX」「出一套设计系统/设计令牌」「把 UX 建议落到代码」
- 需要按平台出具体的组件/状态/间距/字体/交互规格
- 对既有前端做设计质量审查（无障碍、性能、响应式、层次、清晰度）
- 触发词：UI 设计、UX 流程、信息架构、视觉风格、设计系统、设计令牌、组件规格、文案/微文案、无障碍、前端界面、让设计更好看、检查设计质量

## 步骤

1. **分诊（只问必须问的）**：目标平台（web/iOS/Android/桌面）、技术栈（React/Next/Vue/Svelte、CSS/Tailwind、组件库）、目标与约束（转化/速度/品牌调性/无障碍等级）、已有素材（截图/Figma/仓库/URL/用户旅程）。用户说「全部都要」→ 按 设计 → UX → 代码 → 设计系统 顺序当作四份交付物。
2. **按需产出四类交付物**（都要具体到组件名、状态、间距、字体、交互）：
   - **UI 概念 + 布局**：视觉方向、栅格、字体系统、配色系统、关键屏/区块。
   - **UX 流程**：用户旅程、关键路径、错误/空/加载状态、边界情况。
   - **设计系统**：令牌（颜色/字体/间距/圆角/阴影）、组件规则、无障碍说明。
   - **实现计划**：精确到文件级的改动、组件拆分、验收标准。
3. **需要灵感/标准时检索内置库**（见下方命令），需要结构化令牌输出时跑生成器。
4. **写代码/改代码时套用设计规范**（见下），并主动指出反模式。
5. **按命令做审查/打磨**（见命令表），审查结果要给具体问题（带行号/组件名），不空谈。
6. **输出标准**：默认 ASCII-only 令牌/变量（除非项目已用 Unicode）；必须包含间距刻度、字阶、2–3 组字体配对、颜色令牌、组件状态；必须覆盖空/加载/错误、键盘导航、焦点态、对比度。

## 内置库检索命令

数据在 `scripts/data/`（BM25 检索，纯本地）。脚本原位的 `data/` 目录已对齐到 `scripts/data/`，可直接运行：

```bash
# 通用检索（域：style/prompt/color/chart/landing/product/ux/typography）
python3 scripts/ui-ux/search.py "SaaS dashboard" --domain style --max-results 3
# 指定技术栈检索（html-tailwind / react / nextjs）
python3 scripts/ui-ux/search.py "form validation" --stack react
# 生成完整设计系统建议（ASCII 或 markdown）
python3 scripts/ui-ux/design_system.py "fintech mobile app" -p "My Project" --format markdown
# 生成并持久化（Master + 页面覆盖 模式）
python3 scripts/ui-ux/search.py "dashboard" --design-system --persist -p "My Project" --page dashboard -o ./design-system
# 生成器简版入口
python3 scripts/ui-ux/design_system.py --help
```

数据文件：`scripts/data/{styles,colors,typography,charts,landing,products,ux-guidelines,ui-reasoning,web-interface,icons,react-performance}.csv` 与 `scripts/data/stacks/*.csv`（astro / flutter / html-tailwind / jetpack-compose / nextjs / nuxt-ui / nuxtjs / react-native / react / shadcn / svelte / swiftui / vue）。

## 前端设计规范（写代码时强制套用）

**字体**：选有个性的字体（Geist、Instrument Serif、DM Sans、Sora）；建 modular scale（1.25 或 1.333）；禁止 Arial / Inter（过于通用）/ system-ui；同页 ≤2 族。

**颜色**：用 OKLCH 定义（感知均匀）；中性色永远带色调（暖灰/冷灰，不纯灰）；暗色背景用 `#0f0f0f` 不用纯黑；禁止彩色背景上放灰字；禁止纯黑纯灰。

**空间**：4px 或 8px 基准间距；用留白制造呼吸感；正文宽 65ch、容器最大 1280px；禁止随意 padding（13px、22px）。

**动效**：缓动 `cubic-bezier(0.16, 1, 0.3, 1)`；微交互 100–200ms、页面过渡 300–500ms；尊重 `prefers-reduced-motion`；禁止 bounce/elastic；禁止 >600ms。

**交互**：焦点态必须可见（不移除 outline）；加载优先 skeleton 而非 spinner；错误提示具体可操作（"邮箱格式不对" 而非 "输入有误"）；禁用态要说明原因。

**UX 文案**：按钮动词开头（"保存更改" 而非 "确认"）；空状态说明原因 + 下一步；错误说人话；禁止"请稍候…"（要说在做什么）。

## 命令表

| 命令 | 功能 |
|------|------|
| `/audit [组件名]` | 检查无障碍、性能、响应式问题（列 3–5 个具体问题） |
| `/critique [组件名]` | UX 设计评审：层次、清晰度 |
| `/polish [组件名]` | 发布前最终打磨（输出完整改后代码 + 说明） |
| `/distill [组件名]` | 化繁为简，去多余元素 |
| `/colorize [组件名]` | 引入战略性色彩 |
| `/animate [组件名]` | 添加有意义的动效 |
| `/bolder [组件名]` | 让平淡设计更大胆 |
| `/quieter [组件名]` | 让张扬设计沉稳下来 |
| `/delight [组件名]` | 添加令人会心一笑的细节 |
| `/normalize [组件名]` | 与设计系统规范对齐 |
| `/harden [组件名]` | 增加错误处理、边界情况、国际化 |

## 输入输出

- **输入**：需求描述 / 截图 / Figma / 仓库 / URL / 用户旅程；技术栈与约束。
- **输出**：设计方向与布局规格、UX 流程、设计令牌、实现计划、改后代码（命令类）、审查问题清单。

## 注意事项

- 代码变更优先落地到具体 CSS/代码，不停留在概念。
- 发现反模式要简短指出（Inter + 紫色渐变、卡片套卡片、彩色背景灰字、bounce 动画等）。
- 审查结果必须带行号或组件名，禁止「大致符合」这类模糊表述。
- 检索脚本依赖 CSV 数据，勿移动 `scripts/data/` 相对位置（`core.py` 按 `__file__/../.. /data` 解析）。

## 可复用示例

**登录表单（套用规范后的特征）**：字体用 Geist 或 DM Sans；输入框 focus `2px solid oklch(0.6 0.2 250)`；按钮文案"登录"而非"确认"；错误提示"邮箱格式不正确，请检查 @ 符号前后"；加载用 skeleton；间距用 8 的倍数（8/16/24/32px）。

```bash
# 为一个金融 App 出设计系统
python3 scripts/ui-ux/design_system.py "fintech mobile app" -p "WalletApp" --format markdown
```
