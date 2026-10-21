---
name: novel-writing
description: 多平台中文网文分章节创作助手。支持番茄、七猫、起点、晋江、纵横、飞卢、豆瓣、知乎盐选等主流平台，按平台自动适配章节字数、节奏模式与润色风格；支持悬疑/言情/奇幻/科幻/历史等题材，10–200 章长篇创作，结尾设置悬念钩子，并做去 AI 痕迹的深度润色；含大纲/人物档案/情绪曲线/黄金开篇模板与字数检查脚本。触发词：写网文、创作小说、分章节写作、连续剧情、章节悬念、长篇小说、番茄/起点/晋江/七猫小说、网文创作助手。
author: Soulmate Agent团队成员：岸
---

# 多平台中文网文分章节创作

## 平台适配（核心）

创作开始前必须确认 **发布平台**，并读取 `references/platform-profiles.md` 获取该平台配置：

| 平台 | 平台键 | 章节字数 |
|-----|--------|---------|
| 番茄小说 | `tomato` | 2200-2800 |
| 七猫免费小说 | `qimao` | 2200-2800 |
| 起点中文网 | `qidian` | 3000-4500 |
| 纵横中文网 | `zongheng` | 3000-4000 |
| 晋江文学城 | `jjwxc` | 2500-4000 |
| 飞卢小说网 | `feilu` | 3000-5000 |
| 豆瓣阅读 | `douban` | 3000-6000 |
| 知乎盐选/短篇 | `zhihu` | 8000-15000/篇 |
| 通用/其他 | `generic` | 2500-3500 |

用户未指定平台时，在第一阶段询问；指定了则直接采用对应配置。

## 核心流程

### 第一阶段：7 问确认（锁定爆款基因）

逐一询问用户，每个问题提供选项供其选择。

**问题 0：发布平台（必选，决定全局参数）**
选项：番茄小说（免费流量、快节奏、情绪标签）/ 七猫免费小说（同番茄策略）/ 起点中文网（男频长篇、世界观、升级体系）/ 纵横中文网（传统男频、升级流）/ 晋江文学城（女频、CP、情感细腻）/ 飞卢小说网（极快爽点、系统/同人）/ 豆瓣阅读（品质向、偏文学节奏）/ 知乎盐选/短篇（单篇闭环、强反转）/ 通用/其他（自定义平台规则）。
记录：`平台` + `平台键`。

**问题 1：情绪标签（必选，决定推荐方向）**
选项：打脸爽文（扮猪吃虎、马甲掉落、逆袭碾压）/ 极致虐恋（追妻火葬场）/ 爆笑反套路（沙雕吐槽、神转折）/ 悬疑惊悚（细思极恐、规则怪谈、烧脑反转）/ 治愈甜宠（日常温馨、双向奔赴、养成系）/ 脑洞大开（系统流、末日囤货、星际经营）/ 升级逆袭（等级突破、换地图、长期成长，起点/纵横/飞卢推荐）/ CP 推拉（强强、救赎、双向奔赴，晋江推荐）。
若平台与情绪标签不匹配，提示用户并建议更契合的组合（参考 `references/platform-profiles.md` 推荐表）。

**问题 2：题材与风格**
选项：悬疑推理 / 现代言情 / 古代言情 / 奇幻玄幻 / 科幻未来 / 武侠仙侠 / 历史架空 / 都市现实。

**问题 3：主角设定**
选项：男性主角（独角戏）/ 女性主角（独角戏）/ 双主角（男女双线）/ 群像戏（多线叙事）。需要时继续追问职业/身份。

**问题 4：主角核心反差点**
选项：表面摆烂实际卷王 / 社恐但被迫当众打脸 / 被虐后觉醒反杀 / 老实人黑化 / 隐藏大佬装萌新 / 看似废柴实则天赋异禀 / 其他（自行描述）。

**问题 5：核心冲突**
选项：生死存亡 / 查明真相 / 爱情阻碍 / 复仇雪恨 / 权力争夺 / 成长突破 / 守护保护。

**问题 6：章节数量**
选项：10 章（短篇，约 2-3 万字）/ 30 章（约 6-8 万字）/ 50 章（约 10-14 万字）/ 100 章（约 22-28 万字）/ 200 章（约 44-56 万字）/ 自定义。
知乎盐选/短篇模式：改为询问"篇数"，单篇 8000-15000 字。

7 问收集完成后，进入第二阶段。

### 第二阶段：规划 + 二次确认

1. **创建项目文件夹**：`novels/[小说名称]/`
2. **生成大纲**：`00-大纲.md`，用 `templates/outline-template.md`（番茄用 `templates/outline-template-tomato.md`），顶部写入项目配置（平台、字数、节奏）。
3. **生成人物档案**：`01-人物档案.md`，用 `templates/character-template.md`（番茄用 `-tomato` 版）。
4. **生成情绪曲线图**：`02-情绪曲线.md`，用 `references/emotion-curve.md` 中对应平台的节奏节（番茄用 `references/tomato-emotion-curve.md`）。
5. **生成黄金开篇**：`03-黄金开篇.md`，用 `references/golden-opening.md` 输出三个版本（字数按平台要求；番茄用 `references/tomato-golden-opening.md`）。

