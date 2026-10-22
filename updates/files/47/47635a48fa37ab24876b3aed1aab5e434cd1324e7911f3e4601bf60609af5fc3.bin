---
name: video-prompt-engineer
description: AI 图像/视频提示词工程。把模糊想法转成可直接投喂生成工具的提示词：支持文生图(T2I)、图生图(I2I)、文生视频(T2V)、图生视频(I2V)、首尾帧视频；参数化构建人物设定、场景环境、发型妆容、姿势摆拍、镜头运镜、构图视角、色彩光影；覆盖中式风格（古风/汉服/各朝代服饰/武甲/中式建筑），并针对 Seedance 2.0（即梦）给出平台限制、素材映射、时间轴分段、IP 规避与自检清单。触发场景：AI 绘画提示词、AI 视频提示词、即梦/Seedance 提示词、人物设定、场景描述、发型设计、姿势参考、运镜构图、中式风格、古风、汉服、图生视频、首尾帧、角色替换、视频延长、节拍同步、产品展示视频、电商广告视频、一镜到底、对话短剧。
author: Soulmate Agent团队成员：岸
---

# AI 图像/视频提示词工程 (video-prompt-engineer)

两个能力面：**通用参数化提示词构建**（图像 + 视频，含中式风格库）与 **Seedance 2.0 平台化提示词工程**（硬限制、素材映射、IP 规避）。

## 一、先确定生成模式

| 模式 | 何时用 | 需要的素材 |
|------|--------|-----------|
| 文生图 T2I | 无参考图 | 无 |
| 图生图 I2I | 有参考图，换场景/角度/表情 | 参考图 |
| 文生视频 T2V | 无素材，要动态 | 无 |
| 图生视频 I2V | 有参考图/首帧 | @image |
| 首尾帧视频 | 有首帧（或首尾帧）+ 文字 | @image |
| All-Reference | 图+视频+音频多种素材 | @image / @video / @audio |

## 二、参数化提示词构建（通用）

按重要性收集参数：主体描述（性别/年龄/外貌/服装/道具/动作）、生成模式、场景环境（见 `references/locations.md`）、发型妆容（`references/hairstyles.md`）、姿势动作（`references/poses.md`、`references/character-design.md`）、镜头语言（`references/camera.md`）、风格调性、构图视角、色彩光影（后三者见 `references/framework.md`；中式风格见 `references/chinese-style.md`）。

**精准控制框架：**

```
[主体描述], [场景环境], [风格调性], [构图视角], [色彩光影], [镜头语言], [技术细节]
```

规则：模块用中文逗号 `, ` 分隔，输出为连贯中文段落，不加解释性文字或标签。

**各模式模板：**

- 文生图：`[主体描述], 位于[场景环境]中，[动作姿态]。[风格调性]，[构图视角]，[色彩光影]，[技术细节]`
- 图生图：`保持原图模特，生成一张新图片。[主体在新场景中的描述]，她穿着与输入照片中完全相同的服饰，[新角度/新动作/新表情]。[场景环境]，[光影效果]，[风格调性]，[技术细节]`
- 文生视频：`[主体描述], 位于[场景环境]中，[基础动作姿态]。[镜头运镜描述]，展现[氛围/情绪]。[风格调性]，[构图视角]，[色彩光影]，视频生成，[技术细节]`
- 图生视频：`保持原图模特，生成一段视频。以[镜头运镜方式]进行拍摄，模特[动作变化描述]。[场景环境]，[光影动态效果]，[风格调性]，视频生成，[技术细节]`
- 首尾帧：描述从首帧到尾帧的过渡方式与动态变化关键要素。

视频生成提示词**必须包含运镜描述**。

**中式风格触发**（中式/中国风/国风/古风/汉服/古装、武侠/仙侠/宫斗、汉唐宋明清等朝代、旗袍/襦裙/马面裙等元素、故宫/园林/四合院等建筑）→ 加载 `references/chinese-style.md`（含各朝代女性汉服边襟花边构成、男性战甲、中式建筑、纹样与配色）。

## 三、Seedance 2.0 / 即梦 平台化提示词

### 平台硬限制

| 项目 | 限制 |
|------|------|
| 提示词 | ≤ 2000 字符 |
| 混合输入总数 | 图片+视频+音频 ≤ 12 个 |
| 图片 | jpeg/png/webp/bmp/tiff/gif，≤ 9 张，每张 < 30MB |
| 视频 | mp4/mov，≤ 3 个，总时长 2–15s，总大小 < 50MB |
| 音频 | mp3/wav，≤ 3 个，总时长 ≤ 15s，总大小 < 15MB |
| 单段生成时长 | 4–15 秒 |
| 声音 | 支持原生音视频同步（环境音/对话/背景音乐）；可用 @audio 控制音乐风格与节奏，也可文字描述 |
| 人脸 | 真实人脸参考图可能被审核拦截，建议插画/3D 风格 |

### 输出格式（每次必须包含）

```text
Mode: [Text-only / First/Last Frame / All-Reference]

Assets Mapping:
- @image1: [用途，如：首帧/角色锚点]
- @video1: [用途，如：镜头语言+运动节奏]
- @audio1: [用途，如：音乐节奏参考]
（Text-only 模式写 "- none"）

Final Prompt:
[画幅], [时长], [风格].
0-Xs: [动作 + 镜头].
X-Ys: [动作 + 转场].
Y-Zs: [高潮/收尾 + 结束帧].
[连续性指令：preserve identity, outfit, lighting...]

Negative Constraints:
no watermark, no logo, no subtitles, no on-screen text.
[如涉及 IP 规避，在此列出所有可能被推断的品牌/角色名]

Generation Settings:
Duration: Xs
Aspect Ratio: X:X
```

