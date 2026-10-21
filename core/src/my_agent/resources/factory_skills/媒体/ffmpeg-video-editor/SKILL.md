---
name: ffmpeg-video-editor
description: FFmpeg 视频编辑。把自然语言剪辑需求翻译成正确的 FFmpeg 命令，并提供即用脚本，覆盖剪切/裁剪、格式转换、改宽高比、改分辨率、压缩、提取/去除音频、调速、转 GIF、旋转翻转、截帧、加水印、烧字幕、合并拼接，以及按时间戳切片、烧录 SRT、导出多平台比例（9:16/1:1/16:9）、从长视频提取精彩片段。触发场景：剪视频、剪切片段、合并视频、转格式、压缩视频、提取音频、加字幕、调速、改比例、竖屏、裁切、加水印、做 gif、截帧、批量处理视频、自动剪辑、提取精华片段。
author: Soulmate Agent团队成员：岸
---

# FFmpeg 视频编辑 (ffmpeg-video-editor)

两条用法：**命令式**（把自然语言需求翻成 FFmpeg 命令，见 `references/ffmpeg命令参考.md`）与**脚本式**（本目录 `scripts/` 下即用脚本）。

## 环境要求

需要 `ffmpeg` 与 `ffprobe`：

```bash
# macOS
brew install ffmpeg
# Debian/Ubuntu
sudo apt-get install ffmpeg
# 或见 https://ffmpeg.org/download.html
```

## 脚本式用法

### 基础编辑（Bash 包装脚本）

```bash
scripts/cut.sh          input.mp4 --start 00:00:10 [--end 00:00:30 | --duration 30] --out out.mp4
scripts/merge.sh        a.mp4 b.mp4 [c.mp4 ...] --out merged.mp4
scripts/convert.sh      input.mov --format mp4 --out out.mp4
scripts/extract-audio.sh input.mp4 --out audio.mp3
scripts/add-subtitles.sh input.mp4 subs.srt --out out.mp4
scripts/resize.sh       input.mp4 [--width 1920 --height 1080 | --scale 720] --out out.mp4
scripts/speed.sh        input.mp4 --rate 2.0 --out out.mp4      # 2.0=2倍速, 0.5=半速
scripts/crop.sh         input.mp4 --x 100 --y 100 --width 800 --height 600 --out out.mp4
```

### 快速切片 / 字幕 / 多平台导出（Python 脚本）

```bash
python3 scripts/cut_video.py --input video.mp4 --start 10 --duration 30 --output clip.mp4
python3 scripts/cut_video.py --input video.mp4 --segments "0-30,60-90,120-150" --output ./clips/
python3 scripts/burn_subtitles.py --input video.mp4 --srt subs.srt --output subtitled.mp4
python3 scripts/export_social.py --input video.mp4 --format vertical --duration 60 --output shorts/
python3 scripts/extract_highlights.py --input long.mp4 --num-clips 5 --min-duration 8 --output ./clips/
```

导出格式：`vertical`=9:16（抖音/快手/小红书），`square`=1:1（Instagram），`horizontal`=16:9（YouTube/B站）。

`scripts/burn_subtitles.py` 支持字幕位置、字体大小、颜色自定义。`scripts/extract_highlights.py` 用场景检测算法定位切换点。

## 命令式用法

用户描述操作 → 识别操作与参数 → 生成命令。参数缺失时按操作推断输出文件名（如 `video_trimmed.mp4`）；**始终加 `-y` 与 `-hide_banner`**。常用命令（完整清单见 `references/ffmpeg命令参考.md`）：

```bash
# 剪切（-c copy 不重编码，最快）
ffmpeg -y -hide_banner -i "in.mp4" -ss 00:01:21 -to 00:01:35 -c copy "out.mp4"

# 改宽高比（加黑边）
ffmpeg -y -hide_banner -i "in.mp4" -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" -c:a copy "vertical.mp4"

# 压缩（CRF 18 高质量 → 28 小体积，23 均衡）
ffmpeg -y -hide_banner -i "in.mp4" -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k "out.mp4"

# 烧字幕
ffmpeg -y -hide_banner -i "in.mp4" -vf "subtitles='subs.srt'" "out.mp4"

# 合并（先写 files.txt: file 'a.mp4'）
ffmpeg -y -hide_banner -f concat -safe 0 -i files.txt -c copy "merged.mp4"
```

## 常见工作流

- **社媒片段**：`scripts/cut.sh` 切片 → `scripts/resize.sh` 转竖屏。
- **提取精华**：多次 `scripts/cut.sh` 分段 → `scripts/merge.sh` 合并。
- **换/混背景音乐**：

```bash
# 替换音轨
ffmpeg -i v.mp4 -i m.mp3 -c:v copy -map 0:v:0 -map 1:a:0 -shortest out.mp4
# 混音（原声 70% + 音乐 30%）
ffmpeg -i v.mp4 -i m.mp3 -filter_complex "[0:a]volume=0.7[a0];[1:a]volume=0.3[a1];[a0][a1]amix=inputs=2:duration=first" -c:v copy -shortest out.mp4
```

## 技巧

- 质量：`-crf 18` 高质量，`-crf 28` 小体积（默认 23）。
- 预设：`-preset slow` 更高压缩比，`-preset fast` 更快编码。
- 硬件加速：Apple Silicon 加 `-c:v h264_videotoolbox`。
- `-c copy` 不重编码（快），但可编辑能力受限。

## 排障

- **合并报 Codec mismatch**：视频需同编码/分辨率/帧率，先重编码再合并：
  `ffmpeg -i a.mp4 -c:v libx264 -c:a aac -vf "scale=1920:1080" -r 30 tmp_a.mp4`
- **字幕不显示**：确认字幕格式与扩展名匹配（.srt/.ass/.vtt），检查编码：
  `file -I subs.srt` 应显示 `charset=utf-8`；需要时 `iconv -f GBK -t UTF-8 subs.srt > subs_utf8.srt`。

## 注意事项

- 脚本均为本机 Bash/Python3，调用 ffmpeg；**本机未实跑验证每个脚本**，首次使用先跑一条最短命令确认 ffmpeg 可用。
- 含中文路径时确保 UTF-8 编码传入 ffmpeg。
- 破坏性覆盖前确认输出文件名；统一带 `-y` 会静默覆盖，注意别覆盖源文件。


## 参考文件

- `references/ffmpeg命令参考.md` — 全量 FFmpeg 命令参考（剪切/转换/比例/分辨率/压缩/音频/调速/GIF/旋转/截帧/水印/字幕/合并/时间格式）。
- `scripts/*.sh` — Bash 包装脚本；`scripts/*.py` — 快速切片/烧字幕/多平台导出/精华提取。
