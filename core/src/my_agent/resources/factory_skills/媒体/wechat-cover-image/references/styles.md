# 风格库（Style Library）

本库为「公众号爆款封面工坊」内置的视觉风格与赛道知识库。**全部内建、零外部依赖**。分两轴使用：

- **轴 A · 视觉风格家族（32 种）**：决定画面的「技法与调性」。
- **轴 B · 内容赛道（17 类）**：决定「主体与叙事」。

Agent 应同时选两轴：先按赛道定主体，再按风格家族定视觉，最后用 `prompt_recipes.md` 拼提示词。

---

## 轴 B：内容赛道 × 推荐风格速查表

| 赛道 | 首选风格家族（按优先级） | 主体建议 |
|------|--------------------------|----------|
| 美妆护肤 | 极简大字报 / 实拍质感 / 治愈小清新 / 黑金奢华 | 产品特写、肤质光泽、手部试色 |
| 穿搭时尚 | 杂志拼贴 / 实拍质感 / 极简大字报 / 波普艺术 / 孟菲斯 | 全身穿搭、街拍、单品质感 |
| 美食 | 实拍质感 / 微缩场景 / 治愈小清新 / 黏土 3D | 俯拍满桌、热气蒸腾、食材特写 |
| 旅行 | 电影感运镜 / 治愈小清新 / 国潮水墨 / 剪纸镂空 | 地标、山海、公路、城市天际 |
| 职场成长 | 极简大字报 / 信息图表 / 扁平插画 / 几何包豪斯 | 办公场景、上升箭头、人物剪影 |
| 情感心理 | 治愈小清新 / 东方留白 / 手绘涂鸦 / 双色调 | 双人/单人情绪场景、暖光室内 |
| 育儿亲子 | 卡通萌系 / 治愈小清新 / 手绘涂鸦 / 黏土 3D | 宝宝、亲子互动、童趣场景 |
| 财经商业 | 信息图表 / 科技赛博 / 极简大字报 / 黑金奢华 / 几何包豪斯 | K线、金币、楼宇、数据可视化 |
| 科技数码 | 科技赛博 / 3D 等距 / 霓虹渐变 / 新拟态 / 像素 8-bit | 设备特写、芯片、光效、UI元素 |
| 健康养生 | 治愈小清新 / 东方留白 / 扁平插画 / 森系手作 | 果蔬、晨练、经络、自然元素 |
| 教育知识 | 信息图表 / 扁平插画 / 极简大字报 / 几何包豪斯 | 书本、脑图、公式、知识点图标 |
| 搞笑娱乐 | 卡通萌系 / 手绘涂鸦 / 杂志拼贴 / 街头涂鸦 / 孟菲斯 / 像素 8-bit | 表情包式人物、夸张场景 |
| 家居生活 | 治愈小清新 / 微缩场景 / 实拍质感 / 森系手作 | 房间一角、收纳、绿植 |
| 读书成长 | 东方留白 / 国潮水墨 / 极简大字报 / 剪纸镂空 | 书本、咖啡、书桌、窗外 |
| 健身运动 | 高对比暗黑 / 实拍质感 / 霓虹渐变 / 街头涂鸦 | 训练瞬间、汗水、器械、剪影 |
| 探店本地生活 | 实拍质感 / 微缩场景 / 杂志拼贴 | 门店门头、招牌菜、街角烟火 |
| 宠物萌宠 | 卡通萌系 / 治愈小清新 / 黏土 3D | 猫狗特写、萌宠日常、拟人场景 |

---

## 轴 A：32 种视觉风格家族

> 每条含：适用赛道、配色、主体/构图、生图提示词模板（用 `{subject}` 主题、`{mood}` 情绪占位）、标题排版建议、点击钩子。提示词**必须强调无文字**。

### 1. 极简大字报（Minimal Bold）
- **适用**：职场、财经、读书、干货知识
- **配色**：单一主色（红/橙/墨绿）+ 大量留白（米白/浅灰）
- **主体/构图**：强主体居中或偏一侧，背景纯净，几何留白
- **提示词**：`A minimalist bold poster style cover, {subject}, solid {mood} background with generous negative space, one strong focal subject, flat clean lighting, high-end editorial, NO text, NO letters, NO numbers, 2.35:1`
- **标题排版**：超大粗体主标题贴底部或左侧，主色块衬底
- **点击钩子**：确定感、权威感、一眼读完

