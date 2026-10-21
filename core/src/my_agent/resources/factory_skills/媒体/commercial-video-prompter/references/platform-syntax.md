# 各平台提示词语法差异参考

## Sora（OpenAI）

### 语法特点
- 倾向于**自然语言描述**，类散文风格
- 支持长提示词（建议 150-300 词英文）
- 对摄像机运动指令响应好（camera movement keywords）
- 对情绪/氛围词汇理解深

### 关键指令词汇
```
Camera movements:
- slow push-in / slow pull-out（慢速推进/拉出）
- tracking shot（跟踪镜头）
- aerial drone shot（无人机俯拍）
- static locked-off shot（固定机位）
- handheld subtle movement（轻微手持感）

Lighting:
- golden hour soft backlight（黄金时段柔和逆光）
- hard single source Rembrandt light（伦勃朗单侧硬光）
- diffused window light（漫射窗光）
- industrial overhead fluorescent（工业顶置荧光灯）

Texture/Realism:
- hyper-realistic skin texture with visible pores（超写实皮肤毛孔纹理）
- peach fuzz facial hair caught in light（光线中的汗毛细节）
- natural subsurface scattering（自然皮下散射）
- micro-scratches on metal surface（金属表面微划痕）
```

### 示例结构
```
[场景环境描述], [主体状态], [产品/道具描述], [光线描述], 
[摄像机运动], [情绪基调], [材质细节], cinematic, 8K, photorealistic
```

---

## Runway Gen-3 / Gen-4

### 语法特点
- 对**动态描述**响应更强（motion-first）
- 建议将"运动"放在提示词**前半部分**
- 支持图像参考（Image-to-Video），建议提供参考图
- 对风格词汇（如"Studio Ghibli style"）敏感

### 关键指令词汇
```
Motion descriptors（运动描述词，放句首）:
- Slowly drifting（缓慢漂移）
- Gently breathing（轻柔呼吸感）
- Subtle micro-movements（细微微动）
- Camera slowly pushing in（镜头缓推）
- Soft parallax depth effect（视差景深效果）

Style anchors（风格锚定词）:
- Shot on ARRI Alexa（ARRI 摄影机感）
- Anamorphic lens flare（变形镜头光晕）
- Film grain texture（胶片颗粒感）
- Cinematic color grading（电影调色感）
```

### 示例结构
```
[运动描述 FIRST], [场景], [主体], [光线], [风格词], 
[摄像机], [情绪], [品质词: cinematic, photorealistic, 4K]
```

---

## 可灵 Kling（快手）

### 语法特点
- 支持**中英文混合**提示词
- 对中文理解优秀，推荐使用中文主体描述
- 支持"负面提示词"（negative prompt）
- 对写实人像质量有专项优化

### 推荐中文提示词结构
```
[环境/背景描述]，[主体人物/产品描述]，[光线描述]，
[镜头/构图描述]，[情绪/氛围描述]，[材质质感描述]，
电影级画质，超写实，8K分辨率
```

### 常用负面提示词（Negative Prompt）
```
塑料感皮肤，变形，畸形手指，低质量，模糊，噪点，
卡通感，动漫风格，过度饱和，人工智能感，假脸
```

### 关键中文指令词
```
光线：伦勃朗光、窗边柔光、逆光轮廓、工业顶光、丁达尔光效
镜头：微距特写、浅景深虚化、慢速推进、固定机位、手持轻微晃动
质感：皮肤毛孔纹理、金属拉丝质感、丝绸纤维细节、瓷器釉面反光
情绪：静谧温暖、高冷克制、情绪张力、情感释放、庄重威严
```

---

## 即梦 AI（字节跳动）

### 语法特点
- 与可灵类似，中文优化好
- 对镜头运动描述响应稳定
- 支持风格参考图上传

### 推荐结构
```
画面描述 + 光线 + 镜头运动 + 风格标签 + 品质标签
```

---

## 海螺 AI（MiniMax）

### 语法特点
- 中文理解强，人物一致性好
- 适合剧情/叙事类视频

### 推荐结构
```
[叙事场景]，[人物状态]，[情绪变化]，[产品出现方式]，
电影质感，写实风格
```

---

## 跨平台通用强制注入词

无论使用哪个平台，以下质量关键词**必须注入**：

**英文版（Sora/Runway）：**
```
cinematic, photorealistic, 8K resolution, natural skin texture, 
visible pores, peach fuzz detail, subsurface scattering, 
no plastic skin, no AI artifacts, professional color grading
```

**中文版（可灵/即梦/海螺）：**
```
电影质感，超写实，8K画质，自然皮肤纹理，毛孔可见，
汗毛细节，无塑料感，无AI痕迹，专业调色
```

---

## 平台选择建议

| 场景 | 推荐平台 |
|------|---------|
| 极致写实人像（东方美女/男模） | 可灵 Kling |
| 宏大场景/科幻/工业 | Sora |
| 快速迭代/风格化 | Runway Gen-3 |
| 剧情叙事类 | 海螺 AI |
| 国内小红书/抖音场景 | 即梦 AI |
