# 用 HTML 排版微信公众号文章：完整规范速查手册

> 适用场景：你想先在本地用 HTML 把文章排版好、预览满意后，再搬到公众号后台发布。
> 整理日期：2026-09-02 ｜ 资料基于微信官方《公众平台编辑器插件开发规范》+ 多篇深度实测文章交叉验证（来源见文末）。

---

## 0. 先记住 5 句话（核心结论）

1. **公众号正文不是"网页"，而是经过微信清洗的 HTML 片段**——保存时微信会过一遍"白名单过滤器"，不认识的标签和样式直接删掉。
2. **只认行内样式**：不支持 `<style>` 标签、不支持外部 CSS 文件、不支持 class/id 选择器，一切样式必须写进每个元素的 `style="..."` 属性里。
3. **禁一切脚本与交互**：JS、iframe、表单全部无效，文章是静态的。
4. **图片必须走微信图床**：先用公众号后台"图片库"上传，拿到 `https://mmbiz.qpic.cn/...` 链接再填入 `src`；外链图片、Base64 图片发布后会裂图。
5. **搬运方式 = 复制"渲染结果"而非"源码"**：本地浏览器打开 HTML → Ctrl+A 全选 → Ctrl+C → 到公众号编辑器 Ctrl+V。浏览器剪贴板会携带格式化后的富文本，微信再清洗一遍、只留合规内容。

一句话排版本质：**用白名单内的标签 + 内联样式，写一个"微信看得懂"的 HTML。**

---

## 1. 底层机制：微信到底对你的 HTML 做了什么

公众号编辑器的正文其实是一个富文本区域（`contenteditable`）。当你粘贴/保存内容时，微信端会执行类似 HTML Sanitization（消毒）的处理，有**四道关卡**：

| 关卡 | 处理方式 | 举例 |
|------|---------|------|
| ① 标签白名单 | 只保留允许的标签，其余整段删除 | `<p>` 保留，`<script>` 删除 |
| ② 属性白名单 | 只保留允许的属性 | `src/alt/href/style` 保留，`onclick/id` 删除 |
| ③ CSS 清洗 | 只保留允许的内联样式属性 | `color/font-size` 保留，`position:fixed` 整行删除 |
| ④ 图片重写 | 上传后替换为微信 CDN 地址并加宽高限制 | `src` 被替换为 mmbiz.qpic.cn 链接 |

**两个直接后果：**
- 你在本地浏览器里看到的效果 ≈ 公众号里的效果，但不完全等于——凡是被微信禁止的样式，发布后**静默丢失**（不报错，就是不见了）。
- 所以"本地预览 OK"只是第一步，**最终一定要用公众号后台的"预览"扫码在真机上看一遍**。

> 微信官方还提供了一个结构校验接口（第三方编辑器用它验证模板是否合规）：
> `POST http://mp.weixin.qq.com/article-bin/verify_article_structure`，body 传 `{"content":"<你的HTML>"}`，返回 `isValid` 布尔值 + 违规详情。想严格自检可以拿它测，但普通创作者用不到，知道有这回事即可。

---

## 2. HTML 标签支持清单（白名单）

### ✅ 完全支持（放心用）

