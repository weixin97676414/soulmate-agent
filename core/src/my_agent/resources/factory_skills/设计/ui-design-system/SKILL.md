---
name: ui-design-system
description: UI 设计系统与界面规范：从设计简报→信息架构→颜色/字体/间距/圆角/阴影令牌→组件→交互→响应式→无障碍→走查评分，含决策表、数值规范与设计走查评分表。触发场景：从零设计界面、建立/审查设计系统、设计令牌、界面规范、UI 质量走查、无障碍检查。
author: Soulmate Agent团队成员：岸
---

# UI 设计系统与界面规范
## 适用场景

- 从零设计一个页面/产品界面（落地页、仪表盘、App、SaaS、电商、营销站）
- 建立或审查设计系统（颜色、字体、间距、圆角、阴影、动效令牌）
- 评审既有 UI 的质量、做设计走查与无障碍检查
- 需要"摆脱模板感"、给出有明确方向感的界面规范

## 步骤

1. **写设计简报（Design Brief）**：项目类型、目标用户（技术水平/年龄段/使用场景/设备）、业务目标与用户目标、成功指标、品牌性格、约束（技术栈、无障碍等级、必须支持深色模式/RTL/i18n）。
2. **定信息架构**：列出页面全部内容/功能 → 按 must/should/nice 排序 → 分组 → 定义浏览顺序；选导航形态（顶部栏 / 侧边栏 / 底部 Tab / 汉堡 / 命令面板）。
3. **建立设计系统基座**：颜色体系 → 字体体系 → 间距体系 → 圆角体系 → 阴影/层级体系（数值见下）。
4. **设计组件**：按钮层级、表单、卡片、弹窗、表格、空状态、加载状态。
5. **定义交互**：微交互时长/缓动、滚动行为、Toast/通知。
6. **响应式**：断点策略 + 各断点组件变化 + 触控规范。
7. **无障碍检查**：按 WCAG AA 清单逐条过。
8. **设计走查打分**：按下方 0–100 评分表打分，低于 60 分需重做。
9. **交付与实现**：交接清单 + CSS 架构约定 + 设计令牌。
10. **进阶**：令牌三层结构、动效体系、性能优化、国际化。

## 决策表（选型用）

**按产品类型定重点：**

| 类型 | 核心优先级 | 布局模式 | 密度 |
|------|-----------|----------|------|
| 落地页 | 转化 | 单列、CTA 聚焦 | 低 |
| 仪表盘 | 信息密度 | 网格/面板 + 侧边导航 | 高 |
| 移动 App | 拇指区、速度 | Tab 栏 + 卡片 + 底部弹层 | 中 |
| SaaS | 效率、可学习 | 侧边栏 + 内容区 | 中高 |
| 电商 | 浏览+购买 | 网格目录 + 吸底购物车 | 中 |
| 营销站 | 品牌叙事 | 分区 + 视差 + 媒体 | 低-中 |

**导航形态判据**：条目 <7 用顶部栏；7–15 用侧边栏；>15 用侧边栏+分组。移动端底部 Tab 最多 5 个。

**布局骨架**：F 型（内容密集，如博客/资讯）、Z 型（极简，如落地页/登录）、仪表盘型（导航+KPI 行+图表+表格+侧栏）。

**设计方向（选一个走极端，不要平庸）**：极简 / 奢华精致 / 活泼 / 编辑感 / 工业风。

**Grid vs Flexbox**：页面级结构用 CSS Grid（`grid-template-areas`）；导航栏用 Flexbox；卡片网格用 `auto-fill/auto-fit`；居中用 `place-items: center`；侧栏+内容用 `250px 1fr`。

**字体配对**（最多 2 族）：

| 气质 | 标题 | 正文 |
|------|------|------|
| 现代 SaaS | Inter | Inter |
| 精致 | Playfair Display | Source Serif Pro |
| 友好创业 | Poppins | DM Sans |
| 技术/开发 | Space Grotesk | IBM Plex Sans |
| 大胆编辑 | Clash Display | Satoshi |
| 干净企业 | Plus Jakarta Sans | Inter |

## 数值规范（硬信息）

**颜色令牌**：主色 50–900 十级；语义色 success `#22c55e`、warning `#f59e0b`、error `#ef4444`、info `#3b82f6`；中性灰 50–900；表面色 background / surface / surface_raised / overlay `rgba(0,0,0,0.5)`。

**对比度（WCAG）**：普通文字 <18px ≥4.5:1；大字 ≥18px 粗体或 ≥24px ≥3:1；UI 组件/图标 ≥3:1；AAA 普通文字 ≥7:1。**禁止仅用颜色传达信息**。

**深色模式**：背景不用纯黑，用 gray-900 `#111827`；文字用 gray-100（不要纯白）；饱和色提亮一级（primary-500 → 400）；边框用 gray-700；卡片 gray-800；阴影改用更亮的边框或微光。

**字阶（1.25 比例，rem）**：xs 0.75 / sm 0.875 / base 1（正文不得低于 16px）/ lg 1.125 / xl 1.25 / 2xl 1.5 / 3xl 1.875 / 4xl 2.25 / 5xl 3。行高：标题 1.25、正文 ≥1.5、长文 1.75。行长上限 65ch（45–75ch）。

**间距（4px 基准）**：0 / 1=0.25rem / 2=0.5rem / 3=0.75rem / 4=1rem / 5=1.25 / 6=1.5 / 8=2 / 10=2.5 / 12=3 / 16=4 / 20=5 / 24=6rem。相关项 4–8px、成组项 12–16px、区块 32–64px、页面区段 64–96px、卡片内边距 16–24px。

