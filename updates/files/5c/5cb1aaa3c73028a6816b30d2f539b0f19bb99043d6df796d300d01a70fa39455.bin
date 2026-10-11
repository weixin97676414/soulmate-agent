# 画面提示词库 (Prompt Library)

工具无关的提示词组装方法。目标:每个镜头都能快速组装出稳定、可复用的画面提示词。

## 提示词组装公式(英文提示词推荐顺序)

```
[角色锚点句] + [主体动作/表情] + [场景] + [机位/景别] + [风格锚点] + [光影/氛围] + [画质词] + [负面提示词]
```

例(真人):
> young asian man, black short hair, white shirt black glasses, mole on left eyebrow, surprised expression, office room, medium shot, cinematic, soft window light, photorealistic, 8k --no blurry, distorted face, extra fingers

例(漫剧):
> chinese anime style, young asian man, black short hair, white shirt black glasses, shocked expression, neon city street, low angle shot, dynamic lighting, clean lineart, vibrant colors --no blurry, off-model, watermark

## 固定锚点(全流程不变)

- **角色锚点句**:见 `character-card.md`,每个角色一段,原样复用
- **风格锚点句**:每项目固定一段,如"写实电影感 / 国漫厚涂 / 日漫赛璐璐 / 3D 皮克斯风"
- 禁止中途换同义词(会导致漂移)

## 常用镜头/机位词

- 景别:extreme wide shot / wide / full shot / medium shot / close-up / extreme close-up
- 运镜提示(camera):slow push-in / pull back / pan left / tracking shot / handheld / crane up
- 角度:eye level / low angle / high angle / dutch angle / over-shoulder shot

## 风格词库

| 类型 | 风格词(选一) |
|---|---|
| 真人写实 | photorealistic, cinematic, film grain, 35mm, shallow depth of field |
| 电影感 | cinematic lighting, teal and orange, anamorphic, dramatic shadows |
| 国漫 | chinese anime style, ink painting texture, clean lineart, vibrant |
| 日漫 | japanese anime style, cel shading, pastel palette, detailed eyes |
| 3D 渲染 | 3D render, pixar style, subsurface scattering, soft global illumination |
| 悬疑/暗黑 | moody, low-key lighting, high contrast, desaturated, fog |
| 甜宠/明亮 | bright, soft light, warm tones, bokeh, pastel |

## 光影氛围词

morning light / golden hour / neon glow / moonlight / candlelight / rainy window / harsh noon sun / volumetric light

## 负面提示词(通用)

`blurry, low quality, distorted face, deformed hands, extra fingers, watermark, text, logo, off-model, inconsistent character, bad anatomy`

## 逐镜头生成流程

1. 取角色锚点句(该镜头人物)
2. 加动作/表情(从分镜"画面描述"提取)
3. 加场景、机位、风格锚点、光影
4. 生成 2~3 备选,挑最佳
5. 有人物镜头一律用参考图模式,禁止纯文生图出人脸

## 完整示例(照抄可改)

### 示例 A:真人短剧(悬疑,近景,女主惊讶)

```
young asian woman, 25, oval face, big eyes, black long straight hair, white blouse, silver earrings, shocked expression, eyes wide, office at night, medium close-up, slow push-in, cinematic, moody low-key lighting, teal and orange, photorealistic, film grain, 35mm --no blurry, distorted face, extra fingers, watermark, text
```

### 示例 B:漫剧(国漫,反派登场,低角度)

```
chinese anime style, middle-aged man, square face, scar on right cheek, black suit, cold grin, standing on rooftop, night city neon background, low angle shot, dramatic rim light, clean lineart, vibrant colors, dynamic composition --no blurry, off-model, watermark, text, extra limbs
```

### 示例 C:空镜(无人物,转场用)

```
empty corridor, hospital, fluorescent light, cold color tone, long shot, wide angle, cinematic, slightly desaturated --no people, blurry, text
```

复用规则:示例 A/B 的人名/外貌/服装换成你项目角色卡锚点句,风格与负面词保留;示例 C 换场景词即可。