| 类别 | 标签 | 说明 |
|------|------|------|
| 段落 | `<p>` | 正文主力，默认自带上下间距 |
| 容器 | `<section>`、`<div>` | 微信自家的编辑器大量用 `<section>` 做模块容器；`<div>` 也保留。**做色块/卡片/留白全靠它俩** |
| 行内容器 | `<span>` | 局部变色、加背景、改字号的必备 |
| 标题 | `<h1>`~`<h6>` | 建议当"小标题"用，配内联样式自定义字号颜色 |
| 加粗 | `<strong>`、`<b>` | 推荐 `<strong>`（语义更标准） |
| 斜体 | `<em>`、`<i>` | 推荐 `<em>` |
| 下划线 | `<u>` | |
| 删除线 | `<s>`、`<del>`、`<strike>` | |
| 上下标 | `<sub>`、`<sup>` | 注释、角标 |
| 换行 | `<br>` | 段内强制换行（不产生段落间距） |
| 分隔线 | `<hr>` | 可用，但更好看的分隔用 `<section>` 画 |
| 列表 | `<ul>`、`<ol>`、`<li>` | 无序/有序列表，可自定义符号与缩进 |
| 引用 | `<blockquote>` | 配内联样式做"引用块/金句块" |
| 代码 | `<code>`、`<pre>` | 行内代码与代码块（`<pre>` 见下方⚠️，有坑） |
| 链接 | `<a>` | 只能链公众号文章/小程序；**外部网址会弹"即将离开微信"提醒**，慎用于正文 |
| 图片 | `<img>` | 必须用微信图床链接，自动 `max-width:100%` |
| 表格 | `<table>/<thead>/<tbody>/<tr>/<td>/<th>` | 支持**轻量表格**；复杂跨行跨列、嵌套表格表现差，谨慎使用 |
| 语音 | `<mpvoice>` | 微信专用：插入语音 |
| 视频 | `<mpvideo>` | 微信专用：插入视频（腾讯视频 iframe 是微信唯一放行的外部 iframe） |

### ❌ 会被删除 / 无效（别用）

| 标签 | 原因 |
|------|------|
| `<script>`、`<style>`、`<link>` | 禁脚本、禁样式表 |
| `<iframe>` | 全部禁止（唯一例外：腾讯视频官方嵌入） |
| `<form>`、`<input>`、`<button>`、`<select>`、`<textarea>` | 表单/交互组件全部移除 |
| `<video>`、`<audio>` | 要用微信的 mpvideo/mpvoice，或官方"视频/音频"按钮插入 |
| `<object>`、`<embed>`、`<canvas>`、`<frame>`、`<frameset>` | 一律不支持 |
| `<html>`、`<head>`、`<body>` | 你只需要正文片段，不需要完整页面骨架 |
| `<svg>` | 部分场景能过，但复杂度高、兼容性差（iOS 尤其多坑）；**装饰图形建议直接做成图片** |

---

## 3. CSS 内联样式支持清单

> 前提：**一切写在 `style=""` 里**，不要想用 class。

### ✅ 稳定可用（放心用）

| 类别 | 属性 | 常用值示例 |
|------|------|-----------|
| 字号 | `font-size` | `15px`、`16px`（推荐 px，勿用过大值） |
| 字体 | `font-family` | 系统字体栈，见第 5 节 |
| 字重 | `font-weight` | `bold`、`400/600/700` |
| 颜色 | `color` | 十六进制 `#3f3f3f`（推荐）；`rgba()` 部分旧设备兼容性一般 |
| 行高 | `line-height` | `1.6`、`1.75`（无单位数值最稳） |
| 字间距 | `letter-spacing` | `0.5px`、`1px` |
| 对齐 | `text-align` | `left/center/right`（**不要用 start/end**，见红线） |
| 缩进 | `text-indent` | `2em` 首行缩进 |
| 修饰 | `text-decoration` | `underline`、`line-through`、`none` |
| 外边距 | `margin` / `margin-top/bottom/left/right` | `0 0 16px 0`；段间距主力 |
| 内边距 | `padding` | 色块内边距 |
| 边框 | `border`、`border-radius` | 卡片、圆角 |
| 背景 | `background-color` | 纯色背景块 |
| 阴影 | `box-shadow` | 卡片阴影（注意深色模式会反色，见第 6 节） |
| 宽度 | `width`、`max-width` | 图片 `width:100%`、`max-width:100%` |
| 显示 | `display` | `block`、`inline-block`、`flex`（flex 可用，做多列排版） |
| Flex | `flex`、`flex-direction`、`justify-content`、`align-items`、`gap` | 两列布局/图标+文字并排 |
| 对齐基线 | `vertical-align` | 图片与文字对齐 |
| 透明度 | `opacity` | **不要设 0**（见红线） |
| 行内间距 | `white-space` | 慎用，涉及换行 |

