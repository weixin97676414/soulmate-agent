# 小红书笔记配图 Prompt 模板

本文件为本技能（小红书图文笔记生成）的配图生成 Prompt 仓库。第 7 步配图生成时，按本文件模板调用 ImageGen（或等效图像生成工具），默认生成 **6 张 3:4 竖版配图**（1024×1536 接近 3:4，发布前可裁剪为 1080×1440 或 1242×1660）。

---

## 🎯 配图设计原则（强制）

所有配图必须遵守以下反幻觉规则：

| 禁止项 | 原因 | 正确做法 |
|---|---|---|
| 出现人脸 / 人像 | 避免 AI 假脸、避免被质疑「不是你本人」 | 用物件平铺、场景特写、产品细节 |
| 出现文字 / Logo / 品牌名 | 防止 AI 乱写品牌、规避极限词风险 | prompt 里加 `no text, no logos, no brand names` |
| 出现具体产品包装 | 看起来像广告 / 软广，且会编造品牌 | 只展示品类特征，不展示包装 |
| 过度美颜 / 假滤镜 | 用户反感一眼 AI 的糖水片 | 用自然光、胶片颗粒、真实材质感 |

**默认出图公式**：

```
[构图] + [主体物件/场景] + [光线与色调] + [背景] + [no text, no logos, no people] + [风格词]
```

---

## 🖼 默认 6 张配图模板（以「9 月错峰海边好物」为例）

调用 ImageGen 时建议参数：

```json
{
  "size": "1024x1536",
  "quality": "high"
}
```

### 图 1：封面 / 首图

**Prompt：**

```text
Sunset seaside beach scene in late summer, warm golden hour light, a wide-brim straw hat and a small straw tote bag resting on weathered wooden boardwalk in foreground, turquoise sea and gentle soft waves blurred in background, no people, no text, no logos, warm amber tones, vacation lifestyle aesthetic photography, serene and empty beach capturing off-peak September vibe, instagram style film grain
```

**配图说明**：首图决定点击率，主体是大面积暖橙 + 海蓝；草帽和编织包都是「海边氛围」关键词。不要放文字，文字由后期封面设计叠加。

---

### 图 2：穿搭平铺

**Prompt：**

```text
Flat lay photograph of a neatly folded single white chiffon blouse with a standard pointed collar and long sleeves, placed on cream linen fabric beside folded beige linen wide-leg pants, tan leather flat sandals, black tortoiseshell uv400 sunglasses, and a woven straw crossbody bag, soft natural daylight from side, muted warm tones, no text no logos, minimalist beach vacation wardrobe, top-down view, clean composition
```

**配图说明**：展示正文里提到的「雪纺罩衫 + 亚麻长裤 + 草编包 + 墨镜」组合，平铺形式最稳，不易出 AI 人像 bug。

---

### 图 3：墨镜特写

**Prompt：**

```text
Close-up photograph of stylish tortoiseshell-frame sunglasses with dark uv400 lenses resting on soft pale beach sand, sun glare reflecting off the lens surface, soft bokeh of turquoise sea in background, late afternoon warm side light, no text, no people, no logos, vacation accessory photography, warm tones, shallow depth of field
```

**配图说明**：重点突出「UV400 + 海面反光」这两个卖点，背景虚化更高级。

---

### 图 4：草编包特写

**Prompt：**

```text
Detail photograph of a natural rattan straw crossbody bag with intricate woven texture, soft sunlight filtering through its open weave creating dappled shadows, scattered dried botanicals and small seashells on a sunlit wooden surface, warm earth tones, no text, no logos, artisanal handcraft aesthetic, soft focus vacation style background
```

**配图说明**：强调编织纹理和光影，ins 风明显，适合作为「拍照出片神器」的证据。

---

### 图 5：挂脖防水手机袋

**Prompt：**

```text
Underwater photograph of a simple clear transparent rectangular waterproof phone pouch with a black zipper closure and an adjustable fabric lanyard strap, floating in crystal clear turquoise sea water, sunlight rays streaming through water surface creating caustic light patterns, small colorful tropical fish in soft focus background, action camera perspective, vibrant aqua and warm golden tones, summer water sports photography, no text no logos, no people, the object is clearly a phone bag not a camera
```

**配图说明**：第一次跑容易生成成「水下相机 / 潜水面镜」，所以必须加 `the object is clearly a phone bag not a camera` 这句强约束。

---

### 图 6：Tote 袋 / 救场小物

**Prompt：**

```text
Travel lifestyle photograph of a large natural cotton canvas tote bag leaning against sun-warmed coastal rocks by the seaside, a folded damp swimsuit and rolled beach towel casually placed at the top opening, soft focus gentle waves in background, late afternoon warm sunlight, muted earth tones with navy and cream accents, no text no logos, no people, post-beach getaway aesthetic
```

**配图说明**：表现「装湿泳衣回家」的场景感，比单纯拍包更有代入感。

---

## 🔧 复用到其他选题的改写方法

1. 把 `[主体物件]` 换成当前笔记的核心好物
2. 把 `[光线与色调]` 换成选题的氛围色（海边=暖橙+海蓝；职场=冷灰+米白；家居=奶油+木色）
3. 把 `[背景]` 换成选题的场景（桌面 / 公园 / 办公室 / 卧室）
4. **保留三件套**：`no text, no logos, no people`

---

## ⚠️ 反幻觉提醒

- 本模板生成的图片仍属于 **AI 生成内容**，发布前必须勾选「AI 辅助创作」标签。
- 如果笔记涉及具体品牌合作，**不能用 AI 图冒充实拍图**——必须替换为真实拍摄素材，并在蒲公英后台勾选「广告」。
- 如果用户要求「真人出镜」或「本人实拍」，必须明确拒绝：AI 生成的人像不是该用户本人，属于虚假宣传。

