---
name: zhihu-research-page
description: 通过大规模联网搜索自动创建知乎风格的深度知识网页，样式高度还原 zhihu.com。生成多章节、多答主模拟回答页面，含大量有效中文字与真实搜索引用。支持手动裁剪为任意比例版本（如「执行 5% 版本」）。适用于生成知识专题页、学习路径教程、产品深度百科、行业研究报告等需要系统整理某一主题知识的场景。触发：知乎风格网页、深度知识页、研究页、知识专题、学习路径教程、行业研究报告、zhihu-research-page。
author: Soulmate Agent团队成员：岸
---

# 一句话生成知乎高质量回答网页（可自由剪裁）

输入一个研究主题 → 自动产出：

- 📄 一个知乎风格的完整 HTML 单页（含顶栏 / 问题头 / 侧栏 / 10 章节 / 页脚）
- 🔗 每章 ≥11,000 有效中文字，全页 ≥100,000 字（100% 版本）
- 🔍 累计 ≥500 次真实 WebSearch（7~8 个并行搜索代理）
- 📎 242+ 条真实可点击外链（**禁止编造 URL**）
- 🧪 字数核验 + 结构校验脚本

## 用法示例

```
/ zhihu-research-page 执行5%版本
主题：什么是 Harness Engineering？

/ zhihu-research-page 执行200%的v2版本
主题：各种调式的流行歌曲都有什么特点，它们各有什么代表作？
```

## 工作区目录约定

为避免工作区根目录散落中间文件，所有产出严格按以下目录存放：

```
工作区/
├── index.html                  # 最终 HTML 骨架（唯一留在根目录的文件）
├── images/                     # 所有图片资源（与 HTML 同目录，相对路径引用）
├── other/                      # 网页草稿、脚本、中间产物
│   ├── _draft_*.html           # 各章节 HTML 草稿
│   ├── assemble.py             # 从 skill 复制的拼接脚本
│   ├── scan_html.py            # 从 skill 复制的预扫描脚本
│   └── index_skeleton.html     # 骨架备份（方便二次运行还原）
└── research_result/            # 搜索结果及中间产物
    └── search_result.md        # 搜索结果累积文件
```

**铁律**：

- 阶段 0 第一步：`mkdir -p ./images ./other ./research_result`
- 所有路径在命令行和代码中**显式使用 `./other/` 和 `./research_result/` 前缀**，不依赖 `cd`
- 最终交付的 `index.html` 仍在根目录

## 异常处理

**遇到异常时，必须先读取 `TROUBLESHOOTING.md`** 查找匹配方案。该文件覆盖 12 类高频异常的根因和修复步骤（配额耗尽、task-notification 不实、`<code>` 字体异常、Windows 编码崩溃、颜色归一误伤、字数失真、权限被拒等）。仅当文件中无匹配方案时，才自行分析处理。

## 工作流总览（8 阶段）

```
[0] 收集输入 → [1] 诊断问题 → [2] 创建骨架 HTML → [3] 并行搜索(500+)
→ [4] 规划章节 → [4.5] 答主身份与头像配置 → [5] 并行写章 → [6] 组装校验 → [7] 交付
```

**严禁跳过任何阶段**。搜索和撰写都通过 Subagent 委托执行，主流程不直接生成章节内容。

### 子代理权限配置

使用 Agent 工具启动的子代理在写文件时经常遇到 Write/Bash 权限被拒。需在项目根目录的 `.claude/settings.local.json` 中显式授权对 `_draft_*.html`、`index.html`、`assemble.py`、`images/*` 的 Write/Edit/Bash 权限；若配置中有 `additionalDirectories`，确保当前工作区路径被包含。

### 阶段 0：收集输入

| 参数 | 默认 | 说明 |
|------|------|------|
| 研究主题 | 从对话上下文自动提炼 | 用户未指定则扫描上下文提炼一句中文主题 |
| 参考材料 | 空 | 用户提供的文档/链接/笔记，注入所有子代理 |
| 章节建议 | 按主题自动规划 | 用户可指定 >5 个章节标题 |
| 输出路径 | `./index.html` | 成品 HTML 路径 |
| 语言 | 中文 | 章节撰写语言 |
| 部分执行比例 | 无 | 如「仅执行 3%」，按比例缩减参数 |

**主题提炼规则**：用户只说「执行 skill / N% 版本」而未给主题时，**不追问用户**，直接从当前对话上下文提取。

**教程/学习模式**：主题含「教程 / 教学 / 学习路径 / 怎么做 / 入门 / 指南 / 上手」等关键词时自动启用——提炼答主背景、必要时提问（≤2 轮）、搜索侧重入门教程与避坑、写作目标为「跟着做就能上手」。

### 部分执行模式（N% 版本）

用户指定「执行 X% / N% 版本」时按公式等比缩减，主题与上一版本完全相同，**N 可为任意正数**：