### ⚠️ 有条件可用（慎用 / 部分设备不稳）

| 属性 | 问题 |
|------|------|
| `transform` | 历史版本会被整行过滤；近期简单旋转/缩放可能生效，但**跨设备不一致**，别依赖 |
| `linear-gradient(...)` | 内联渐变"技术上可保留"，但旧版微信内置浏览器兼容性存疑；**重要背景建议用纯色或图片** |
| `float` | 不被禁但很危险：易脱离容器造成内容意外错位，**强烈建议用 flex 代替** |
| `%` 百分比（高度/负 margin） | 部分场景失效（如 `margin-top:-100%` 无效），尺寸优先 px |
| `filter` | 简单滤镜可用，复杂效果别想 |
| `z-index` | 只有父级 `display:flex` 时才生效，且无定位环境下意义有限 |

### ❌ 会被整行删除 / 完全无效（别写）

| 属性 | 说明 |
|------|------|
| `position`（absolute/fixed/relative/sticky） | **整行删除**。做不了悬浮、吸附、层叠；一切走文档流 |
| `animation`、`transition` | 无 `<style>` 承载不了关键帧；CSS 动画不可用 |
| `@media` 媒体查询 | 无效，无法按屏幕适配（靠微信自身的响应式） |
| `:hover`、`:active`、`::before`、`::after` | 无选择器机制，伪类伪元素全部失效 |
| `cursor` | 无效（移动端无鼠标） |

### ⚠️ 属性级"暗坑"（微信官方编辑器插件规范明令禁止的写法）

这些来自微信开发者文档《公众平台编辑器插件开发规范》，是第三方编辑器接入时的硬性红线，写 HTML 时同样要避开：

| 红线 | 错误示例 | 后果 |
|------|---------|------|
| `opacity: 0` 叠透明图 | `<img style="opacity:0">` + 背景 SVG 同位置叠放 | 发布后后台**无法再修改这张图**（实际显示的是 SVG 背景图） |
| 透明光标 `caret-color: transparent` | `caret-color: rgba(0,0,0,0)` | 编辑时看不到光标，体验灾难 |
| `line-height: 0` | 容器设 `line-height:0` | 文字行全部重叠，不可读 |
| 固定宽度 | 容器写死 `width:586px` | 大屏靠左留白、小屏挤爆，破坏响应式 |
| 固定高度 / `height:0` | 容器 `height:0` 靠编辑器撑开 | 编辑器里正常，**移动端直接空白** |
| `text-align: start/end` | 混排 start 值 | iOS18 等部分终端渲染不一致 |
| 用 `<pre>` 包正文 | `<pre style="line-height:1.75">普通段落…` | `<pre>` 自带 `white-space:pre`，**移动端窄屏文字被横向截断**。正文请用 `<section>`/`<p>` |
| SVG 动画只写 `begin="touchstart"` | | PC 端鼠标点击不触发，要 `begin="touchstart; click"` |

---

## 4. 结构类硬规则（官方文档）

- **同标签嵌套 ≤ 15 层**：`<section><section><section>…` 嵌套过深会被编辑器自动删除，别套娃。
- **行内容器规范**：微信渲染时会生成 `<span leaf>` 这样的行内容器节点，它的内部只能放行内内容（文字/图片/行内标签），不要把块级结构硬塞进去。
- **id 属性会被剥离**：写了也白写 → 别指望锚点跳转、JS 定位。
- **class 属性不会被删但无样式作用**：微信不加载任何 CSS，class 只是装饰性的。可以留着当"代码里的注释标记"，别指望它出样式。

---

## 5. 页面宽度与排版设计参数（好看的关键）

### 5.1 页面宽度

