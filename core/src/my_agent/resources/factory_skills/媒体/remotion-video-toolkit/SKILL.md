---
name: remotion-video-toolkit
description: 用 Remotion + React 进行程序化视频创作的完整工具箱。覆盖动画、时序（插值/缓动/弹簧）、场景编排与转场、字幕（逐词高亮/导入 SRT）、3D（Three.js/React Three Fiber）、图表、Lottie、字体、Tailwind、音视频媒体处理、帧提取与尺寸测量，以及 CLI / Node.js API / AWS Lambda / Cloud Run 多方式渲染。触发场景：写 Remotion 代码、构建视频生成流水线、做数据驱动视频模板、程序化生成视频、批量个性化视频、动态广告、动画数据可视化、字幕视频、渲染 MP4、视频即服务。适用 React 组件渲染成真实 MP4。
author: Soulmate Agent团队成员：岸
---

# Remotion 程序化视频工具箱 (remotion-video-toolkit)

写 React 组件，产出真实 MP4。本技能提供 29 条按主题组织的规则文档（`rules/`），从第一个动画到生产级渲染流水线。

## 能做什么

- **规模化个性化视频**：把用户数据作为 JSON props，一个模板渲染成千上万个视频（年度总结、入职引导等）。
- **自动化社媒视频**：拉取实时数据（榜单、指标）每日/每周渲染，无需人工剪辑。
- **动态广告/营销视频**：替换客户名、产品图、价格，同模板无限变体，可服务端 API 或 Lambda 渲染。
- **动画数据可视化**：把仪表盘/KPI 变成可分享的带图表视频。
- **TikTok/Reels 字幕**：转写音频、逐词高亮字幕、导出即上传。
- **产品展示 / 教育讲解 / 视频即服务**：数据库/接口驱动，发送 JSON 返回视频。

## 环境要求

- Node.js 18+
- React 18+（Remotion 逐帧渲染 React 组件）
- Remotion — `npx create-video@latest`
- FFmpeg — 随 `@remotion/renderer` 附带，无需单独安装
- 服务端渲染：AWS 账号（Lambda）或 GCP 账号（Cloud Run）

## 快速开始

```bash
npx create-video@latest my-video        # 脚手架
cd my-video && npm start                # 浏览器预览
npx remotion render src/index.ts MyComposition out/video.mp4   # 渲染 MP4
npx remotion render src/index.ts MyComposition out.mp4 --props '{"title": "Hello"}'  # 传入动态数据
```

## 规则索引（详见 `rules/` 下对应文件）

### 核心

| 规则 | 文件 | 说明 |
|------|------|------|
| 组合 | `rules/compositions.md` | 定义视频、静帧、文件夹、默认 props、动态 metadata |
| 渲染 | `rules/rendering.md` | CLI、Node.js API、AWS Lambda、Cloud Run、Express 服务端模式 |
| 动态 metadata | `rules/calculate-metadata.md` | 渲染时动态设置时长、尺寸、props |

### 动画与时序

| 规则 | 文件 |
|------|------|
| 动画（淡入/缩放/旋转/滑动） | `rules/animations.md` |
| 时序（插值曲线、缓动、弹簧物理） | `rules/timing.md` |
| 排序编排（延迟/串联场景） | `rules/sequencing.md` |
| 转场 | `rules/transitions.md` |
| 裁剪（动画首尾裁切） | `rules/trimming.md` |

### 文字与排版

| 规则 | 文件 |
|------|------|
| 文字动画（打字机/逐词高亮/揭示） | `rules/text-animations.md` |
| 字体（Google Fonts 与本地字体） | `rules/fonts.md` |
| 文字测量（适配容器、检测溢出） | `rules/measuring-text.md` |

### 媒体

| 规则 | 文件 |
|------|------|
| 视频（嵌入/裁剪/调速/音量/循环/变调） | `rules/videos.md` |
| 音频（导入/裁剪/淡入淡出/音量与速度） | `rules/audio.md` |
| 图片（Img 组件） | `rules/images.md` |
| GIF（时间轴同步播放） | `rules/gifs.md` |
| 资产（导入任意媒体） | `rules/assets.md` |
| 解码检查（浏览器兼容性校验） | `rules/can-decode.md` |

### 字幕

| 规则 | 文件 |
|------|------|
| 转写字幕（Whisper / Deepgram / AssemblyAI） | `rules/transcribe-captions.md` |
| 显示字幕（TikTok 逐词高亮） | `rules/display-captions.md` |
| 导入 SRT | `rules/import-srt-captions.md` |

### 数据可视化 / 高级 / 媒体工具

| 规则 | 文件 |
|------|------|
| 图表（动画柱状/折线） | `rules/charts.md` |
| 3D（Three.js / React Three Fiber） | `rules/3d.md` |
| Lottie（After Effects 动画） | `rules/lottie.md` |
| TailwindCSS 样式 | `rules/tailwind.md` |
| DOM 测量 | `rules/measuring-dom-nodes.md` |
| 获取视频时长 | `rules/get-video-duration.md` |
| 获取视频尺寸 | `rules/get-video-dimensions.md` |
| 获取音频时长 | `rules/get-audio-duration.md` |
| 提取帧 | `rules/extract-frames.md` |

`rules/assets/` 内含可直接引用的示例组件：柱状图 `rules/assets/charts-bar-chart.tsx`、打字机文字 `rules/assets/text-animations-typewriter.tsx`、逐词高亮文字 `rules/assets/text-animations-word-highlight.tsx`。


## 参考文件

- `rules/*.md` — 29 条 Remotion 规则。
- `rules/assets/*.tsx` — 图表与文字动画示例组件。