### 2. 实拍质感（Real-Photo Texture）
- **适用**：美妆、美食、穿搭、健身
- **配色**：自然真实色，暖光优先
- **主体/构图**：浅景深特写，主体清晰背景虚化，微距质感
- **提示词**：`Photorealistic macro photography, {subject}, shallow depth of field, bokeh background, soft natural window light, ultra detailed skin/fabric/food texture, premium product look, NO text, NO watermark, 2.35:1`
- **标题排版**：底部暗化蒙版 + 白字
- **点击钩子**：真实可信、想点击看细节

### 3. 3D 等距插画（3D Isometric）
- **适用**：科技、财经、职场、教育
- **配色**：糖果色/科技蓝紫，明亮统一
- **主体/构图**：等距视角小场景，圆润几何体，软阴影
- **提示词**：`3D isometric illustration, {subject} as a cute rounded miniature scene, soft studio light, pastel tech color palette, clean white background, blender render style, NO text, NO letters, 2.35:1`
- **标题排版**：主标题压顶部，字色取场景主色
- **点击钩子**：现代感、专业、清爽

### 4. 扁平插画（Flat Illustration）
- **适用**：教育、职场、健康、育儿
- **配色**：2–3 色高饱和扁平色块
- **主体/构图**：几何化简笔人物/物体，无渐变纯色
- **提示词**：`Flat vector illustration, {subject}, bold simple shapes, two-tone color blocks, minimal shading, modern infographic style, NO text, NO letters, 2.35:1`
- **标题排版**：粗体无衬线主标题，色块分割
- **点击钩子**：易懂、亲和、知识感

### 5. 渐变流体（Gradient Fluid）
- **适用**：科技、财经、读书、情感
- **配色**：梦幻渐变（紫粉蓝 / 青绿）
- **主体/构图**：流动曲面、光斑、抽象能量
- **提示词**：`Abstract gradient fluid art, smooth flowing curves, dreamy {mood} color gradient, soft glowing orbs, elegant and modern, cinematic lighting, NO text, NO letters, 2.35:1`
- **标题排版**：白字或深墨字，居中或底部
- **点击钩子**：高级感、氛围、好奇心

### 6. 杂志拼贴（Magazine Collage）
- **适用**：穿搭、旅行、搞笑、美食
- **配色**：多素材混排，统一滤镜
- **主体/构图**：照片+色块+线条拼贴，版面活泼
- **提示词**：`Fashion magazine collage layout, {subject} composed of cut-out photos, color blocks and thin lines, vibrant editorial mashup, risograph texture, NO readable text, 2.35:1`
- **标题排版**：杂志刊头式大标题跨顶部
- **点击钩子**：时尚、会玩、信息量

### 7. 手绘涂鸦（Hand-drawn Doodle）
- **适用**：情感、育儿、搞笑、读书
- **配色**：马克笔风，暖白纸底+1–2 重点色
- **主体/构图**：随性线条、便签、箭头、小表情
- **提示词**：`Hand-drawn doodle sketch, {subject} in playful marker lines on warm paper, sticky notes and arrows, friendly rough texture, NO text, NO letters, 2.35:1`
- **标题排版**：手写体感主标题（用排版模拟）
- **点击钩子**：亲切、像朋友、轻松

### 8. 国潮水墨（Guochao Ink）
- **适用**：旅行、读书、健康、美食
- **配色**：墨黑+朱红+宣纸米黄
- **主体/构图**：水墨晕染、祥云、山石、书法笔意
- **提示词**：`Chinese guochao ink wash painting, {subject} with ink bleed and vermilion red seal accent, rice-paper texture, elegant negative space, traditional yet trendy, NO text, NO letters, 2.35:1`
- **标题排版**：朱红印章式栏目标签 + 墨色主标题
- **点击钩子**：文化认同、高级、国风

### 9. 科技赛博（Tech Cyber）
- **适用**：科技、财经、数码
- **配色**：霓虹青/品红 + 深蓝黑
- **主体/构图**：网格、光带、全息 UI、粒子
- **提示词**：`Cyberpunk tech visual, {subject}, neon cyan and magenta glow, dark grid background, holographic UI elements, futuristic, cinematic, NO text, NO letters, 2.35:1`
- **标题排版**：霓虹描边主标题
- **点击钩子**：前沿、酷、未来感