- 公众号图文**无固定宽度**，自适应手机屏幕（逻辑宽度约 375~414pt，PC 上内容区约 578px）。
- 因此你的 HTML **不要写死外层宽度**，让内容 100% 流式铺开；想要"整体内缩"，用外层 `<section>` 加 `padding: 0 8px`（或 10~16px）即可。
- 本地预览时，建议把浏览器窗口/预览容器调成 **375px 宽**模拟手机观感。

### 5.2 字号规范（行业通行推荐，非微信强制）

| 元素 | 字号 | 说明 |
|------|------|------|
| 正文 | **15~16px** | 主流大号共识；14px 偏小，17px 偏大 |
| 注释/图注 | 12~13px | 配灰色 `#999/#888` |
| 小节标题 | 16~18px | 比正文大 2~3px，加粗即可，不必用大号 |
| 章标题 | 18~20px | 文章内大标题 |
| 颜色 | 正文 `#3f3f3f`~`#595959` | **不要纯黑 `#000`**，柔和耐读 |
| 标题色 | `#333` 或品牌主色 | |
| 强调色 | 全篇 ≤ 2 种 | 高亮、链接、金句用 |

### 5.3 间距参数（直接影响阅读舒适度）

| 参数 | 推荐值 | 写法 |
|------|--------|------|
| 行高 line-height | **1.6 ~ 1.8**（正文常用 1.75） | `line-height:1.75` |
| 字间距 letter-spacing | 0.5~1px | `letter-spacing:0.5px` |
| 段间距 | 段落间 12~20px | `margin:0 0 16px 0`（下边距） |
| 两端留白 | 正文容器左右 8~12px | 外层 section `padding:0 10px` |
| 每段长度 | 手机屏 3~5 行 | 超过就拆段 |

### 5.4 字体（不要指定具体字体名做"特殊字体"效果）

微信**不支持 webfont/自定义字体**，字体完全由读者设备决定。你可以显式给 `font-family` 一个"系统字体栈"，让 iOS/Android/Windows 各自命中最佳系统字体：

```css
/* 无衬线（默认正文，推荐） */
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
  "Helvetica Neue", Helvetica, Arial,
  "PingFang SC", "Hiragino Sans GB",
  "Microsoft YaHei", "Source Han Sans CN", sans-serif;

/* 衬线（文艺感） */
font-family: "Songti SC", "Noto Serif CJK SC", "SimSun", "Times New Roman", Georgia, serif;

/* 等宽（代码块） */
font-family: "SF Mono", "Menlo", "Consolas", "Courier New", monospace;
```

> 想要"独一无二的字体"效果（书法字、艺术字）→ 直接把字做成 PNG 图片插进去，这是唯一稳定方案。

### 5.5 深色模式适配（2020 年起微信支持，必须考虑）

微信会把图文里**接近黑白的"无彩色"自动反转**，彩色基本不反转：

| 浅色模式色值 | 深色模式显示为 |
|------|------|
| `#232323`（近黑） | `#c3c3c3`（近白） |
| `#333333` | `#b3b3b3` |
| 彩色值 | **不变** |
| 阴影 | **被反转为白色光晕** |

深色模式下排版的 6 条守则：

1. **图片用透明底 PNG**：JPG 白底图在深色模式下一个大亮块，很刺眼。
2. **别用纯黑/纯白大色块**：深色背景（如 `#1a1a1a`~`#2d2d2d`）代替纯黑。
3. **少用 box-shadow**：阴影会反转成白色光晕，像"发光体"。
4. **避免白色边框**：深色模式变刺眼亮框。
5. **用低饱和色**：高饱和荧光色在深色背景下刺眼且色差大。
6. **深色模式预览一遍再发布**（见第 9 节工作流）。

---

## 6. 图片规范（封面 + 正文配图）

### 6.1 文章封面

