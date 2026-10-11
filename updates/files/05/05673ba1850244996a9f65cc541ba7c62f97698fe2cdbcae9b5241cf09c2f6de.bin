---
name: zhihu-topic-selection
description: 一键抓取知乎热榜、推荐问题、邀请回答三项数据，整理为可检索的本地 SQLite 数据库并生成可视化面板。触发：知乎选题、知乎热榜、抓取热榜、知乎推荐问题、邀请回答、找选题、领域热点、知乎数据采集、zhihu-fetcher、选题助手。全程本地运行，不依赖第三方 API。
author: Soulmate Agent团队成员：岸
---

# 知乎内容选题助手

抓取知乎**热榜**、**推荐问题**、**邀请回答**三项核心数据，自动整理为可检索的本地数据库，帮助内容创作者快速发现选题、跟踪领域热点、了解读者关注方向。全程本地运行，不依赖任何第三方 API。

## 适用人群

- 社媒运营：追踪行业热点，策划知乎内容矩阵
- 博主 / KOL：发现高关注度问题，定位写回答和写文章的方向
- 领域写作者：了解自己擅长领域的读者在关注什么
- 知乎新手：快速了解平台热点分布，找到合适的答题切入点

## 5 分钟快速上手

**第一次使用，只需三步：**

```bash
# 第1步: 登录知乎（Edge 浏览器），然后关闭浏览器
# 第2步: 自动提取 Cookie
node scripts/auto_cookie.js --headless

# 第3步: 一键采集全部数据
python scripts/save_to_db.py all

# 完成！查看可视化报告
python scripts/generate_html.py
# 用浏览器打开 data/index.html
```

若第 2 步提示「未检测到登录态」，说明 Edge 中没有知乎登录记录。打开 Edge 访问 https://www.zhihu.com 扫码登录一次，再重新运行即可。以后每天只需运行第 3 步一条命令。

## 功能

### 获取实时热搜（热榜）

知乎全站热榜，含排名、热度值、内容摘要。**不需要登录**：

```bash
python scripts/save_to_db.py hot
```

### 获取推荐问题

知乎创作者中心为你的账号**智能推荐的答题机会**，含浏览数、回答数、关注数、推荐理由。**需要登录**：

```bash
python scripts/save_to_db.py recommend
```

### 获取邀请回答

别人**直接邀请你回答**的问题列表。**需要登录**：

```bash
python scripts/save_to_db.py invited
```

### 一键全部采集

```bash
python scripts/save_to_db.py all
# 依次执行: hot(50条) → recommend(100条) → invited(100条)
```

### 生成可视化报告

```bash
python scripts/generate_html.py
```

用浏览器打开 `data/index.html`：热榜支持日期筛选 + 关键词搜索 + 热度过滤，点击卡片跳转知乎；问题列表按来源（推荐/邀请）筛选、搜索、按关注数排序；另含抓取日志。

## 数据存储结构

所有数据存储在 `data/zhihu.db`（SQLite）中，三张核心表：

### articles 表（热榜）

| 字段 | 说明 |
|------|------|
| `rank` | 热榜排名 (1-30) |
| `title` | 标题 |
| `url` | 知乎链接 |
| `heat` | 热度值 |
| `summary` | 内容摘要 |
| `fetch_date` | 抓取日期 |

### questions 表（推荐/邀请问题）

| 字段 | 说明 |
|------|------|
| `qid` | 知乎问题 ID |
| `title` | 问题标题 |
| `url` | 问题链接 |
| `answer_count` | 已有回答数 |
| `follower_count` | 关注数 |
| `view_count` | 浏览数 |
| `source` | `recommend`（推荐）/ `invited`（邀请） |
| `recommend_reason` | 推荐理由 |
| `fetch_date` | 抓取日期 |

### fetch_logs 表（抓取日志）

记录每次抓取的时间、来源、新增/更新条数。

## 如何查询和搜索

### 命令行

```bash
python scripts/query.py today            # 今日热榜
python scripts/query.py date 2026-06-26  # 指定日期
python scripts/query.py questions recommend
python scripts/query.py questions invited
```

### 可视化面板

打开 `data/index.html`，支持按日期筛选、关键词搜索、来源过滤。

### 直接查数据库