### 10. 治愈小清新（Healing Fresh）
- **适用**：情感、育儿、美食、家居、健康
- **配色**：奶油白+浅绿+淡粉，低饱和
- **主体/构图**：柔和日光、植物、柔软物体，慢生活
- **提示词**：`Soft healing aesthetic, {subject}, warm sunlight through window, pastel cream and mint tones, cozy daily life mood, gentle film grain, NO text, NO letters, 2.35:1`
- **标题排版**：圆润细体主标题，浅色衬底
- **点击钩子**：放松、想收藏、情绪价值

### 11. 复古胶卷（Retro Film）
- **适用**：旅行、美食、穿搭、读书
- **配色**：暖橙褐+褪色黄，胶片颗粒
- **主体/构图**：胶片质感街景/人像，漏光
- **提示词**：`Retro film photography, {subject}, 35mm grain, warm faded tones, light leak, nostalgic mood, vintage color grade, NO text, NO letters, 2.35:1`
- **标题排版**：做旧字体主标题
- **点击钩子**：怀旧、故事感、格调

### 12. 高对比暗黑（High-contrast Dark）
- **适用**：健身、科技、财经、职场
- **配色**：纯黑底 + 单一高亮色（红/荧黄）
- **主体/构图**：强逆光剪影，硬光，戏剧张力
- **提示词**：`High-contrast dark moody scene, {subject}, dramatic backlight silhouette, single accent color, hard light, cinematic shadow, NO text, NO letters, 2.35:1`
- **标题排版**：高亮色主标题，强对比
- **点击钩子**：力量感、冲突、想点

### 13. 卡通萌系（Cartoon Cute）
- **适用**：育儿、搞笑、美食、情感
- **配色**：马卡龙色，圆润明亮
- **主体/构图**：Q 版人物/动物，大眼睛，夸张表情
- **提示词**：`Cute kawaii cartoon, {subject} as chibi character, big sparkly eyes, rounded shapes, macaron color palette, cheerful, NO text, NO letters, 2.35:1`
- **标题排版**：圆胖卡通字主标题
- **点击钩子**：可爱、愉悦、想转

### 14. 信息图表（Infographic）
- **适用**：财经、教育、职场、科技
- **配色**：品牌色 + 中性灰，图表元素
- **主体/构图**：数据卡片、箭头、图标、数字感图形（非真实文字）
- **提示词**：`Clean infographic cover, {subject} visualized with charts, arrows and icon shapes, corporate blue and neutral grey, structured layout, NOT containing readable text, 2.35:1`
- **标题排版**：信息卡式主标题 + 小标签
- **点击钩子**：干货、专业、可收藏

### 15. 电影感运镜（Cinematic）
- **适用**：旅行、情感、美食、健身
- **配色**：电影级调色，冷暖对比
- **主体/构图**：宽幅景别、前景虚化、故事瞬间
- **提示词**：`Cinematic widescreen shot, {subject}, anamorphic lens flare, shallow foreground, teal-and-orange grade, storytelling moment, film still, NO text, NO letters, 2.35:1`
- **标题排版**：宽幅底部字幕式主标题
- **点击钩子**：大片感、沉浸、好奇剧情

### 16. 微缩场景（Miniature / Tilt-shift）
- **适用**：美食、家居、旅行、育儿
- **配色**：真实饱和，移轴虚化
- **主体/构图**：玩具般微观世界，俯拍
- **提示词**：`Tilt-shift miniature world, {subject} as a tiny realistic diorama, overhead view, dreamy blurred edges, vibrant and cute, NO text, NO letters, 2.35:1`
- **标题排版**：底部白字 + 微阴影
- **点击钩子**：有趣、巧思、想细看

### 17. 霓虹渐变（Neon Gradient）
- **适用**：科技、健身、财经、数码
- **配色**：荧光渐变（紫→粉→蓝）
- **主体/构图**：发光体、液态金属、能量线
- **提示词**：`Neon gradient art, {subject}, glowing liquid-metal forms, vibrant magenta-to-cyan gradient, energetic and modern, soft bloom, NO text, NO letters, 2.35:1`
- **标题排版**：发光描边主标题
- **点击钩子**：活力、年轻、潮