| 类型 | 尺寸 | 比例 | 说明 |
|------|------|------|------|
| 头条大图（单图文/首条） | 900×383px（高清 1200×510） | **2.35:1** | 消息列表顶部展示 |
| 次条/小图封面 | 500×500px（最低 200×200） | **1:1** | 第 2~8 条 |
| 分享卡片（朋友圈/聊天） | 系统从大图**中心**自动裁 383×383 | 1:1 | ⚠️ 关键内容必须放在封面**中心 383×383 安全区**内，四周会被裁 |

封面安全区硬规则：上下各可能裁掉 15%，左右各留 10% 空白；**底部不放标题/二维码/关键文字**。

### 6.2 正文配图

| 参数 | 推荐/限制 |
|------|-----------|
| 宽度 | **750~1080px**（超过 1080 微信会强制压缩变糊）；小于 320px 会模糊 |
| 格式 | JPG（照片）、PNG（图标/文字/透明底） |
| **不支持 WebP**（上传报错） | |
| 单张大小 | 平台上限 10MB；**建议压到 500KB 以内**（加载快） |
| 像素上限 | 长×宽 < 600 万像素，超出报错 |
| GIF 动图 | 宽 ≤640px（超出会被压缩）；帧数 <300；≤10MB；**iOS 默认不自动播放**，需点击 |
| 长图/信息图 | 高 >2500px 建议拆 2~3 张，避免加载失败 |

### 6.3 图片三准则（最容易翻车的点）

1. **全部走微信图床**：素材管理 → 图片 → 上传 → 复制 `mmbiz.qpic.cn` 链接。外链图、Base64 图、本地相对路径 → 发布后裂图。
2. **每张图 src 都要换**：即使 HTML 里图片路径写对了，发布时微信也会改写；**不要直接复制网页上的图片**，先存本地再传素材库。
3. **文中图片上下各空一行**，阅读不拥挤；`max-width:100%` 防溢出。

---

## 7. 官方富媒体组件（编辑器里点按钮插入，比手写 HTML 靠谱）

微信后台工具栏提供的组件本质上也是特殊 HTML 标签，**建议在编辑器里用按钮插入**，别手写：

`<mp-common-mpaudio>` 音频卡、`<mp-common-videosnap>` 视频号卡、`<mp-common-profile>` 公众号名片、`<mp-common-miniprogram>` 小程序卡、`<mp-common-poll>` 投票、`<mp-common-search>` 号内搜索、地理位置、问一问、腾讯视频 `<iframe>`、礼物等。

手写这些标签格式繁琐还容易错，直接在编辑器里点对应按钮即可。

---

## 8. 实操工作流：本地 HTML → 公众号后台（三种路径）

### 路径 A：本地写 HTML → 浏览器渲染 → 全选复制粘贴（你要的方式，推荐）

1. 用编辑器（VS Code / 记事本）写 HTML，**只用白名单标签 + 内联样式**，宽度不写死（或外层容器设 375px 以内预览）。
2. 浏览器打开 HTML 文件，确认字体、间距、配色效果。
3. 图片**先全部传到公众号素材库**，把 `mmbiz.qpic.cn` 链接填进 `<img src>`；本地占位图只是预览用。
4. 浏览器里选中**正文内容区域** → Ctrl+A / Ctrl+C（复制的是"渲染结果+富文本"）。
5. 打开公众号后台 → 新建图文 → 正文区 Ctrl+V 粘贴 → **微信自动清洗一遍**。
6. 点"预览"，**手机扫码真机检查**（重点：深色模式、图片清晰度、样式有没有被吃）。
7. 没问题 → 上传封面 → 发表。

> ⚠️ 不要尝试把"HTML 源码文本"粘进正文——微信会把它当纯文本显示成代码。**粘的是渲染结果**。

### 路径 B：Markdown/文本 → 转码工具（省心，适合长文）

推荐工具（都懂微信的坑，自动内联化、规避禁用属性）：

