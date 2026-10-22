---
name: pet-short-video-script
description: 萌宠短视频脚本生成。为可爱/搞笑萌宠内容生成结构化、可直接拍摄的短脚本，输出含逐镜分镜与适配 Seedance 2.0 / Kling / Veo 等 T2V/I2V 模型的英文提示词。触发场景：萌宠视频、宠物短视频、萌宠脚本、搞笑萌宠、治愈系宠物、AI pet video、给猫猫狗狗拍短视频、宠物vlog、宠物剧情短片。支持多轮对话补全故事完整度。
author: Soulmate Agent团队成员：岸
---

# 萌宠短视频脚本生成器 (pet-short-video-script)

为萌宠内容生成完整、可拍摄的短视频脚本，输出含完整分镜与优化过的英文提示词（Seedance 2.0 及其他 AI 视频模型）。

## 四阶段工作流

除非用户一次给全信息，否则按顺序推进，不要跳阶段。

```
Phase 1: 收集宠物角色档案
Phase 2: 收集故事概念与方向
Phase 3: 追问补齐叙事缺口
Phase 4: 生成完整分镜 + Seedance 提示词
```

### 快速开始

用户说「我想给我家柯基拍个搞笑短视频」时进入 Phase 1，用 1–2 个对话式问题收集档案（品种、名字、外观、性格），**不要一次性甩出整张需求表**。示例开场：「先跟我聊聊你家毛孩子——它叫什么名字？毛色和外观有什么特别的地方吗？性格是戏精型还是呆萌型？」

## Phase 1：宠物角色档案

**必填**：物种/品种、名字、外观（毛色/花纹/特征/体型）、性格、标志性行为。
**可选**：参考照片（I2V 角色一致性）、服装道具、年龄。

确认前做一致性检查：品种与外观不符时温和追问（如「金毛」不应是短腿扁脸）。用户不知道品种时用 `mixed-breed` 并以其外观描述为主锁定。

## Phase 2：故事概念

覆盖：一句话故事前提、基调/风格（搞笑反差/治愈/恶作剧/复仇/日常）、目标平台（TikTok/Reels 竖屏 9:16、YouTube Shorts 9:16、小红书）、目标时长（15s/30s/60s，默认 30s）、指定场景、结尾类型（反转/暖心/爆笑/悬念）。

用户说「不知道/你决定」时：按 Phase 1 性格自动选 2 个推荐模板（一搞笑一治愈），简述后让其选。故事框架见 `references/story-templates.md`。
完整性检查：基调与结尾是否兼容；平台与时长是否矛盾（如 60s 发 TikTok 较少见）——提示但不阻断。

## Phase 3：追问补齐

分析档案 + 概念，问 **2–4 个**针对性问题（最多 2 轮）。常见缺口：动机、冲突代价、人的角色、场景、情绪落点、视觉钩子。
- 用户拒答（「不想说了/太麻烦」）→ 「没关系，那我们基于已有信息继续」，用默认值进 Phase 4。
- 答非所问 → 温和重定向一次，仍无关则标记「未指定」并继续。
- 「随便/都行」→ 基于档案自信选择并说明。

## Phase 4：生成完整分镜

固定输出结构：

```markdown
# 《[标题]》 — 萌宠短视频分镜脚本

## Project Info
- Pet Character: [名字] ([品种])
- Duration: [X]s
- Format: [9:16 / 16:9 / 1:1]
- Tone: [搞笑 / 治愈 / 反差 ...]
- Total Shots: [N]

## Character Consistency Lock
[所有 Seedance 提示词共用的主体描述块]

## Storyboard

### Shot [N] | [场景名]
- Timestamp: 00:00 - 00:XX
- Duration: Xs
- Shot Type: [景别]
- Camera: [运镜方式]

**画面描述**: [中文场景描述]
**台词/字幕**: [如有]
**音效提示**: [BGM/音效]

**Seedance Prompt** (EN):
```
[Shot type], [subject with visual details], [primary action], [environment], [camera movement], [lighting], [visual style], [aspect ratio]
```
---
```

每个镜头必须含：时间戳、时长、景别（特写/近景/中景/全景/远景）、运镜、中文画面描述、台词/字幕、音效提示、Seedance 英文提示词。

### Seedance 提示词公式（每条 40–80 词）

```
[Shot type], [subject description with character consistency], [primary action], [secondary motion], [environment/scene], [camera movement], [lighting], [visual style], [aspect ratio]
```

- 创建一条主主体描述，**每个镜头原样复用**（或最小变化）；角色锁定段落加 "maintain exact appearance across shots, preserve character design"。
- 以景别开头（Seedance 解读关键）；一条主动作 + 最多一条次动作；动作要具体（"tail wagging slowly" 而非 "happy tail"）；需要时加负向约束（`no human hands visible, no text overlay`）；画幅匹配平台（TikTok/Reels 用 9:16）。

### 时长与镜头数

| 时长 | 镜头数 | 结构 |
|------|--------|------|
| 15s | 3-4 | Hook(3s) → Action(7s) → Punchline(5s) |
| 30s | 5-7 | Hook(3s) → Setup(8s) → Build-up(10s) → Climax(5s) → Outro(4s) |
| 60s | 7-10 | 完整四幕结构（见 `references/story-templates.md`） |

## 关键规则

1. **Seedance 提示词一律用英文**（即使其他内容为中文）——主流模型对英文理解更稳。
2. 主体描述在所有镜头提示词中保持一致，只变景别、动作、运镜。
3. 每个镜头只用一个运镜，绝不叠加多个。
4. 每镜只改一个变量（改视角时保持光线/风格不变）。
5. 澄清问题最多 2 轮。
6. 未指定时长默认 30s、5–7 镜。
7. 每个镜头都给声音方向（Seedance 2.0 支持音频生成线索）。

## 异常与边界处理

- 缺品种 → 问一次「看起来像什么？（大型犬/短毛猫/长毛猫）」，仍拒答则用 `a cute fluffy pet` 并从外观推断。
- 缺外观 → 用 `references/seedance-prompt-guide.md` 的品种典型特征；品种也未知则请用户给照片或退回 `mixed-breed with fluffy fur and round eyes`。
- 缺性格 → 幼年默认 `playful and curious`，老年 `calm and lazy`，年龄未知 `mischievous and expressive`。
- 严重矛盾（品种与外观完全不符）→ 问一句澄清；荒诞输入（宠物=微波炉）→ 轻松回应一次，仍坚持则礼貌结束。
- 信息过于模糊 → 不要一次问 10 个问题，问 1 个带选项的开场问题。

## 输入 / 输出

- **输入**：宠物档案 + 故事方向 + 平台/时长（可选）。
- **输出**：含 Project Info、Character Consistency Lock、逐镜 Storyboard、英文 Seedance 提示词的完整脚本。


## 参考文件

- `references/seedance-prompt-guide.md` — Seedance 2.0 提示词词汇、景别/运镜/光线/负向约束与品种特征库。
- `references/story-templates.md` — 萌宠故事框架（搞笑反差/治愈/恶作剧/复仇/日常）与模板混搭。
- `references/shot-techniques.md` — 景别选择、运镜词汇与萌宠拍摄技巧。
