---
name: auto-video-clipper
description: 全自动 AI 视频剪辑：从素材导入到成片导出。自动识别视频/音频/图片素材、分析场景与内容、剔除黑屏模糊杂音、提取高光片段并排序、按风格匹配转场与滤镜、字幕生成与烧录、音频降噪与人声增强、BGM 卡点、特效添加，最后按预设参数导出成片。触发场景：自动剪辑、AI 剪辑视频、批量剪辑视频、视频素材自动处理、从素材自动生成成片、剪短视频、自动添加字幕、自动配乐、自动转场、特效自动添加、滤镜自动匹配、全自动视频制作。
author: Soulmate Agent团队成员：岸
---

# 全自动 AI 视频剪辑 (auto-video-clipper)

从素材目录到成片的无人干预剪辑流水线。核心依赖：FFmpeg（必需）、Whisper（字幕，可选）、MoviePy/Pillow/NumPy/librosa（Python 处理）。

## 执行流程

### Step 1 素材准备与分析

```bash
python3 scripts/analyze_media.py --input "<素材目录>" --output "<分析输出目录>"
```

自动解析视频(mp4/mov/avi/mkv)、音频(mp3/wav)、图片(jpg/png)，提取元数据、建立索引，输出分析报告 JSON。

### Step 2 配置剪辑参数

按需设置：目标时长（15s/30s/1min/3min/5min）、输出格式（mp4 推荐 / mov）、分辨率（保持原分辨率或指定如 1080p）、存储路径。默认配置见 `references/default_config.yaml`。

### Step 3 执行自动剪辑

```bash
python3 scripts/auto_clip.py --config "<配置文件路径>"
```

按配置自动做片段选取、转场添加、时长控制。

### Step 4 音频处理

`scripts/audio_process.py`：音频分离、人声增强（降噪/清晰度）、背景音乐匹配、音效添加。

### Step 5 字幕与特效

```bash
python3 scripts/add_subtitles.py --input "<成片路径>" --output "<带字幕版本>"
python3 scripts/add_effects.py   --input "<视频文件>"   --output "<添加特效后视频>"
```

`scripts/add_subtitles.py` 用 Whisper 自动识别台词（支持中英双语）、智能排版、错别字修正。

### Step 6 最终导出

```bash
python3 scripts/export_final.py --input "<待导出视频>" --preset "高质量/标准/压缩"
```

按预设导出，自动设置分辨率/帧率/比特率，按「日期+主题+时长」命名并存储至预设路径。

### 一键全流程

```bash
python3 scripts/full_pipeline.py --config "<配置文件路径>"   # 整合所有模块，素材→成片
```

## 脚本说明

| 脚本 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `scripts/analyze_media.py` | 素材分析 | 素材目录 | 分析报告 JSON |
| `scripts/auto_clip.py` | 自动剪辑 | 分析报告+配置 | 中间视频文件 |
| `scripts/audio_process.py` | 音频处理 | 视频文件 | 处理后音频 |
| `scripts/add_subtitles.py` | 字幕生成 | 视频文件 | 带字幕视频 |
| `scripts/add_effects.py` | 特效添加 | 视频文件 | 添加特效后视频 |
| `scripts/export_final.py` | 最终导出 | 处理后视频 | 成片文件 |
| `scripts/full_pipeline.py` | 全流程整合 | 配置 | 成片 |

## 默认配置（节选）

```yaml
output: {format: mp4, resolution: "1920x1080", frame_rate: 30, bitrate: "8M"}
subtitle: {enabled: true, language: "zh-CN", position: "bottom_center", font_size: 36, color: "white"}
audio: {bgm_volume: 0.3, voice_volume: 1.0, enhance_voice: true}
style: {transition: "fade", transition_duration: 0.5, filter_preset: "auto"}
export: {storage_path: "<输出目录>", naming: "{date}_{theme}_{duration}"}
```

完整默认配置见 `references/default_config.yaml`。

## 适用场景

| 场景 | 推荐配置 | 预期时长 |
|------|----------|----------|
| 搞笑集锦 | 快节奏卡点+音效 | 3-5 分钟 |
| 电影解说 | 叙事风格+字幕 | 5-15 分钟 |
| 短视频 | 高潮片段+滤镜 | 15-60 秒 |
| Vlog 剪辑 | 自然过渡+BGM | 3-10 分钟 |
| 教程视频 | 清晰叙事+标注 | 5-30 分钟 |

## 环境要求与安装

- **必需**：FFmpeg（`ffmpeg` / `ffprobe`）。
- **Python 依赖**（见 `requirements.txt`）：Pillow、numpy、moviepy、openai-whisper、pydub、librosa、tqdm、pyyaml。
- 字幕依赖 Whisper 模型，**首次使用需下载模型文件**。

```bash
pip install -r requirements.txt
which ffmpeg   # 应返回路径
```

## 注意事项 / 踩坑

- 素材路径含中文时，FFmpeg 命令需使用 UTF-8 编码。
- 批量剪辑建议用队列管理，避免内存溢出。
- 建议使用清晰、无严重抖动的高质量素材。
- 性能参考：1-5 分钟视频剪辑约需 2-3 分钟完成。
- 导出前确认输出路径空间充足；导出失败会自动重试或记录日志。
- 脚本调用 FFmpeg 与可选 Whisper；**本机未实跑验证完整流水线**，首次使用先跑 `scripts/analyze_media.py` 确认环境与模型可用。


## 参考文件

- `references/default_config.yaml` — 默认剪辑配置模板。
- `references/quickstart.md` — 快速上手。
- `references/ffmpeg_guide.md` — 相关 FFmpeg 说明。
- `requirements.txt` — Python 依赖。
- `scripts/*.py` — 七个流水线脚本。
