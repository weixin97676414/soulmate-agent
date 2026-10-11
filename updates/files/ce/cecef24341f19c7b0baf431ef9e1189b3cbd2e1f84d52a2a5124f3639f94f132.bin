---
name: movie-production-workflow
description: 用 AI 视频生成制作影视片段的项目管理与制作流程。从概念到成片的工作流：剧本→拆解→生成→组装→精修，管理风格圣经、角色参考图、镜头清单、提示词与迭代记录，并按工具路由（运动/时长/风格）与商业片、实验性技术的不同要求组织生产。触发场景：用 AI 做电影/短片、AI 影视项目、风格圣经、角色一致性表、镜头清单、分镜组装、多机位/多剧集生成管理、商业片（版本/格式/本地化）、实验片（音频同步/风格变形）、工具选型与制作流程管理。
author: Soulmate Agent团队成员：岸
---

# AI 影视项目制作流程管理 (movie-production-workflow)

用 AI 视频生成制作影片：管好剧本、提示词、一致性与制作流程，从概念到成片。

## 核心工作流

每部片都走：**剧本 → 拆解 → 生成 → 组装 → 精修**。

生成任何视频之前，先建立三样东西：

1. **风格圣经（Style bible）** — 视觉语言、色板、光线、颗粒。
2. **角色设定表（Character sheets）** — 多角度参考图。
3. **镜头清单（Shot list）** — 逐场含构图、时长、转场。

## 项目结构

```
<project>/
├── script.md           # 源剧本或 treatment
├── style-bible.md      # 视觉规则、参考、色板
├── characters/         # 每个角色的参考图
├── shots/              # 按场景组织的生成片段
├── timeline.md         # 剪辑装配顺序
└── status.md           # 已完成 / 待处理
```

## 生成检查清单

每次生成镜头前：
- [ ] 已附角色参考图
- [ ] 风格关键词已锁定（来自 style-bible）
- [ ] 已回顾上一个镜头，确认连续性
- [ ] 已按镜头类型选定工具（见 `references/tools.md`）

生成后：
- [ ] 对照参考图检查角色一致性
- [ ] 检查光线/色彩是否匹配场景
- [ ] 在 shots 目录记录提示词 + 结果
- [ ] 标记需要重生成的连续性问题

## 快速索引

| 需要 | 加载 |
|------|------|
| 把剧本拆成镜头 | `references/preproduction.md` |
| 按工具撰写有效提示词 | `references/generation.md` |
| 剪辑、色彩匹配、声音 | `references/postproduction.md` |
| 哪个镜头用哪个 API/工具 | `references/tools.md` |
| 商业片：版本、格式、本地化 | `references/commercial.md` |
| 实验片：音频同步、风格变形 | `references/experimental.md` |

## 关键规则

1. **一致性优先于速度** — 宁可重生成，也不破坏角色连续性。
2. **全记录** — 每条提示词、每次迭代、何者有效/失败都要记录。
3. **工具路由很重要** — 例如 Seedance 适合运动、Kling 适合时长、Runway 适合风格（以各工具当前实际能力为准）。
4. **先粗后精** — 先做动态分镜（animatic），只对已批准的镜头做精修。
5. **项目规模意识** — 两小时的片 = 数百个镜头，要规划迭代次数。


## 参考文件

- `references/preproduction.md` — 剧本拆解为镜头。
- `references/generation.md` — 按工具撰写提示词。
- `references/postproduction.md` — 剪辑、色彩匹配、声音。
- `references/tools.md` — 工具/API 选型。
- `references/commercial.md` — 商业片：版本、格式、本地化。
- `references/experimental.md` — 实验片：音频同步、风格变形。