- **mdnice.com** — 免费、主题多、专为公众号设计，支持代码高亮/表格/公式，一键复制
- **md.openwrite.cn（doocs/md）** — 开源免费，微信 Markdown 编辑器，代码主题好看，支持 mermaid/公式
- **typezen.online** — 72 套排版模板（极简/商务/文艺/科技风）
- **135editor.com / xiumi.us（秀米）** — 模板库最全的商业编辑器，含"HTML 代码块"入口，适合无代码基础者

流程：Markdown/草稿 → 粘贴进工具 → 选主题调样式 → 点"复制"（复制的是排版后的富文本）→ 粘到公众号后台 → 上传图片 → 预览发布。

### 路径 C：开发者工具硬改（进阶，官方编辑器无"HTML 源码"按钮时的替代）

公众号编辑器没有公开的"源码模式"入口。想精确插入一段 HTML：

1. 编辑器正文点一下，出现光标。
2. 浏览器按 F12（Mac：Cmd+Option+I）打开开发者工具。
3. 找到正文区对应的节点（通常是最外层可编辑 div），右键 → **Edit as HTML**（Chrome/Edge）。
4. 粘贴代码 → 点击页面空白处保存 → 编辑器里就会渲染出效果。

> 此方式适合小段插入；整篇文章搬运仍建议路径 A。

---

## 9. 发布前自检清单（每条都有人踩过）

| # | 检查项 | 后果 |
|---|--------|------|
| 1 | 有没有用 `<style>`/外部 CSS/JS | 发布后被整体丢弃，样式全丢 |
| 2 | 有没有 `position:absolute/fixed` | 整行删除，元素位置崩掉 |
| 3 | 有没有 `id`/伪类/`@media`/动画 | 静默无效 |
| 4 | 图片是否全部来自微信图床 | 外链图裂图 |
| 5 | 图片宽度是否 ≤1080px、格式是否 WebP | 报错/变糊/无法上传 |
| 6 | 是否写了纯黑 `#000`、纯白底大块、box-shadow | 深色模式下刺眼/发光 |
| 7 | `<section>` 嵌套是否超过 15 层 | 被自动删除部分结构 |
| 8 | 有没有用 `line-height:0`、`opacity:0`、写死宽高 | 文字重叠 / 后台改不了图 / 移动端空白 |
| 9 | 是否用 `<pre>` 包了普通正文 | 移动端文字截断 |
| 10 | **手机预览了没**（含深色模式） | 只有真机预览才能发现被清洗掉的样式 |

---

## 10. 可直接套用的"合规 HTML 排版模板"

下面这个模板每个属性都在微信白名单内，可直接拿来当骨架（标题/正文/图片/引用/分割线都齐了）：

