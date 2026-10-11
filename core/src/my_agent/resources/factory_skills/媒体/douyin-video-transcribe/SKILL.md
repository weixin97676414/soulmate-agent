---
name: douyin-video-transcribe
description: 抖音视频文案提取 / 本地音视频转文字 / 多平台短视频文案提取。当用户分享抖音链接（v.douyin.com、douyin.com、iesdouyin.com 等）并提到"提取文案/提取文字/提取字幕/提取内容/提取文本""视频转文字/视频转文本/语音转录/音频转文字""这个视频说了什么/帮我看看这个视频讲什么/总结这个抖音视频"，或复制打开抖音的分享口令（含链接的整段分享文案）时触发；也支持本地视频/音频文件转文字（本地视频转文字/本地音频转文字/逐字稿/听写/语音识别）。另支持粘贴抖音/快手/小红书/视频号公开分享链接提取标题、简介、口播文案，输出原版/优化朗读版/精简浓缩版三版本 + 通用违禁词提醒 + 口播时长参考（触发词：文案提取、快手文案提取、小红书文案提取、视频号文案提取、链接提取文案、竞品文案收集）。底层用 Playwright 捕获抖音视频，Whisper medium 模型本地转录中文，无需云端 API，全程本地化。
author: Soulmate Agent团队成员：岸
---

# 抖音视频文案提取 & 本地音视频转录

## 一句话定位

从抖音链接或本地媒体文件提取语音 → Whisper 本地转录为中文文本 → agent 整理纠错 → 输出可读 Markdown。

## 触发场景（满足任一即命中）

**抖音链接场景**

| 用户输入特征 | 示例 |
|-------------|------|
| 抖音链接 + "提取文案/文字/字幕/内容/文本" | "帮我把这个抖音视频的文案提取出来" |
| 抖音链接 + "转文字/转录/转文本" | "这个抖音视频转成文字" |
| 抖音链接 + "说了什么/讲什么/总结" | "这个视频说了什么？帮我看看" |
| 抖音完整分享口令文本（含链接） | "0.23 复制打开抖音，看看… https://v.douyin.com/xxx" |
| 任何含 douyin.com 域名且意图是获取文本 | "帮我听一下这个视频在讲什么" |

**本地媒体文件场景**

| 用户输入特征 | 示例 |
|-------------|------|
| 视频/音频文件路径 + "转文字/转录" | "把 ./videos/talk.mp4 转成文字" |
| 媒体文件 + "字幕" 意图 | "帮我给这个视频加字幕" |
| 媒体文件 + "逐字稿/听写/语音识别" | "帮我把这段录音做成逐字稿" |
| 任意媒体文件 + 提取文本意图 | "把这段采访音频转成文本" |

**多平台链接场景（快手 / 小红书 / 视频号）**

| 用户输入特征 | 示例 |
|-------------|------|
| 快手/小红书/视频号链接 + "提取文案/文案提取" | "把这个小红书链接的文案提取出来" |
| 公开短视频分享链接 + "链接提取文案/竞品文案收集" | "收集这条快手视频的文案" |
| 视频号链接 + "提取口播/标题/简介" | "这条视频号讲了什么，把文案给我" |

> 关键判断：用户消息同时出现「抖音链接/分享文本」或「本地媒体文件路径」+「获取文本内容」的意图时触发。路径可为绝对/相对路径或 `@"..."` 附件引用语法。

## 支持的媒体格式

**视频**：`.mp4` `.m4v` `.avi` `.mkv` `.mov` `.wmv` `.flv` `.webm` `.ts`
**音频**：`.mp3` `.wav` `.flac` `.m4a` `.ogg` `.aac` `.wma` `.opus`

## 环境要求

| 需求 | 说明 |
|------|------|
| Python | 3.10–3.12（**3.13 不兼容**，greenlet DLL 加载失败） |
| numpy | **必须 < 2.0**（>=2.0 会触发 `ImportError: cannot load module more than once`） |
| VC++ Redist | Windows 下 torch 需要（https://aka.ms/vs/17/release/vc_redist.x64.exe） |
| 磁盘空间 | ~4GB（torch ~2GB + Whisper 模型 ~1.4GB + Chromium ~300MB） |

## 首次配置

`scripts/setup_env.py` 自动完成：①检测兼容 Python（3.10–3.12）②创建独立 venv（`<skill_dir>/venv/`）③按正确顺序装依赖（numpy<2 → requests/imageio[ffmpeg] → playwright → openai-whisper）④安装 Chromium ⑤验证导入 ⑥保存配置到 `.env_config.json`。

```bash
python scripts/setup_env.py
python scripts/setup_env.py --force           # 强制重建
python scripts/setup_env.py --mirror=pypi      # 使用官方源
python scripts/verify_env.py                   # 检查所有依赖
python scripts/verify_env.py --fix             # 检查并自动修复
python scripts/verify_env.py --json            # JSON 输出（供程序调用）
```

> **跨机器迁移注意**：`.env_config.json` 由 `setup_env.py` 自动生成，含机器特定路径。迁移后必须重新运行 `python scripts/setup_env.py`，不能直接复制配置文件。