```bash
sqlite3 data/zhihu.db

# 按关键词搜热榜
SELECT title, rank, heat FROM articles
WHERE title LIKE '%AI%' AND fetch_date='2026-06-26'
ORDER BY rank;

# 搜高关注度推荐问题
SELECT title, follower_count, answer_count, recommend_reason
FROM questions
WHERE source='recommend' AND fetch_date='2026-06-26'
ORDER BY follower_count DESC LIMIT 20;
```

### 导出 Excel / CSV

```bash
sqlite3 -header -csv data/zhihu.db "SELECT rank, title, heat, fetch_date FROM articles WHERE fetch_date='$(date +%Y-%m-%d)'" > hot.csv
sqlite3 -header -csv data/zhihu.db "SELECT title, follower_count, answer_count, recommend_reason FROM questions WHERE source='recommend' AND fetch_date='$(date +%Y-%m-%d)'" > recommend.csv
```

## Cookie 认证

推荐和邀请数据需要知乎登录态。Cookie 保存在 `config/fallback-sources.json`（仅本地，不上传任何地方）。

### 方式一：自动获取（推荐）

从 Edge 浏览器配置文件中自动提取，无需手动操作：

```bash
# 1. 关闭所有 Edge 窗口
# 2. 运行自动提取
node scripts/auto_cookie.js --headless
```

脚本会自动检测登录状态。**如果提示未登录** → 打开 Edge 访问知乎扫码登录一次即可，之后提取都是自动的。

### 方式二：手动复制（备用）

1. 打开 https://www.zhihu.com，确认已登录
2. 按 **F12** → 点击 **Network（网络）** 标签
3. 按 **F5** 刷新
4. 点一个 `www.zhihu.com` 开头的请求
5. 右侧 **Request Headers** → 找到 `Cookie:` 行
6. 双击值 → **Ctrl+A** → **Ctrl+C**
7. 运行 `python scripts/save_cookie.py "<粘贴内容>"`

## 遇到错误怎么办

| 现象 | 处理 |
|------|------|
| 提示「未检测到登录态」或采集数据为空 | Cookie 过期，重新运行 `node scripts/auto_cookie.js --headless`；Edge 也退登了就重新扫码 |
| 采集推荐/邀请时 401 | 同上，Cookie 过期 |
| Edge 提示 "browser already running" | 后台有残留进程，`taskkill /F /IM msedge.exe` 后重试 |
| 网络超时 / 抓取失败 | 知乎接口偶发波动，重试一次；工具自动重试最多 2 次 |

采集频率：工具内置 2 秒请求间隔；若短时间内反复大量采集（如 1 分钟内跑 5 次 all），建议间隔 5 分钟以上。

## 常见问题

- **Cookie 多久过期？** 一般 7-30 天。过期后推荐和邀请无法采集（热榜不受影响），重新提取即可。
- **热榜不需要登录，为什么还要配置 Cookie？** 只采集热榜可完全跳过 Cookie 配置。
- **可以同时登录多个知乎账号吗？** 工具读取 Edge 的 Profile，Edge 登录哪个账号就采哪个账号。
- **支持其他浏览器吗？** 目前仅支持 Edge。知乎若登录在 Chrome，可先在 Edge 扫码登录。
- **能定时自动采集吗？** Windows 用「任务计划程序」，Mac/Linux 用 `crontab`，例如每天早上 9 点执行 `python scripts/save_to_db.py all`。

## 文件结构

```
zhihu-topic-selection/
├── SKILL.md
├── package.json
├── config/fallback-sources.json   # Cookie 配置（不入 git）
├── data/                          # 运行时生成：zhihu.db、index.html
├── scripts/
│   ├── save_to_db.py              # 数据采集主入口
│   ├── generate_html.py           # HTML 报告生成
│   ├── query.py                   # 命令行查询工具
│   ├── auto_cookie.js             # 自动 Cookie 提取
│   ├── save_cookie.py             # 手动 Cookie 保存
│   └── db.py                      # 数据库操作
└── snippets/
    ├── fetch-hot.js               # 热榜抓取
    └── fetch-featured.js          # 推荐/邀请抓取
```

## 安装要求

- Python 3.8+
- Node.js 18+（Cookie 自动提取用）
- Edge 浏览器（读取登录态）

无需注册任何第三方 API，无需付费。

## 注意事项

- Cookie、数据库均仅本地保存，不上传任何地方；不要在仓库中提交 `config/fallback-sources.json` 里的真实 Cookie。
- 遵守平台限流与条款，采集行为仅限当前账号本来可查看的公开数据。
- 本技能不做发布动作；如需发布到草稿，见 `zhihu-auto-publish`。
