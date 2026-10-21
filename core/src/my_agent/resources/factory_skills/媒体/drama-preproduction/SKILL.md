---
name: drama-preproduction
description: AI 短剧 / AI 漫剧前期制作工作流：剧本 → 角色设定 → 分镜脚本 → 画面提示词 → 审校合规。触发场景：做 AI 短剧/漫剧、写短剧剧本、写分镜脚本、设计角色一致性、生成文生图/图生图画面提示词、审校剧本文案。涵盖短剧结构、角色卡与一致性策略、分镜表模板、画面提示词库、合规审校清单，工具无关。
author: Soulmate Agent团队成员：岸
---

# AI 短剧 / AI 漫剧前期制作 (drama-preproduction)

定位：从创意到「逐镜头画面提示词」的完整前期管线。视频生成、配音、剪辑等后期步骤不在本技能范围（工具迭代快，另行维护）。

产出链：立项定调 → 剧本 → 角色卡 → 分镜表 → 定妆图 → 画面提示词 → 审校文档。

## 快速开始（怎么触发、从哪进入）

| 用户想做什么 | 从这里开始 |
|---|---|
| 「帮我做一部 AI 短剧/漫剧」 | 步骤 1，逐步确认推进 |
| 「写个短剧剧本」/「给个钩子」 | 步骤 2（先读 `references/story-structure.md`） |
| 「角色总是不一样 / 怎么保持一致性」 | 步骤 3（先读 `references/character-card.md`） |
| 「写分镜」/「拆镜头」 | 步骤 4（先读 `references/storyboard-template.md`） |
| 「生成画面提示词」 | 步骤 6（先读 `references/prompt-library.md`） |
| 「帮我把把关 / 审校」 | 步骤 7（先读 `references/review-checklist.md`） |
| 「做不下去了 / 出错了」 | 直接看「异常与修正」或 `references/faq.md` |

不知道从哪开始 → 从步骤 1 走，每步结束向用户确认产出是否符合预期，再进下一步。

## 文档导航（什么时候读哪份）

| 阶段 | 必读 |
|---|---|
| 剧本 | `references/story-structure.md` |
| 角色 | `references/character-card.md` + `assets/character-card-template.md` |
| 分镜 | `references/storyboard-template.md` + `assets/storyboard-template.csv` |
| 画面提示词 | `references/prompt-library.md` |
| 审校 | `references/review-checklist.md` |
| 卡住/出错 | `references/faq.md` |

## 异常与修正（反馈回路）

每步结束后必须做一次「产出核对」，而不是直接推进：

- 用户对产出不满意 → 停下，问清差异点，**只改差异，不要整段重写**。
- 输入数据缺失/格式不对 → 列出缺什么、让用户补，不猜。
- 生成失败（工具报错/超时）→ 按 FAQ「生成失败」处理，保留已生成部分。
- 中途改需求（换题材/加角色/改平台）→ 回退到对应步骤（改题材→步骤2；加角色→步骤3），提示影响面。

完整场景见 `references/faq.md`，遇到问题先查它。

## 制作管线

### 1. 立项定调
确认并记录：平台（抖音/快手/视频号/小红书，决定时长与画面比例，竖屏 9:16 为主）、单集时长（通常 1~3 分钟）、类型（漫剧/真人 AI 短剧）、风格基调（一句话定位，如「赛博朋克悬疑漫剧」）、目标观众与调性。
产出：`project-brief.md`（平台/时长/类型/风格/题材一句话）。

### 2. 剧本创作
读取 `references/story-structure.md` 后创作。
- 结构：黄金 3 秒钩子 → 冲突升级 → 反转 → 结尾钩子（留看下集）。
- 每集标注：目标 / 冲突 / 反转 / 结尾钩子。
- 分支：漫剧（冲突夸张、信息密度高、节奏快）；真人短剧（情感细腻、台词生活化、反转符合人设）。
产出：分集剧本，每集含上表四要素。

### 3. 角色设定
读取 `references/character-card.md`。为每个主要角色建卡：身份 / 外貌锚点 / 服装 / 性格 / 语气 / 口头禅；提炼一句「一致性锚点描述」（后续所有画面生成必须复用）；明确角色间关系与冲突点。
产出：每角色一份 `character-card`（用 `assets/character-card-template.md` 模板）。

### 4. 分镜脚本
读取 `references/storyboard-template.md`。把每集剧本拆成逐镜头，填写 `assets/storyboard-template.csv`。
- 字段：镜头号 / 景别 / 运镜 / 时长(秒) / 画面描述 / 台词 / 字幕 / 音效 / BGM / 生成方式。
- 分支：漫剧（分镜可舞台化、夸张构图，镜头数可更多）；真人短剧（运镜接近实拍：推拉摇移、过肩、特写）。
产出：本集完整分镜表（CSV），含镜头间衔接检查。

### 5. 角色定妆图（文生图）
按角色卡为每个主要角色生成 2~3 张定妆图；与用户确认后锁定 1 张作为「一致性参考图」；保留该图的完整提示词与负面提示词。
产出：每角色 1 张锁定定妆图 + 提示词存档。

### 6. 逐镜头画面提示词
读取 `references/prompt-library.md`。逐镜头生成画面提示词：角色锚点 + 场景 + 镜头 + 风格 + 光影；每镜头给 2~3 个备选；所有涉及该角色的镜头必须复用角色锚点语句。
产出：分镜表补充「画面提示词」列 + 备选列表。

### 7. 审校与合规
读取 `references/review-checklist.md`：剧本（逻辑自洽、反转成立、无烂尾）、角色（每镜头人物与角色卡一致）、分镜（衔接连贯、时长合计符合目标）、合规（AI 生成标注、版权、平台违禁词）。
产出：审校记录 + 修改后的定稿文档集。

## 分支对照（漫剧 vs 真人 AI 短剧）

| 维度 | 漫剧 | 真人 AI 短剧 |
|---|---|---|
| 视觉风格 | 日漫 / 国漫 / 3D 渲染 | 写实 / 电影感 / 胶片 |
| 分镜 | 夸张构图、舞台化 | 接近实拍运镜 |
| 台词 | 高信息密度、金句多 | 生活化、情绪化 |
| 一致性难点 | 画风统一 + 角色外貌 | 面部特征 + 口型 |
| 后续（另行维护） | 动态化分镜 | 图生视频 + 口型驱动 |

## 文件约定

- 所有中间产物存到项目目录下的 `drama-project/<剧名>/`，命名：01-project-brief.md、02-script-EP01.md、03-character-card.md、04-storyboard-EP01.csv、05-prompt-EP01.md、06-review.md。
- 中文内容、直白表述，避免文学化空话（提示词除外）。


## 参考文件

- `references/story-structure.md`、`references/character-card.md`、`references/storyboard-template.md`、`references/prompt-library.md`、`references/review-checklist.md`、`references/faq.md`
- `assets/character-card-template.md`、`assets/storyboard-template.csv`