## Agent 执行指引（必须先确定解释器）

```python
import json, os
from pathlib import Path

SKILL_DIR = Path("<本 skill 目录>")   # 运行时替换为实际安装路径
config_file = SKILL_DIR / ".env_config.json"

if config_file.exists():
    config = json.loads(config_file.read_text())
    PYTHON_EXE = config["venv_python"]    # 如 /path/to/venv/bin/python
else:
    print("请先运行: python scripts/setup_env.py")
    sys.exit(1)
```

**所有脚本必须用 `PYTHON_EXE` 运行**，不得使用系统默认 `python`。

## 快速开始

```bash
# 1. 首次使用：配置环境（仅需一次）
python scripts/setup_env.py

# 2a. 抖音链接 → 转录
python scripts/fetch_douyin_video.py <抖音短链接>

# 2b. 抖音链接 → 转录（指定输出目录）
python scripts/fetch_douyin_video.py <抖音短链接> --output ./result

# 2c. 本地文件 → 转录
python scripts/transcribe_local.py <视频或音频文件路径>

# 2d. 本地文件 → 转录（指定输出目录）
python scripts/transcribe_local.py audio.mp3 --output ./result
```

## 工作流程

**模式 A：抖音链接 → 转录**
```
抖音短链接 → Playwright 捕获视频 URL → 下载视频 → Whisper 转录 → agent 整理 → 保存 Markdown
```

**模式 B：本地文件 → 转录**
```
本地文件路径 → 格式验证 → Whisper 转录 → agent 整理 → 保存 Markdown
```

**模式 C：多平台链接 → 文案提取（快手 / 小红书 / 视频号）**
```
公开分享链接 → 识别平台 → 提取标题/简介/口播 → 违禁词提醒 → 三版本改写 → 时长参考 → 固定格式输出
```
仅处理用户输入的**公开可访问**分享链接，自动识别平台（抖音 / 快手 / 小红书 / 视频号），提取标题、简介、口播文案，**不篡改原文、不获取隐私数据**。抖音链接走模式 A 的 Playwright + Whisper 主流程；快手 / 小红书 / 视频号的提取依赖宿主可用的网页/工具能力，**若宿主无法访问目标链接，必须向用户说明，不得编造标题/文案**。

1. 对**原版口播文案**做通用违禁与敏感词提醒（只提醒，不修改、不删除内容）。
2. 生成「优化朗读版」（语句通顺、断句清晰，适合口播拍摄）与「精简浓缩版」（核心内容精炼，适合短平快视频）。
3. 统计字数并给出建议口播时长（中文口播约 4–5 字/秒，示例：126 字 ≈ 30 秒）。
4. 按下方固定格式输出，排版整洁、无冗余符号。

```
【标题】
(提取的标题)

【简介】
(提取的简介)

【口播文案 · 原版提取】
(完整原文)

【违禁 / 敏感词提醒】
(检测结果，无则显示未检测到)
备注：本提醒为通用合规参考，不代表任何平台官方审核意见。

【口播文案 · 优化朗读版】
(语句通顺、断句清晰，适合口播拍摄)

【口播文案 · 精简浓缩版】
(核心内容精炼，适合短平快视频)

【文案时长参考】
总字数：XXX 字
建议口播时长：约 XX 秒
```

模式 A / B 共用 `scripts/transcribe.py` 中的转录和 MD 写入逻辑。

### 步骤 1（仅抖音模式）：Playwright 捕获视频 URL
无需登录即可提取。Chrome 无头模式下打开短链接，首次等待 8 秒让 JS 填充 `video.src`，未捕获则自动增加到 13 秒重试一次。Playwright 失败时自动回退到 Douyin API 方案获取视频 URL。

> 为什么不用网络拦截？登录模态框覆盖时网络拦截失效，但 DOM 中 `video.src` 已就绪。

### 步骤 2（仅抖音模式）：下载视频（文件名含时间戳）
所有产物共用同一个 `YYYYMMDD_HHMMSS` 时间戳，重复运行不会覆盖。

```python
from scripts.transcribe import make_timestamp
ts = make_timestamp()  # "20260618_112500"
video_path = f"douyin_video_{ts}.mp4"
```

### 步骤 3：Whisper 转录
使用 `medium` 模型（~1.4GB，首次自动下载后缓存于 `~/.cache/whisper/`）。脚本内置**模型缓存损坏自动修复**：若检测到模型文件不完整或加载崩溃，自动删除缓存并重新下载。

### 步骤 4：整理纠错 → 保存 Markdown
脚本**不调用外部 LLM**。转录完成后输出原始文本，由 agent 自身完成整理：

| 允许 | 禁止 |
|------|------|
| ✅ 添加标点符号 | ❌ 删减内容 |
| ✅ 修正 ASR 错字 | ❌ 改写概括 |
| ✅ 语义分段断句 | ❌ 添加总结评论 |

Agent 整理完毕后调用 `scripts/transcribe.py` 中的 `write_cleaned_md()` 写入 `.md`：