| 参数 | 完整版 | N% 版本 |
|------|--------|---------|
| 工作目录 | 当前工作区 | 新建 `v{M}_{N}pct/`（M = 上一版本号+1，同级） |
| 搜索次数 | ≥500 | `max(5, floor(500 × N/100))` |
| 每章字数 | ≥11,000 | `max(100, floor(11000 × N/100))` |
| 全页字数 | ≥100,000 | `floor(100000 × N/100)` |
| 章节数 | 10 | `max(3, min(30, floor(10 × N/100)))` |
| 搜索代理数 | 3 轮串行 | N%≤100% 用 1 个；>100% 用 `min(6, floor(3 × N/100))` |
| HTML title / h1 | 主题 | 追加「（{N}%版本）」 |

**铁律**：新目录与上一版本目录同级；目录内建 `images/`、`other/`、`research_result/`；title 与 h1 必须含「N%版本」；主题与大纲与上一版本一致，仅等比压缩。

### 阶段 1：诊断问题（搜索之前）

1. **拆解问题**：核心问题（1 句）、关键子问题（3~5 个）、预期答案轮廓。
2. **确定搜索方向**：规划 7 个搜索子方向，互不重叠。
3. **拟定临时问题标题**：问句形式、有吸引力，后续可微调。

### 阶段 2：创建骨架 HTML（index.html）

1. 读取 `references/css-template.css` 的完整内容，嵌入 `<style>...</style>` 块。**不要修改 CSS**。
2. 按模板构建 HTML 结构（顶栏 `zh-header` / 问题头 `zh-card` / `zh-main` / 侧栏 `zh-sidebar`），正文区留 `<!-- ASSEMBLE -->` 占位标记。
3. CSS 从 skill 目录读取，写入**工作区**的 `index.html`；必须完整嵌入，不缩略。

### 阶段 3：并行搜索（≥500 次真实搜索）

**核心教训**：per-session 搜索配额是主子代理共享硬限——7 代理并行各要求 ≥72 次会大量触顶空转。**改为 3 轮串行**：每轮最多 3 个代理，每个 ≥72 次；剩余不足 72 次时集中给 1 个代理。官方文档优先用 `WebFetch` 抓取（不计入搜索配额）。

- 搜索代理 Prompt 模板见 `templates/search_agent_prompt.md`（读入并替换 `{direction}`）。
- **子代理完成验收标准**：task-notification 元数据不可信，**唯一验收方式是 `ls` 检查指定文件已生成 + 文件大小 > 0**。代理必须把结构化报告写入明确文件路径（如 `./research_result/report_XX.md`）。
- **search_result.md 协同积累**：主流程在每个搜索代理回传后**立即**把结构化结果追加到 `./research_result/search_result.md`（用 Python `open(path, "a")` 追加，比 Edit 稳定），并更新文件头的「累计搜索次数」「已覆盖子方向」。写入动作只由主流程串行执行，代理不直接写该文件。
- 各代理回传后，从所有区块的「关键数据/事实」提取 `- 来源：URL`，合并为去重来源池清单，阶段 5 传给撰写代理。

### 阶段 4：规划章节（证据驱动）

**严禁在搜索之前猜测章节标题。** 从搜索报告提取高频主题、争议焦点、知识缺口，设计 10 个章节（逻辑递进：概念→原理→实践→生态/避坑），标题简洁（≤20 字）。将章节列表写入**工作区**的 `assemble.py` 的 `CHAPTERS` 变量，并为每章拟 3~5 条预期覆盖要点。

### 阶段 4.5：答主身份与头像配置

**默认策略**：使用 DiceBear 风格化 SVG 头像（稳定、统一、零搜索成本）。仅当用户**明确要求**真实头像时才启动身份搜索。

头像三级优先级：① 真实人物公开头像（公开可验证直链）；② DiceBear 风格化 SVG（`https://api.dicebear.com/7.x/{bottts-neutral|avataaars|notionists}/svg?seed=<英文短语>&backgroundColor=<hex>&radius=50`）；③ 单字符占位 div。

**铁律**：绝不编造图链；身份不明的真实人物宁弃用；不依赖 WebFetch 测可达。

**缓存到本地**：所有可用头像下载缓存到 `./images/`（真实头像保留原始格式，DiceBear 存 `.svg`），HTML 中 `src` 指向本地相对路径（如 `./images/ch-01.png`）。作者块统一结构：

```html
<div class="zh-answer__author">
  <div class="zh-answer__author-avatar">
    <img src="./images/ch-01.png" alt="{答主名}头像" width="44" height="44" style="border-radius:50%;display:block">
  </div>
  <div class="zh-author__meta">
    <div class="zh-author__name">{答主名}</div>
    <div class="zh-author__bio">{一句话简介}</div>
  </div>
  <button class="zh-btn--follow" type="button">关注</button>
</div>
```

头像路径注入到章节写作代理的 Prompt 中，代理不得自行编造。模板见 `templates/author_block.html`。