### 核心规则

1. 先声明 Mode；2. 必须有 Assets Mapping（每个素材的控制职责明确）；3. 时间码分段，每段一个主要动作；4. 具体而视觉化（✅ "a woman in a red trench coat walks through rain-soaked neon streets" ❌ "a woman walking"）；5. 对话/音效与画面分层；6. 风格匹配（水墨配古风、霓虹配赛博朋克）；7. 简洁可控，避免纯诗意模糊；8. 需要时加 Negative Constraints（去水印/文字/IP 引用）；9. **叙事场景必须有声音层**：只要含剧情/故事/解说/旁白/角色互动，就加 Dialogue 或 Narration 层和 Sound 层。台词 `Dialogue (Name, emotion): "line"`，旁白 `Narration (emotion): "line"`，音效 `Sound: [描述]`。

### 场景处理指南

- **视频延长**：写 `Extend @video1 by Xs`；Duration 填**新增段**时长；写连续性指令。
- **角色替换**：`@video1`=原始动作与镜头，`@image1`=替换角色外观；保留编舞、节奏、转场。
- **节拍同步**：@video/@audio 作节奏参考，按时间段锁定节拍切换点。
- **纯文本生成**：prompt 必含风格、色彩、角色完整外观、环境、光线、镜头运动、时间轴。
- **多段拼接（>15s）**：声明总时长与分段数；首段 ≤15s 且结尾留干净交接帧；第 2 段起 `Extend @video1 by Xs`；每段末尾写交接帧描述。
- **对话短剧**：画面/对话/音效分三层；每 3–5 秒最多一句台词；情绪标签 cold/desperate/cheerful/whispering/firm/sarcastic。
- **产品展示/电商**：@image1=产品照片（身份锚点）；常用 360° 旋转、3D 爆炸视图、重组动画、英雄光；背景干净；指定材质 glass reflections / metallic sheen / matte finish / translucent glow。
- **一镜到底**：@image1=首帧，后续 @image 作场景路标；写 `no cuts, single continuous shot, one-take`；15 秒配 3–5 个路标最佳。

### IP / 版权规避

平台审核会拒绝可识别 IP，即使不写名字也可能被拦。原则：绝不用 IP 名/角色名/品牌词（含 "style of"）；发明全新描述性昵称（"Alloy Sentinel"）；用通用描述替换标志性特征（"arc reactor"→"hex-light energy core"）；Negative 列出所有可推断 IP；加 `family-friendly`/`PG-13` 有助过审。被拒时三级渐进规避：L1 换原创昵称 → L2 替换标志性视觉特征 → L3 完全改变角色类型。玩具/手办：去品牌标识，用 "original vinyl-style toy figure"。

### 场景速查

| 场景 | 关键技巧 | 推荐模式 |
|------|----------|----------|
| 电商/产品广告 | 360° 旋转、爆炸视图、英雄光、纯净背景 | All-Reference |
| 对话短剧 | 对话标签+情绪、音效层、走位 | All-Reference / First Frame |
| 奇幻/仙侠 | 法术粒子、武术编排、能量光环 | Text-only / All-Reference |
| 科普/教育 | 4K CGI、透明解剖、标注缩放 | Text-only |
| MV/节拍同步 | 节拍锁定剪辑、宽屏、多图蒙太奇 | All-Reference + @audio |
| 一镜到底 | 多图路标、连续镜头、无剪辑 | All-Reference |
| IP 安全原创 | 原创名字、独特特征、明确 Negative | Text-only |
| 玩具/手办 | 去品牌、vinyl-style toy、干净动作 | All-Reference |

### 自检清单

字符数 ≤ 2000；文件数量与大小在限制内（混合 ≤ 12）；单段 4–15 秒；每个素材有明确 @asset 角色；有清晰时间轴分段；需要时有 Negative Constraints；无 IP 名称/角色名/品牌词；Negative 列出所有可推断 IP；角色用原创名字；对话/音效与画面分层；多段视频有交接帧描述；镜头术语参考 `references/camera-and-styles.md`；有剧情/解说场景已加 Dialogue/Narration + Sound 层。

## 输出规则

1. 直接输出提示词，不加解释、标题或分类标签。
2. 最终提示词为中文（通用面）；Seedance 平台面按上方格式输出。
3. 保证是连贯段落/结构，包含所有用户指定的重要参数。
4. 用户参数不完整时主动询问缺失关键信息；优先使用参考文档中的专业术语。


## 参考文件

- `references/framework.md` — 提示词框架、风格词、美学词、构图、色彩参考。
- `references/camera.md` — 运镜方式与视角。
- `references/poses.md`、`references/character-design.md` — 姿势与角色设计。
- `references/hairstyles.md` — 发型设计。
- `references/locations.md` — 地理位置/场景参考。
- `references/chinese-style.md` — 中式风格库（汉服/武甲/建筑/纹样）。
- `references/recipes.md` — 现成 Seedance 提示词模板（含中文注释，覆盖常见场景）。
- `references/camera-and-styles.md` — 镜头语言与视觉风格词汇表（中英对照）。