```html
<!-- 文章主体：两端留白容器（可整体调节） -->
<section style="padding: 0 12px;">

  <!-- 大标题：居中、加粗 -->
  <h1 style="font-size: 20px; color: #333333; text-align: center; line-height: 1.5; letter-spacing: 1px; margin: 24px 0 8px 0;">
    这里是文章主标题
  </h1>

  <!-- 副标题/导语 -->
  <p style="font-size: 14px; color: #888888; text-align: center; margin: 0 0 24px 0;">
    导语副标题或引言
  </p>

  <!-- 小节标题 -->
  <h2 style="font-size: 17px; color: #1a1a1a; line-height: 1.5; margin: 32px 0 12px 0; border-left: 4px solid #c7000b; padding-left: 8px;">
    一、小节标题（左侧红色竖线装饰）
  </h2>

  <!-- 正文段落 -->
  <p style="font-size: 16px; color: #3f3f3f; line-height: 1.75; letter-spacing: 0.5px; margin: 0 0 16px 0;">
    这里是正文。可以用 <strong style="color: #c7000b;">加粗变色</strong> 强调，
    也可以给关键词上 <span style="background-color: #fff3e0; padding: 2px 4px; border-radius: 3px;">高亮底色</span>。
    段与段之间用 16px 下边距隔开，阅读很舒服。
  </p>

  <!-- 引用/金句块 -->
  <blockquote style="margin: 24px 0; padding: 14px 16px; background-color: #f7f7f7; border-left: 4px solid #c7000b; font-size: 15px; color: #555555; line-height: 1.7;">
    这是引用块：浅灰底 + 左侧红色竖线，适合放金句、观点、数据小结。
  </blockquote>

  <!-- 居中的正文配图（图片链接换成微信图床地址） -->
  <p style="text-align: center; margin: 24px 0;">
    <img src="https://mmbiz.qpic.cn/你的微信图床图片链接" style="width: 100%; max-width: 100%; border-radius: 8px;" alt="图片说明" />
  </p>
  <p style="font-size: 13px; color: #999999; text-align: center; margin: -12px 0 24px 0;">
    ▲ 图注说明文字（灰色小字）
  </p>

  <!-- 卡片：图片+文字并排（flex 两列） -->
  <section style="display: flex; align-items: center; background-color: #fafafa; border-radius: 8px; padding: 14px; margin: 24px 0;">
    <img src="https://mmbiz.qpic.cn/你的图片" style="width: 96px; height: 96px; border-radius: 6px; object-fit: cover;" alt="" />
    <section style="margin-left: 12px;">
      <p style="font-size: 15px; color: #333333; font-weight: bold; margin: 0 0 6px 0;">卡片小标题</p>
      <p style="font-size: 14px; color: #666666; line-height: 1.6; margin: 0;">卡片描述文字，最多两三行，配合缩略图更精致。</p>
    </section>
  </section>

  <!-- 分割线（渐变细线或纯色细线） -->
  <section style="height: 1px; background-color: #e5e5e5; margin: 32px 0;"></section>

  <!-- 结语 -->
  <p style="font-size: 16px; color: #3f3f3f; line-height: 1.75; margin: 0 0 8px 0;">
    结尾段落……
  </p>
  <p style="font-size: 14px; color: #999999; text-align: right; margin: 0;">
    — 完 —
  </p>

</section>
```

> 结构提示：正文建议统一用一个 `padding` 容器包住全部内容（上面的最外层 `<section>`），可以整体控制两侧留白；内层不要再无限套 `<section>`（防嵌套过深）。

---

## 11. 参考来源

1. 微信官方开发者文档《公众平台编辑器插件开发规范》：developers.weixin.qq.com/doc/service/guide/product/plugin_spec.html（含 CSS 红线、结构验证接口 verify_article_structure、嵌套层级限制）
2. axtonliu.ai《微信公众号图文的 HTML/CSS 支持概览》（2025-03，标签/CSS 白名单与过滤规则的最全整理 + 官方兼容模板）
3. 哈哈敲敲/博客园《微信公众号 css 布局和 SVG 推文的一些坑》（百分比失效、transform、SVG/iOS 兼容坑）
4. DeepWiki《WeChat Platform Compatibility》（578px 内容宽度、编辑器的兼容实现）
5. 社区逆向实测文章《公众号支持哪些 HTML/CSS 能力》（通过开发者工具拆解编辑器真实保留的标签与样式）
6. Canva / ima 腾讯《公众号全场景图片设计规范》：封面 900×383（2.35:1）、次条 1:1、正文图 750–1080px、GIF 限制、WebP 不支持
7. huasheng.ai《公众号配图设计规范与最佳实践》（深色模式 6 规则、安全色值、字号参数）
8. 365编辑器 / 腾讯云开发者社区《公众号写作排版指南 v2.0（适配 Dark Mode）》：深色模式色值反转表（#232323→#c3c3c3 等）
9. 掘金/CSDN 对 mdnice、doocs/md、Md2All 等 Markdown 转公众号工具的原理与使用总结
10. LobeHub / Claude Skills 社区《wechat-article》公众号排版 skill：正文 15px、行距 1.8、字距 0.5px、段距 16px、正文色 #3f3f3f 等参数标准