```bash
# 抖音来源
cd <工作目录> && <venv_python> -c "
import sys
sys.path.insert(0, '<skill_dir>/scripts')
from transcribe import write_cleaned_md
md_path = write_cleaned_md(
    cleaned_text='''<整理后的文本>''',
    source='<原始短链接>',
    source_type='douyin',
    timestamp='<时间戳>',
    output_dir='<工作目录>'
)
print(f'MD saved: {md_path}')
"

# 本地文件来源：source_type='local'，source='<源文件名>'
```

## 产物清单

| 文件 | 内容 | 适用模式 |
|------|------|---------|
| `douyin_video_{ts}.mp4` | 原始视频 | 仅抖音 |
| `transcript_{ts}.txt` | Whisper 原始转录（含时间轴） | 两者 |
| `transcript_{ts}.json` | Whisper 完整 JSON 输出 | 两者 |
| `transcript_{ts}.md` | 整理后可读 Markdown | 两者 |

所有文件存放在运行脚本时的当前目录。本地文件模式**不会复制或移动**原始媒体文件，直接读取源文件。

## 常见问题排查

| 症状 | 原因 | 修复 |
|------|------|------|
| `DLL load failed: c10.dll` | VC++ Redist 缺失 | 安装 vc_redist.x64.exe |
| `ImportError: greenlet` (Python 3.13) | greenlet 与 3.13 不兼容 | 使用 Python 3.10–3.12 |
| `cannot load module more than once` | numpy >= 2 冲突 | `pip install "numpy<2" --force-reinstall` |
| Whisper SIGABRT 崩溃 | 模型缓存损坏 | 删除 `~/.cache/whisper/medium.pt` 后重试 |
| `pip install` 清华源 SSL 失败 | 清华源偶发故障 | 换用阿里云 `--mirror=aliyun` |
| 视频 URL 为空（抖音模式） | 需登录或 JS 未加载 | 脚本自动先 Playwright 再 API 备用；确认链接有效 |
| Douyin API 返回乱码 | API 响应编码异常 | `_fix_douyin_text` 自动检测并修复 latin1 编码 |
| Whisper 模型下载慢 | 网络问题 | 手动下载 medium.pt 放到 `~/.cache/whisper/` |
| 本地文件"不支持的格式" | 扩展名不在支持列表 | 用 FFmpeg 转 MP4/MP3 |
| 转录速度太慢（CPU） | 无 GPU 加速 | 安装 CUDA 版 torch |
| 中英混合识别不准确 | Whisper 对混合语言较弱 | 自定义 `initial_prompt` 提示词 |

## 技术要点

1. **登录墙绕过（抖音）**：`video.src` 由 JS 在登录模态框出现前填充，直接 DOM 查询即可捕获
2. **API 备用方案（抖音）**：Playwright 捕获失败时回退到 Douyin web aweme detail API
3. **Playwright 延迟导入**：未安装 playwright 时脚本仍可运行（自动走 API 路径）
4. **Playwright 重试机制**：首次等 8 秒，失败后增至 13 秒重试一次
5. **CDN URL 有效期**：抖音签名 URL（`v26-web.douyinvod.com/...`）约 24 小时，捕获后立即下载
6. **Douyin API 编码修复**：仅在确实乱码时二次解码，不破坏正常 UTF-8
7. **video ID 多格式提取**：支持 `/video/`、`/note/`、`/modal/`、`/share/video/`、`?modal_id=` 五种格式
8. **本地文件零拷贝**：直接从源文件路径读取
9. **模型选择**：硬编码 `medium`，中文最佳性价比
10. **FFmpeg 来源**：`imageio[ffmpeg]` 自动提供，无需系统安装
11. **环境隔离**：依赖装在 skill 目录下独立 venv，不影响系统 Python
12. **GPU 加速**：自动检测 CUDA，有 GPU 提速 5-10 倍
13. **initial_prompt**：默认中文提示文本，提升中英混合识别
14. **依赖分层**：本地转录只需核心依赖；抖音模式额外需要 playwright
15. **Windows UTF-8**：脚本入口自动 `sys.stdout.reconfigure(encoding='utf-8')`
16. **进度与预估**：自动获取媒体时长并预估转录耗时；计时从模型加载完毕后开始

## 文件结构

```
douyin-video-transcribe/
├── SKILL.md
├── scripts/
│   ├── transcribe.py                 # 共享模块：转录 + MD 写入（核心逻辑）
│   ├── fetch_douyin_video.py         # 抖音模式入口：捕获 → 下载 → 转录
│   ├── transcribe_local.py           # 本地模式入口：格式验证 → 转录
│   ├── setup_env.py                  # 环境自动配置（Windows/macOS/Linux）
│   └── verify_env.py                 # 环境快速检测（--fix 自动修复）
├── references/
│   └── whisper_usage.md              # Whisper 参数详解
├── .env_config.json                  # 运行时生成（setup_env.py 自动生成，勿手改）
└── venv/                             # 隔离 Python 环境（自动创建）
```

> `.env_config.json` 和 `venv/` 是运行时生成文件，跨机器迁移后需重新运行 `setup_env.py` 生成。