**圆角**：none 0 / sm 0.25rem / md 0.375rem / lg 0.5rem / xl 0.75rem / 2xl 1rem / full 9999px。只挑 2–3 个值统一使用。

**阴影**：sm `0 1px 2px rgba(0,0,0,0.05)`；md `0 4px 6px -1px rgba(0,0,0,0.1)`；lg `0 10px 15px -3px rgba(0,0,0,0.1)`；xl `0 20px 25px -5px rgba(0,0,0,0.1)`；焦点环 `0 0 0 3px rgba(primary,0.3)`。

**断点**：sm 640 / md 768 / lg 1024 / xl 1280 / 2xl 1536px；移动优先（min-width）；内容最大宽 1280px；容器内边距 移动 16 / 平板 24 / 桌面 32px。

**触控**：最小点击区 44×44px（Apple）/ 48×48px（Material）；目标间距 ≥8px；主要操作放屏幕下方 60%。

**动效**：即时 0–100ms；快 100–200ms；常规 200–400ms；慢 400–700ms。缓动：入 `cubic-bezier(0.16, 1, 0.3, 1)`、出 `cubic-bezier(0.55, 0, 1, 0.45)`、移动 `cubic-bezier(0.65, 0, 0.35, 1)`。列表 stagger 每项 50ms。**必须尊重 `prefers-reduced-motion`**；只动画 `transform`/`opacity`。

## 组件要点

- **按钮层级**：主（实心，每屏 1–2 个）/ 次（描边或弱底）/ 幽灵（纯文字）/ 危险（红，1 个）/ 图标按钮。状态必须有：默认、hover、active（scale 0.98）、focus、disabled（50% 透明 + not-allowed）、loading。
- **表单**：标签在输入框上方；<6 字段用单列；错误在字段下方且具体（写「邮箱需含 @」，不写「输入无效」）；可选字段标「(optional)」而不是必填打星；失焦即校验。
- **卡片**：基础/可交互/推荐三种变体；交互卡片 hover 升阴影。
- **弹窗**：小 480 / 中 640 / 大 800px；深色遮罩可点关闭；右上角关闭按钮；焦点锁定；移动端转底部全屏抽屉；危险操作二次确认。
- **表格**：表头 gray-50、`sticky`；行 hover；数字右对齐；空状态给插图+文案+CTA；加载用骨架行而非转圈。
- **空状态**：图标 + 标题 + 说明 + CTA，绝不留白。
- **加载**：骨架屏 > 转圈；已知进度用进度条；低风险操作可用乐观 UI。

## 设计走查评分表（0–100）

| 维度 | 权重 | 判据 |
|------|------|------|
| 视觉层次 | 20% | 3 秒内能识别主操作，标题/内容/CTA 分层清晰 |
| 一致性 | 15% | 间距/颜色/圆角/字体全站统一，组件复用 |
| 留白 | 15% | 区块有呼吸感，不拥挤也不空旷 |
| 无障碍 | 15% | 对比度、键盘可达、语义化、焦点态 |
| 响应式 | 10% | 三端正常、无横向滚动、触控友好 |
| 交互 | 10% | hover/active/focus/loading 状态齐全 |
| 字体 | 10% | 行长合理、层级清楚、字阶一致 |
| 色彩 | 5% | 语义色正确、颜色不过多、深色模式可用 |

评级：90–100 可上线；75–89 良好需微调；60–74 功能可用待设计优化；<60 需大改。

## 注意事项

- 交付前自检：主 CTA 是否一眼可见；空/加载/错误状态是否都有设计；移动端是否实测（不是桌面缩小）；深色模式；焦点态；对比度；图片 alt；404 页。
- 交接给开发时给：间距/颜色/字号/圆角/阴影的令牌值、所有交互状态、各断点变化、SVG 图标、设计令牌 JSON/CSS 变量。
- CSS 约定：不用 `!important`、不写魔法数字、移动优先 `min-width`、flex 一维 grid 二维、用 `gap` 不用 margin、`aspect-ratio` 替代 padding-top hack。
- 禁止：仅靠颜色传达、移除焦点框、随意间距、动画布局属性、忽略 reduced-motion、全部居中、点击区过小、白底浅灰字、无个性系统字体。

## 可复用示例

**令牌三层结构（CSS 变量）：**

```css
/* Layer 1 原始值 */
--blue-500: oklch(0.55 0.2 250);
--gray-100: oklch(0.95 0.005 250);
--radius-md: 0.5rem;
/* Layer 2 语义 */
--color-primary: var(--blue-500);
--color-surface: var(--gray-100);
/* Layer 3 组件 */
--btn-bg: var(--color-primary);
--btn-radius: var(--radius-md);
--btn-padding: var(--space-2) var(--space-4);
```

**容器 + 流式排版：**

```css
.container { width: 100%; max-width: 1280px; margin-inline: auto; padding-inline: clamp(1rem, 5vw, 3rem); }
h1 { font-size: clamp(2rem, 1.5rem + 2.5vw, 3.5rem); }
section { padding-block: clamp(2rem, 1rem + 4vw, 6rem); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr)); gap: var(--space-6); }
```

**按钮状态：**

```css
.btn { transition: all 150ms ease-out; }
.btn:hover { background: var(--color-primary-600); }
.btn:active { transform: scale(0.98); }
.btn:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
```

**动效安全：**

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```