### 18. 东方留白（Oriental Negative Space）
- **适用**：读书、情感、健康、旅行
- **配色**：素白 + 一抹黛青/赭石
- **主体/构图**：极简一物（一枝、一器、一人），大量留白
- **提示词**：`Minimal oriental composition, {subject} with vast empty space, one ink-toned object, muted celadon and ochre accent, calm and poetic, NO text, NO letters, 2.35:1`
- **标题排版**：细宋体主标题 + 留白
- **点击钩子**：安静、高级、有余韵

### 19. 故障艺术（Glitch Art）
- **适用**：科技、数码、财经、游戏
- **配色**：RGB 分离红/青、黑底、像素抖动
- **主体/构图**：主体带撕裂位移、扫描线、雪花噪点
- **提示词**：`Glitch art cover, {subject} with RGB chromatic aberration, scan lines, pixelated distortion, dark background, digital noise, NO text, NO letters, 2.35:1`
- **标题排版**：错位切片感主标题，白字
- **点击钩子**：冲突、科技、猎奇

### 20. 蒸汽波（Vaporwave）
- **适用**：娱乐、复古、潮流、搞笑
- **配色**：粉紫渐变 + 荧光网格 + 日落色
- **主体/构图**：古希腊雕像、老式电脑窗、棕榈树、荧光网格地板
- **提示词**：`Vaporwave retro-futurism, {subject} with pink-purple gradient sky, neon grid floor, palm trees, old computer windows, dreamy 80s mood, NO text, NO letters, 2.35:1`
- **标题排版**：复古霓虹描边字
- **点击钩子**：怀旧潮流、视觉冲击、好玩

### 21. 低多边形（Low Poly）
- **适用**：科技、教育、旅行、户外
- **配色**：3–4 色几何三角面
- **主体/构图**：主体由多边形三角面构成，几何块面感
- **提示词**：`Low poly geometric art, {subject} composed of colorful triangle facets, clean vector-like shading, modern abstract, NO text, NO letters, 2.35:1`
- **标题排版**：居中粗体主标题，压在三角面上
- **点击钩子**：现代、抽象、技术感

### 22. 新拟态（Neumorphism）
- **适用**：科技、财经、职场、数码
- **配色**：同色系浅灰/米白，软凹凸阴影
- **主体/构图**：柔和凸起/凹陷的UI质感元素，无边界融合
- **提示词**：`Neumorphism soft UI style, {subject} as extruded rounded shapes, monochrome light grey background, soft inner and drop shadows, subtle emboss, minimal, NO text, NO letters, 2.35:1`
- **标题排版**：低对比浮雕感嵌入式主标题
- **点击钩子**：高级、干净、克制

### 23. 黏土 3D（Clay 3D）
- **适用**：育儿、美食、宠物、搞笑
- **配色**：高饱和糖果色，柔光
- **主体/构图**：圆润黏土质感物体/角色，软萌体积感
- **提示词**：`Claymation 3D render, {subject} as cute soft clay object, matte pastel surface, rounded chunky shapes, studio soft light, playful, NO text, NO letters, 2.35:1`
- **标题排版**：圆胖立体字主标题
- **点击钩子**：可爱、Q弹、想捏

### 24. 孟菲斯（Memphis）
- **适用**：搞笑、穿搭、娱乐、潮流
- **配色**：高饱和撞色 + 黑白点线几何
- **主体/构图**：不规则色块、波浪线、圆点、锯齿装饰
- **提示词**：`Memphis design style, {subject} surrounded by playful geometric shapes, squiggles, dots and zigzags, bold clashing colors, 80s graphic, NO text, NO letters, 2.35:1`
- **标题排版**：几何拼贴式粗体主标题
- **点击钩子**：活泼、潮、有态度

### 25. 波普艺术（Pop Art）
- **适用**：美妆、搞笑、娱乐、穿搭
- **配色**：高对比平涂（红黄蓝）+ 半调网点
- **主体/构图**：漫画式主体放大、网点背景、粗黑描边
- **提示词**：`Pop art comic style, {subject} as bold flat illustration, halftone dots, thick black outlines, vivid red yellow blue, Warhol-Lichtenstein vibe, NO text, NO letters, 2.35:1`
- **标题排版**：漫画爆炸框粗体主标题
- **点击钩子**：醒目、戏谑、视觉炸