### 阶段 5：并行写章

一条消息批量启动 10 个撰写代理（`subagent_type: general-purpose`, `run_in_background: true`），每个代理负责一个章节，必须写入指定 `_draft_ch_XX.html`，并用 Python 脚本自验有效中文字 ≥11,000。Prompt 模板见 `templates/writing_agent_prompt.md`（替换 `{topic}`/`{chapter_title}`/`{chapter_points}`/`{chapter_urls}`/`{chapter_id}`）。写完后运行 `python -X utf8 scripts/wordcount_check.py ./other/_draft_ch_XX.html`，结果 ≥11,000 且与 agent 自述差 ≤5% 才算完成。建议每章补 30~60 次搜索核实数据点。

### 阶段 6：组装与核验

```bash
cp <skill_dir>/scripts/scan_html.py ./other/scan_html.py
cp <skill_dir>/scripts/assemble.py ./other/assemble.py
# 编辑工作区副本的 assemble.py，把阶段 4 的章节填入 CHAPTERS
python -X utf8 ./other/scan_html.py     # Windows 必须加 -X utf8 / PYTHONIOENCODING=utf-8
python ./other/assemble.py
```

`scan_html.py` 检测四类 `<code>` 标签问题（开闭不匹配 / 块级标签嵌套 / 异常闭合 / 交叉嵌套）；**字体泄漏和结构异常 99% 来自 `<code>` 标签封闭不当，而非 CSS**。问题清零后再跑 assemble。

`assemble.py` 会：补 h2/h3 样式 → 幂等剥离旧章节并注入锚点 id → 替换 `<!-- ASSEMBLE -->` → 去重 `<style>` → 统一硬编码主题蓝 → 更新回答数 → 重建侧栏 → 自动自查 5 项 → 写入成品并打印字数。

**幂等性**：`<!-- ASSEMBLE -->` 首次运行后被消费，重跑需从 `index_skeleton.html` 还原骨架。

**达标判断**：`总计 < 100,000` 时找出最薄弱的 2~3 章，回阶段 5 扩写，重跑 scan → assemble 直至达标。N% 模式先编辑 `TARGET_WORDS = floor(100000 × N/100)`。

### 阶段 7：交付与收尾

- 结构校验：含 `zh-header`/`zh-sidebar`/`zh-main`；`<article>` 数与回答数匹配；锚点 id 与侧栏 href 一致；`<code>` 开闭数量匹配；每章作者块含非空 `src`（用 `grep -o 'author-avatar[^<]*'` 逐行确认，不依赖跨行正则）。
- 链接抽检：用 WebFetch 对 2~3 条关键官方链接做可达性验证。
- 交付并通报：全页有效中文字数、各章字数分布、搜索总次数、外链总数、链接抽检结果。

## 质量规则（贯穿全局）

| 规则 | 标准 |
|------|------|
| 有效中文字数口径 | 去 `<script>`/`<style>`/所有 HTML 标签后的汉字 + 中文标点；英文代码和英文链接文本不计 |
| 链接真实性 | 禁止编造任何 URL，每个链接必须来自真实搜索或已核验来源池 |
| 搜索次数 | 阶段 3 总搜索 ≥500 次；阶段 5 每章再补 30~60 次 |
| 每章字数 | 每章 ≥11,000 有效中文，全页 ≥100,000 |
| 风格一致 | 所有章节用知乎回答体，含作者块 + 操作条 |
| 诚实性 | 不同版本/来源的矛盾信息如实标注 |
| `<code>` 标签 | 开闭数量必须匹配，内部不得嵌套块级标签，严禁与 `<strong>` 交叉嵌套 |
| 头像真实性 | 禁止编造图链；真实人物身份须 ≥2 独立来源交叉印证 + curl 亲测可达，不足时降级 DiceBear |
| 图片路径 | 所有 `<img>` 的 `src` 必须指向本地 `./images/` 相对路径 |
| CSS 类名隔离 | 页面级包裹层用 `zh-page`（非 `zh-body`），章节正文容器用 `zh-answer__body` |
| 组装前扫描 | 运行 `assemble.py` 前必须先跑 `scan_html.py` 并清零 |

## 资源文件

- `references/css-template.css` — 知乎风格 CSS（直接嵌入 `<style>`）
- `scripts/assemble.py` — 通用拼接与字数核验脚本（使用前编辑 CHAPTERS）
- `scripts/scan_html.py` — HTML `<code>` 标签预扫描脚本
- `scripts/wordcount_check.py` — 独立字数核验 + `<code>` 完整性检查
- `templates/writing_agent_prompt.md` — 章节撰写代理 Prompt 模板
- `templates/search_agent_prompt.md` — 搜索代理 Prompt 模板
- `templates/author_block.html` — 统一作者块 HTML 模板
- `TROUBLESHOOTING.md` — 12 类高频异常及处理方法（遇到异常先读）