完成后展示规划摘要（含平台适配说明）并请求确认。同意后进入第三阶段。

### 第三阶段：疯狂创作（含数据反馈）

按顺序逐章创作，每章完成展示摘要和字数统计，询问"是否继续下一章？"；每完成 5 章执行阶段性检查：

1. 生成本阶段节奏报告：情绪曲线、爆点密度、互动点预测。
2. 询问数据反馈（如有）：番茄/七猫看完读率/追读率；起点看收藏/段评；晋江看收藏/章评。
3. 根据反馈调整后续大纲：为高人气配角加戏、强化爆款情绪标签。

## 逐章创作流程

**1. 写前分析**
1. 读 `00-大纲.md` —— 确认平台配置、TODO list 和已完成章节摘要。
2. 读上一章摘要和结尾钩子。
3. 读 `02-情绪曲线.md` —— 确认本章在节奏单元中的位置和任务。
4. 更新 `00-大纲.md` TODO list，将本章标记为"进行中"。
5. 设计开头钩子 —— **前 20% 必须有即时冲突**（见 `references/chapter-guide.md`）。
6. 规划场景 —— 本章 3–5 个场景，至少一个体现所选情绪标签。

**2. 撰写**
7. 创建章节文件，用 `references/chapter-template.md`。
8. 撰写正文 —— **字数必须落在平台配置区间内**（见 `references/platform-profiles.md`）。对话规范见 `references/dialogue-writing.md`；内容不足见 `references/content-expansion.md`。
9. 设置结尾钩子，见 `references/hook-techniques.md`。
10. 初稿字数粗检，偏离较大先调整再润色。

**3. 撰写后优化**
11. 连贯性检查，见 `references/consistency.md`。
12. 深度润色（去除 AI 味，增加平台味）：去过度修饰的形容词；抽象陈述改具体动作/对话；避免四字格律堆砌；增加口语化表达（番茄/飞卢）或叙事质感（豆瓣/晋江）；情绪高潮处加可划线/段评的金句；长短句交替优化节奏。
13. 质量自查，见 `references/quality-checklist.md`，分数 > 60 再交付。
14. 字数检查（见下）。

**4. 最后收尾**
15. 生成章节摘要（100-200 字），写入 `00-大纲.md`。
16. 更新状态：TODO list 标记本章"完成"。
17. 记录钩子使用情况：在 `02-情绪曲线.md` 中标注实际使用的钩子类型。

## 三大黄金法则

1. **展示而非讲述** —— 用动作和对话表现，不要直接陈述。
2. **冲突驱动剧情 + 情绪过山车** —— 每章必须有冲突；节奏按平台：番茄每 3 章"压-小扬-压-爆"，起点每 5-10 章小高潮，飞卢每章必有爽点。
3. **悬念承上启下** —— 每章结尾必须留钩子，且钩子类型要轮换。

## 字数检查

```bash
# 按平台检查单个章节
python scripts/check_chapter_wordcount.py novels/小说名/第01章.md --platform tomato
python scripts/check_chapter_wordcount.py novels/小说名/第01章.md --platform qidian
python scripts/check_chapter_wordcount.py novels/小说名/第01章.md --platform jjwxc

# 检查目录下所有章节
python scripts/check_chapter_wordcount.py --all novels/小说名/ --platform tomato

# 自定义字数区间（覆盖平台预设）
python scripts/check_chapter_wordcount.py novels/小说名/第01章.md 3000 4000
```

兼容旧命令（等同 `--platform tomato`）：

```bash
python scripts/check_chapter_wordcount_tomato.py novels/小说名/第01章.md
```

低于下限需扩充，高于上限需精简。具体区间见 `references/platform-profiles.md`。

## 参考与模板索引

- 平台配置：`references/platform-profiles.md`
- 章法：`references/chapter-guide.md`、`references/chapter-template.md`、`references/plot-structures.md`
- 人物：`references/character-building.md`
- 开篇：`references/golden-opening.md`、`references/tomato-golden-opening.md`
- 情绪节奏：`references/emotion-curve.md`、`references/tomato-emotion-curve.md`
- 钩子：`references/hook-techniques.md`
- 对话：`references/dialogue-writing.md`
- 扩写：`references/content-expansion.md`
- 连贯性/质检：`references/consistency.md`、`references/quality-checklist.md`
- 模板：`templates/outline-template.md`、`templates/outline-template-tomato.md`、`templates/character-template.md`、`templates/character-template-tomato.md`