### 26. 剪纸镂空（Paper-cut / Kirigami）
- **适用**：旅行、读书、健康、国风
- **配色**：层叠彩纸 + 留白阴影
- **主体/构图**：多层剪纸浮雕，正负形交错，光影层次
- **提示词**：`Paper-cut kirigami art, {subject} layered in colorful cut paper, delicate negative-space silhouettes, soft drop shadow depth, festive craft feel, NO text, NO letters, 2.35:1`
- **标题排版**：镂空描边主标题
- **点击钩子**：精致、手作温度、国风

### 27. 街头涂鸦（Street Graffiti）
- **适用**：健身、潮流、娱乐、搞笑
- **配色**：荧光喷漆撞色 + 水泥墙底
- **主体/构图**：喷漆笔触、涂鸦字、人物剪影、墙面肌理
- **提示词**：`Street graffiti mural, {subject} painted in bold spray-paint strokes on concrete wall, vibrant neon tags, urban grit, dynamic, NO text, NO letters, 2.35:1`
- **标题排版**：喷漆手写感主标题
- **点击钩子**：街头、热血、态度鲜明

### 28. 几何包豪斯（Geometric Bauhaus）
- **适用**：财经、科技、职场、教育
- **配色**：原色（红黄蓝）+ 黑白 + 几何形
- **主体/构图**：圆/方/三角构成，秩序感强，留白
- **提示词**：`Bauhaus geometric composition, {subject} built from primary-color circles squares triangles, clean grid, minimalist modernist, NO text, NO letters, 2.35:1`
- **标题排版**：无衬线几何主标题，色块分割
- **点击钩子**：理性、专业、设计感

### 29. 黑金奢华（Black & Gold Luxury）
- **适用**：财经、美妆、高端数码、美食
- **配色**：纯黑 + 香槟金，金属光泽
- **主体/构图**：奢华材质特写、金线描边、光斑
- **提示词**：`Luxury black and gold visual, {subject} with champagne-gold foil accents on deep black, metallic sheen, elegant premium product feel, soft spotlight, NO text, NO letters, 2.35:1`
- **标题排版**：烫金描边主标题
- **点击钩子**：高级、贵重、想拥有

### 30. 双色调（Duotone）
- **适用**：情感、职场、旅行、读书
- **配色**：两色映射（如青+品红、蓝+橙）
- **主体/构图**：照片经双色通道映射，强统一调性
- **提示词**：`Duotone photographic style, {subject} rendered in two-tone gradient map of teal and magenta, high contrast, editorial moody, NO text, NO letters, 2.35:1`
- **标题排版**：反白主标题，压在暗部
- **点击钩子**：统一、情绪、杂志感

### 31. 像素 8-bit（Pixel Art）
- **适用**：游戏、科技、搞笑、娱乐
- **配色**：有限调色板，方块马赛克
- **主体/构图**：像素方块构成主体，复古游戏感
- **提示词**：`8-bit pixel art, {subject} as blocky retro game sprite, limited palette, visible square pixels, nostalgic arcade, NO text, NO letters, 2.35:1`
- **标题排版**：像素方块字主标题
- **点击钩子**：复古、好玩、游戏魂

### 32. 森系手作（Botanical Craft）
- **适用**：健康、家居、读书、美食、宠物
- **配色**：草木绿 + 燕麦白 + 原木色
- **主体/构图**：植物插画、手账拼贴、麻绳/牛皮纸质感
- **提示词**：`Botanical handcraft style, {subject} with watercolor leaves and pressed-flower texture, kraft paper and linen background, cozy organic, NO text, NO letters, 2.35:1`
- **标题排版**：手写体感主标题，浅底
- **点击钩子**：自然、治愈、慢生活

---

## 风格组合示例（给用户看的「方案三选一」模板）

> 以「职场新人时间管理」为例：
> - **方案 A · 极简大字报**：米白底 + 墨绿强主体，超大标题《别让忙等于盲》，权威确定。
> - **方案 B · 信息图表**：蓝灰数据卡，上升箭头图标，标题《3 张表管住你的 24 小时》，干货感。
> - **方案 C · 治愈小清新**：暖光书桌 + 咖啡，标题《下班前的 10 分钟，决定明天的你》，情绪价值。

Agent 生成时，每个方案都应给出：风格名 + 适用理由 + 配色 + 主体 + 提示词 + 标题策略，便于用户 A/B 选择。
