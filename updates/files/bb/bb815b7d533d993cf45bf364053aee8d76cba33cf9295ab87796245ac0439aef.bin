# FFmpeg 命令参考

所有命令均带 `-y`（覆盖输出）与 `-hide_banner`（清爽输出）。时间格式：`HH:MM:SS` / `MM:SS` / `SS` / `HH:MM:SS.mmm`。

## 剪切/裁剪视频

```bash
ffmpeg -y -hide_banner -i "INPUT" -ss START_TIME -to END_TIME -c copy "OUTPUT"
```

- 从 1:21 切到 1:35：`ffmpeg -y -hide_banner -i "video.mp4" -ss 00:01:21 -to 00:01:35 -c copy "video_trimmed.mp4"`
- 取前 2 分钟：`ffmpeg -y -hide_banner -i "video.mp4" -ss 00:00:00 -to 00:02:00 -c copy "video_clip.mp4"`

## 格式转换

```bash
# MP4（最兼容）
ffmpeg -y -hide_banner -i "INPUT" -c:v libx264 -c:a aac "OUTPUT.mp4"
# MKV（无损换容器）
ffmpeg -y -hide_banner -i "INPUT" -c copy "OUTPUT.mkv"
# WebM（网页优化）
ffmpeg -y -hide_banner -i "INPUT" -c:v libvpx-vp9 -c:a libopus "OUTPUT.webm"
# AVI
ffmpeg -y -hide_banner -i "INPUT" -c:v mpeg4 -c:a mp3 "OUTPUT.avi"
# MOV
ffmpeg -y -hide_banner -i "INPUT" -c:v libx264 -c:a aac "OUTPUT.mov"
```

支持格式：mp4 / mkv / avi / webm / mov / flv / wmv。

## 改宽高比（加黑边）

| 比例 | 分辨率 | 用途 |
|------|--------|------|
| 16:9 | 1920x1080 | YouTube、TV |
| 4:3 | 1440x1080 | 旧电视 |
| 1:1 | 1080x1080 | Instagram 方图 |
| 9:16 | 1080x1920 | TikTok、Reels、Stories |
| 21:9 | 2560x1080 | 超宽/影院 |

```bash
ffmpeg -y -hide_banner -i "INPUT" -vf "scale=WIDTH:HEIGHT:force_original_aspect_ratio=decrease,pad=WIDTH:HEIGHT:(ow-iw)/2:(oh-ih)/2:black" -c:a copy "OUTPUT"
```

示例：
- 16:9：`... scale=1920:1080 ... pad=1920:1080 ...`
- 1:1：`... scale=1080:1080 ... pad=1080:1080 ...`
- 9:16：`... scale=1080:1920 ... pad=1080:1920 ...`

## 改分辨率

| 名称 | 尺寸 |
|------|------|
| 4K | 3840x2160 |
| 1080p | 1920x1080 |
| 720p | 1280x720 |
| 480p | 854x480 |
| 360p | 640x360 |

```bash
ffmpeg -y -hide_banner -i "INPUT" -vf "scale=WIDTH:HEIGHT" -c:a copy "OUTPUT"
# 例：720p
ffmpeg -y -hide_banner -i "video.mp4" -vf "scale=1280:720" -c:a copy "video_720p.mp4"
```

## 压缩视频

CRF：18（高质量）→ 28（低质量），23 均衡。

```bash
ffmpeg -y -hide_banner -i "INPUT" -c:v libx264 -crf CRF_VALUE -preset medium -c:a aac -b:a 128k "OUTPUT"
```

- 均衡（CRF 23）：`-c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k`
- 更小（CRF 28）：`-c:v libx264 -crf 28 -preset fast -c:a aac -b:a 96k`
- 高质量（CRF 18）：`-c:v libx264 -crf 18 -preset slow -c:a aac -b:a 192k`

## 提取音频

```bash
ffmpeg -y -hide_banner -i "INPUT" -vn -acodec CODEC "OUTPUT.FORMAT"
```

