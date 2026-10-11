---
name: official-document-writing
description: 中文公文与事务材料写作：起草 / 改写 / 压缩 / 润色 / 审校各类公文、事务材料及新闻消息 / 编者按 / 新闻评论，含文种核对、GB/T 9704 版式与抗 AI 味。触发场景：写申请 / 请示 / 报告 / 通知 / 函 / 批复 / 方案 / 纪要 / 公告 / 通报 / 制度 / 总结 / 调研 / 讲话 / 致辞 / 述职等，或要求文稿处理、去口语化、降 AI 味。
author: Soulmate Agent团队成员：岸
---

# 中文公文与事务材料写作


## 适用场景

- 起草、改写、压缩、润色、审校中文公文与事务材料：申请、请示、报告、通知、通告、意见、决定、决议、议案、公报、命令、函、复函、批复、说明、方案、纪要、公告、公示、通报、制度、规定、办法、细则、操作规程、工作要点、总结、调研、讲话、致辞、主持词、述职、可研、审查材料、技术需求、采购、整改、反馈等。
- 文种核对、去口语化、降 AI 味、GB/T 9704 版式、Word 正文整理。
- 新闻消息（会议消息、活动消息等）、编者按、新闻评论的起草、改写与审核——公文体例的新闻分支，守事实边界与引述强度。
- 涉及 AI 算力、模型推理/训练、智算中心、模型服务资源类材料的起草与审校。
- 不适用：英文、文学、营销软文、社媒文案、个人求职信、代码说明（走其他功能）。

## 步骤

1. **判真实稿 / 试写稿**：有现实材料、现实事项或实际办理用途 → 按真实稿进文种路由；仅需写法样稿、且没有具体事项/状态/对象/材料/用途 → 读 `assets/official-document-writing/references/trial-draft-routing.md`；用户明确模拟/虚构/生成测试同样读该页。模糊或未决状态按现实事项处理。
2. **理解需求**：识别任务与交付件（起草/改写/压缩/审核/格式）、稿件用途（谁以何身份写给谁）、材料与修改范围、篇幅与形式。只要求指定文字替换且其余逐字保留 → 读 `assets/official-document-writing/references/targeted-checks.md`，直接定位目标、生成并核对改后全文；该替换任务不进入文种选择、篇幅检查、抗 AI 改写。目标有歧义先澄清。
3. **选文种**：按 `assets/official-document-writing/references/reference-index.md` 为每份稿件选一个主叶；标题、模板、正文用途或行文关系冲突时，用 `genre-routing.md` 判定实际用途。独立稿件及有独立用途的附件分别选路。新闻类稿件选 `genre-playbook-news-message.md` / `genre-playbook-editorial-note.md` / `genre-playbook-news-commentary.md` 之一。
4. **按任务加读**：
   - 起草 → 按主文种组织必要要素与合理分析。
   - 改写 → 以最新版底稿为唯一主线；结构动作读 `structure-editing.md`，字段动作读 `field-editing.md`。
   - 压缩或限字 → `compression-details.md`，保留硬要素、事实状态与用户点名字段。
   - 审核/复核/审校 → 对应主文种叶 + `review-checklist.md`。
   - 格式交付 → `format-gbt9704.md`（Word/docx/GB/T 9704/红头/正式版式）。
   - 涉及 AI 算力 → 在主文种叶上叠加 `ai-compute-docs.md`。
5. **写作四步**（`assets/official-document-writing/references/writing-rules.md`）：
   1) 材料与分析；2) 成稿与篇幅（有字数要求时运行 `python scripts/draft_length.py`）；3) 复核并运行 `python scripts/prose_lint.py` 扫描风险（用法见 `prose-lint-usage.md`，同稿已合并检查则不重复运行）；4) 交付，按本轮原始请求核对整条回复。
6. **正文形态收口**：正式正文直接呈现事实、办理事项与有据分析。严禁出现 AI 身份自述、提示词披露、思考过程、起草步骤、脚本结果、起草免责话术及"正文如下"等引导语。普通文字稿不得用井号标题、Markdown 加粗、整稿代码围栏或横线包装（用户明确要求 Markdown/代码/固定模板除外）。

