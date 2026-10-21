# AI视频剪辑 - 快速入门指南

## 快速开始

### 方式一：一键剪辑（推荐）

```bash
python scripts/full_pipeline.py -i "./input" -d 180 -o "./output"
```

参数说明：
- `-i`: 素材目录（必填）
- `-d`: 目标时长（秒），默认180秒（3分钟）
- `-o`: 输出目录
- `-s`: 剪辑风格（auto/quick/slow/narrative）
- `--bgm`: 背景音乐目录

### 方式二：分步执行

```bash
# Step 1: 素材分析
python scripts/analyze_media.py -i "./input" -o "./output\分析结果"

# Step 2: 自动剪辑
python scripts/auto_clip.py -a "./output\分析结果\media_analysis.json" -o "./output\成品" -d 180

# Step 3: 音频处理
python scripts/audio_process.py -i "成品视频.mp4" -o "./output" --bgm "./bgm"

# Step 4: 字幕生成
python scripts/add_subtitles.py -i "成品视频.mp4" -o "./output" --burn

# Step 5: 特效处理
python scripts/add_effects.py -i "成品视频.mp4" -o "./output" --filter vivid

# Step 6: 最终导出
python scripts/export_final.py -i "成品视频.mp4" --preset high --storage "./output\成品"
```

## 使用配置文件

创建 `config.json`：

```json
{
  "input_dir": "./input",
  "output_dir": "./output",
  "target_duration": 180,
  "style": "quick",
  "transition": "cut",
  "bgm_enabled": true,
  "bgm_path": "./bgm",
  "bgm_volume": 0.3,
  "subtitle_enabled": true,
  "filter": "vivid",
  "export_preset": "high"
}
```

执行：
```bash
python scripts/full_pipeline.py -c config.json
```

## 场景示例

### 搞笑集锦（3-5分钟）
```bash
python scripts/full_pipeline.py \
  -i "./input\搞笑素材" \
  -o "./output\搞笑集锦" \
  -d 240 \
  -s quick \
  -t cut \
  --filter vivid
```

### 电影解说（5-10分钟）
```bash
python scripts/full_pipeline.py \
  -i "./input\解说素材" \
  -o "./output\电影解说" \
  -d 600 \
  -s narrative \
  --subtitle \
  --filter cinema
```

### 短视频（15-60秒）
```bash
python scripts/full_pipeline.py \
  -i "./input" \
  -o "./output\短视频" \
  -d 30 \
  -s quick \
  -t flash \
  --filter vivid \
  --effects vignette
```

### Vlog剪辑（3-10分钟）
```bash
python scripts/full_pipeline.py \
  -i "./input" \
  -o "./output\Vlog" \
  -d 300 \
  -s auto \
  --bgm "./bgm\轻音乐" \
  --filter warm
```

## 常用参数速查

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `-i / --input` | 素材目录 | 路径 |
| `-o / --output` | 输出目录 | 路径 |
| `-d / --duration` | 目标时长(秒) | 15/30/60/180/300/600 |
| `-s / --style` | 剪辑风格 | auto/quick/slow/narrative |
| `-t / --transition` | 转场效果 | fade/dissolve/cut/flash |
| `--filter` | 滤镜预设 | auto/vivid/vintage/cool/warm/bw/cinema |
| `--preset` | 导出预设 | high/medium/low |
| `--bgm` | 背景音乐目录 | 路径 |
| `--no-bgm` | 禁用背景音乐 | - |
| `--no-subtitle` | 禁用字幕 | - |
| `--effects` | 添加特效 | vignette/blur/glow/zoom |

## 目录结构建议

```
./output\
├── 素材\
│   ├── 搞笑素材\
│   ├── 背景音乐\
│   └── 音效\
├── 配置\
│   └── default_config.yaml
├── 工作空间\
│   ├── clip_20240101_120000\
│   └── clip_20240102_150000\
└── 成品\
    ├── 搞笑集锦_20240101.mp4
    └── 电影解说_20240102.mp4
```

## 常见问题

### Q: FFmpeg未找到
确保 FFmpeg 已安装并添加到系统 PATH：
```bash
# 验证安装
ffmpeg -version
```

### Q: Whisper模型未加载
首次使用字幕功能会自动下载模型，或手动下载：
```python
import whisper
model = whisper.load_model("base")
```

### Q: 素材中文路径问题
确保使用正确的编码：
```bash
chcp 65001  # Windows PowerShell
```

### Q: 剪辑速度慢
使用快速预设：
```bash
--preset low
```

## 下一步

- 查看 `references/default_config.yaml` 了解完整配置
- 查看 `references/ffmpeg_guide.md` 学习 FFmpeg 技巧
- 查看 `SKILL.md` 了解所有功能