| 格式 | 编码 |
|------|------|
| mp3 | libmp3lame |
| aac | aac |
| wav | pcm_s16le |
| flac | flac |
| ogg | libvorbis |

例：`ffmpeg -y -hide_banner -i "video.mp4" -vn -acodec libmp3lame "video.mp3"`

## 去音频（静音视频）

```bash
ffmpeg -y -hide_banner -i "INPUT" -an -c:v copy "OUTPUT"
```

## 调速

```bash
# 加速（如 2x）
ffmpeg -y -hide_banner -i "INPUT" -filter_complex "[0:v]setpts=0.5*PTS[v];[0:a]atempo=2.0[a]" -map "[v]" -map "[a]" "OUTPUT"
# 减速（如 0.5x 半速）
ffmpeg -y -hide_banner -i "INPUT" -filter_complex "[0:v]setpts=2.0*PTS[v];[0:a]atempo=0.5[a]" -map "[v]" -map "[a]" "OUTPUT"
```

公式：视频 `setpts=(1/speed)*PTS`（2x → 0.5*PTS）；音频 `atempo=speed`（须在 0.5–2.0，超出需链式叠加）。

## 转 GIF

```bash
ffmpeg -y -hide_banner -i "INPUT" -ss START -t DURATION -vf "fps=15,scale=480:-1:flags=lanczos" -loop 0 "OUTPUT.gif"
# 例：从 0:10 起 5 秒
ffmpeg -y -hide_banner -i "video.mp4" -ss 00:00:10 -t 5 -vf "fps=15,scale=480:-1:flags=lanczos" -loop 0 "video.gif"
```

## 旋转/翻转

```bash
ffmpeg -y -hide_banner -i "INPUT" -vf "transpose=1" -c:a copy "OUTPUT"           # 顺时针 90°
ffmpeg -y -hide_banner -i "INPUT" -vf "transpose=2" -c:a copy "OUTPUT"           # 逆时针 90°
ffmpeg -y -hide_banner -i "INPUT" -vf "transpose=2,transpose=2" -c:a copy "OUTPUT" # 180°
ffmpeg -y -hide_banner -i "INPUT" -vf "hflip" -c:a copy "OUTPUT"                 # 水平镜像
ffmpeg -y -hide_banner -i "INPUT" -vf "vflip" -c:a copy "OUTPUT"                 # 垂直翻转
```

## 截帧/截图

```bash
ffmpeg -y -hide_banner -i "INPUT" -ss TIMESTAMP -frames:v 1 "OUTPUT.jpg"
# 例：1:30 处
ffmpeg -y -hide_banner -i "video.mp4" -ss 00:01:30 -frames:v 1 "screenshot.jpg"
```

## 加水印/Logo

| 位置 | overlay 值 |
|------|-----------|
| 左上 | overlay=10:10 |
| 右上 | overlay=W-w-10:10 |
| 左下 | overlay=10:H-h-10 |
| 右下 | overlay=W-w-10:H-h-10 |
| 居中 | overlay=(W-w)/2:(H-h)/2 |

```bash
ffmpeg -y -hide_banner -i "VIDEO" -i "LOGO" -filter_complex "overlay=POSITION" "OUTPUT"
# 例：右上角
ffmpeg -y -hide_banner -i "video.mp4" -i "logo.png" -filter_complex "overlay=W-w-10:10" "video_watermarked.mp4"
```

## 烧字幕

```bash
ffmpeg -y -hide_banner -i "INPUT" -vf "subtitles='SUBTITLE_FILE'" "OUTPUT"
# 例
ffmpeg -y -hide_banner -i "video.mp4" -vf "subtitles='subtitles.srt'" "video_subtitled.mp4"
```

## 合并/拼接

**Step 1** 创建 `files.txt`：

```
file 'video1.mp4'
file 'video2.mp4'
file 'video3.mp4'
```

**Step 2** 拼接：

```bash
ffmpeg -y -hide_banner -f concat -safe 0 -i files.txt -c copy "merged.mp4"
```

## 生成命令时的响应格式

1. 用代码块给出 FFmpeg 命令；2. 简述作用；3. 说明输出文件名是否为推断。