## 文种叶：新闻消息 / 编者按 / 新闻评论

新闻类稿件是公文体例的新闻分支，按公文主线处理，但守更严的事实边界。

- **选文种**：新闻消息（会议消息、活动消息等）→ `assets/official-document-writing/references/genre-playbook-news-message.md`；编者按 → `genre-playbook-editorial-note.md`；新闻评论 → `genre-playbook-news-commentary.md`。判据：稿件对象为新闻稿件，用途是报道事实或表达评论观点。
- **守事实边界**：普通消息不自行补「这不代表 / 这不表示 / 这不构成」等作者判断；材料给出的正式声明、司法判断、专家意见、受访者观点须标明来源，并按原强度转述，不拔高不削弱。
- **编者按**：叙述站在编发者位置；引用作者经历、报道事实或被编发者观点时保留其归属；栏目沿革、编发安排、评价依据取自材料。
- **结构与复核**：沿用公文主线四步——材料与分析 → 成稿与篇幅（`scripts/draft_length.py`）→ 复核与 `scripts/prose_lint.py` → 交付；正文形态约束同公文（无 Markdown 包装，除用户明确要求）。
- **不适用**：文学创作、营销软文、社媒文案（走其他功能）。时效事实需更新核验时启用 `external-research.md` 并记录来源与检索口径。

## 输入输出

- 输入：用户需求（任务 + 文种 + 用途）+ 现实材料/旧稿/模板/字段表（.docx/.md/.txt 或粘贴）。
- 输出：一份或多份稿件，或审稿意见 / 审核后的改好稿件；可按需交付 Word、GB/T 9704 版式。

## 注意事项

- 用户模板、最新版底稿、明确标题与用途优先；用户已有提纲、模板、标题顺序或字段表优先保留。
- 材料只给回执接收方、联系人或承办部门时，不据此补发文单位；未给的主送、落款不补泛称。
- 篇幅与字数是硬约束；真实稿的"只给""仅"等限定适用于整条回复。
- 不熟悉的新文种/新材料类型/特殊事务场景，或需核查通用写法与时效事实时，读 `external-research.md` 做定向联网核查；记录来源、日期、检索口径，冲突或无法核验列为待确认，网络材料仅作背景依据。
- 网页复制稿先剥离来源、栏目路径、责任编辑等元信息；"关于印发"的通知壳、被印发文件正文与附件关系分开处理。

## 可复用示例

- 起草：「写一份 XX 单位关于 XX 的请示，约 800 字」→ 判真实稿 → 选请示主叶 → 组织要素 → `draft_length.py` → `prose_lint.py` → 交付。
- 压缩：「把这份报告压到 800 字，保留金额和数据」→ 真实稿路径 → `compression-details.md` → `draft_length.py`。
- 只改字：「把这些段落里的"部"改成"厅"，其余别动」→ `targeted-checks.md`，生成改后全文并核对，不进入文种选择。
- 格式：「按 GB/T 9704 出一版红头文件」→ 主文种叶 + `format-gbt9704.md`。

## 支撑文件

- `scripts/draft_length.py` — 字数统计与篇幅核对。
- `scripts/edit_scope.py` — 修改范围控制。
- `scripts/material_diff.py` — 底稿与新稿差异比对。
- `scripts/prose_lint.py` — 语言风险扫描（AI 味、套话、风险词）。
- `assets/official-document-writing/references/` — 源技能文种手册与规则页：`reference-index.md`（总入口）、`genre-routing.md`、`genre-playbook-*.md`（各文种手册，含 `genre-playbook-news-message.md`、`genre-playbook-editorial-note.md`、`genre-playbook-news-commentary.md` 三个新闻叶）、`writing-rules.md`、`format-gbt9704.md`、`review-checklist.md`、`prose-lint-usage.md`、`external-research.md`、`trial-draft-routing.md`、`targeted-checks.md` 等。
