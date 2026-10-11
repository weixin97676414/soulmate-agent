# 提示词配方（Prompt Recipes）

把「用户主题 + 选定风格家族」转成高质量、可复用的图像生成提示词。本 skill 的图像生成**全部使用平台内置能力**。

## 1. 通用结构（必含 6 段）

```
[主体/场景] + [风格家族关键词] + [配色与情绪] + [构图与镜头] + [光线] + [硬性约束:尺寸/无文字]
```

- **主体/场景**：来自用户主题与赛道（如「一碗冒着热气的番茄牛肉面」）。
- **风格家族关键词**：取自 `styles.md` 对应家族的英文关键词。
- **配色与情绪**：具体色名 + mood（warm/calm/energetic…）。
- **构图与镜头**：overhead / close-up / centered / rule-of-thirds / wide。
- **光线**：soft window light / dramatic backlight / neon glow / golden hour。
- **硬性约束**：`NO text, NO letters, NO numbers, NO watermark` + 目标比例。

## 2. 比例与尺寸（生成时务必指定）

| 用途 | 宽×高 | 比例标注 |
|------|-------|----------|
| 主封面 | 900×383 | `2.35:1` |
| 方图缩略 | 1080×1080 | `1:1` |
| 朋友圈 | 1080×1350 | `4:5` |

> 提示词里写比例只是辅助，最终以生成工具的 `width/height` 参数为准。

## 3. 组合模板（直接套用）

```
{subject}, {style_family_keywords}, {palette} color tone, {mood},
{composition}, {lighting}, high quality, ultra detailed,
NO text, NO letters, NO numbers, NO watermark, {ratio}
```

**实例（美食·实拍质感·主封面）**：
```
A bowl of steaming tomato beef noodles, photorealistic macro photography,
shallow depth of field, bokeh background, warm natural window light,
ultra detailed food texture, premium look, NO text, NO letters,
NO numbers, NO watermark, 2.35:1
```

**实例（职场·极简大字报·主封面）**：
```
A single glowing arrow curving upward, minimalist bold poster style,
solid deep-green background with generous negative space,
clean flat lighting, high-end editorial, NO text, NO letters,
NO numbers, NO watermark, 2.35:1
```

## 4. 构图关键词库

| 中文意图 | 英文关键词 |
|----------|------------|
| 俯拍 | overhead view / top-down |
| 特写 | close-up / macro |
| 居中 | centered composition |
| 三分法 | rule of thirds |
| 宽幅电影 | cinematic widescreen / anamorphic |
| 浅景深 | shallow depth of field / bokeh |
| 微距质感 | ultra detailed texture |
| 对称 | symmetrical |
| 对角线 | diagonal composition |
| 留白 | negative space |

## 5. 光线关键词库

| 中文意图 | 英文关键词 |
|----------|------------|
| 自然窗光 | soft natural window light |
| 黄金时刻 | golden hour |
| 戏剧逆光 | dramatic backlight |
| 霓虹光 | neon glow |
| 影棚光 | clean studio light |
| 暖光治愈 | warm cozy sunlight |
| 冷调科技 | cool tech lighting |
| 漏光胶片 | light leak |

## 6. 质量增强词（按需追加）

`8k, ultra detailed, masterpiece, award-winning composition, sharp focus, trending on artstation`（适度，避免堆砌导致失控）。

## 7. 避坑清单（重要）

- 🚫 **绝不**写「带中文标题」「写上『XXX』」——AI 写中文字必翻车。标题走 `studio.py compose`。
- 🚫 避免「real person photo of celebrity XXX」等可能涉及真人的具名请求；用「a person / a woman」等泛化描述。
- 🚫 不要一次塞 5+ 冲突风格（既赛博又水墨），画面会脏。
- 🚫 比例与尺寸参数要一致，否则裁切翻车。
- ✅ 一次出 2–4 变体：用「slightly different angle / warmer tone / closer crop」做微小差异，便于 A/B。
- ✅ 参考图分析后用其配色/构图约束生成，保持品牌一致。

## 8. 变体生成策略（A/B 测试）

对同一个主题，建议一次产出 3 个维度差异的变体：

1. **构图变体**：centered vs rule-of-thirds。
2. **色调变体**：warm vs cool。
3. **主体距离**：close-up vs wide。

用户从 3 张里挑，再精修，效率远高于「生成一张→不满意→重来」。
