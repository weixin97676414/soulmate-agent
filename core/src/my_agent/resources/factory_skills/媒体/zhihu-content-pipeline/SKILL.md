---
name: zhihu-content-pipeline
description: 知乎内容创作全流程编排与看板：把选题抓取 → 关键词筛选 → 内容生成 → 本地审阅 → 一键存草稿 → 数据看板串成回答/文章两条工作流，并生成可视化 dashboard.html。触发：知乎回答工作流、知乎文章工作流、批量写知乎、刷新知乎数据、发布到草稿、知乎内容看板、内容创作流程编排、知乎创作数据看板。
author: Soulmate Agent团队成员：岸
---

# 知乎内容创作全流程助手（编排 + 看板）

一句话：从知乎热榜抓选题 → 生成内容 → Dashboard 审阅 → 一键发布到草稿箱（手动审核后发布）。

> ⚠️ **依赖说明**：本技能**只保留可自包含的看板生成与流程编排说明**，`setup.py` 未收录。数据抓取/写稿/发布请使用同族的 `zhihu-topic-selection`、`zhihu-answer-writing`、`zhihu-auto-publish`。

## 两条工作流

### 回答工作流

选题抓取 → 关键词筛选 → 生成 5 篇回答 → 本地保存 → Dashboard 勾选 → 一键发布草稿。

- 输入示例：`开始知乎回答工作流，领域关键词：文献检索、论文下载、外文文献`
- 默认：选题 5 个；回答字数 300-600 字；关键词可组合（AND/OR）。

### 文章工作流

数据抓取 → 热点分析 → 归纳 5 个选题 → 用户确认 1 个 → 生成文章 → Dashboard 勾选 → 发布草稿。

- 输入示例：`开始知乎文章工作流`
- 默认：文章方向 5 个；文章字数 800-1100 字；写作风格（口语化程度、是否用小标题）在写作框架阶段可调。

## 快速开始

```bash
# 生成看板（读取 JSON 数据文件）
python scripts/generate_dashboard.py --mode answer --date 2026-07-01 --data data.json --output dashboard.html
python scripts/generate_dashboard.py --mode both --date 2026-07-01 --data data.json
```

参数：

| 参数 | 说明 |
|------|------|
| `--output` | 输出文件路径，默认 `dashboard.html` |
| `--mode` | `answer` \| `article` \| `both` |
| `--date` | 日期 `YYYY-MM-DD` |
| `--data` | JSON 数据文件路径（含 `answer` 与 `article` 两段） |

数据文件结构（供看板渲染）：

```json
{
  "answer": {
    "stats": {"recommend": 100, "invited": 100, "hot": 30, "matched": 0, "selected": 0},
    "questions": [
      {"title": "...", "url": "...", "view_count": 0, "follower_count": 0,
       "answer_count": 0, "source": "recommend", "answer_preview": "..."}
    ]
  },
  "article": {
    "stats": {"directions": 0, "written": 0, "backup": 0, "words": 0},
    "articles": [
      {"id": "1", "title": "...", "tags": "...", "date": "2026-07-01",
       "draft_url": "...", "body_html": "..."}
    ],
    "backup_topics": [{"title": "...", "source": "..."}]
  }
}
```

看板特性：日期筛选、历史数据查阅、热榜/推荐/邀请数据展示、回答/文章预览与勾选、一键发布状态展示。

## 知识库管理

`references/knowledge_base_template.md` 是持久化领域知识库模板，写作时自动加载。包含：核心观点、产品/服务介绍、常见回答要点、写作风格偏好、禁止事项。

- 复制模板为你的知识库文件后填写。
- **请勿填写账号、密码、密钥等敏感信息**；写作时临时上传的参考资料不保留。
- 切换创作领域：备份当前知识库，复制模板为新的知识库再填充。

## 去 AI 味检查规则

发布前应扫描内容，命中以下规则时处理：

| 检查项 | 风险 | 触发条件 | 处理 |
|--------|------|---------|------|
| 编号分层 | HIGH | 出现「第一层/第二层」等 | 改用自然叙述 |
| 序号列举 | HIGH | 「首先…其次…最后」结构 | 用「然后/还有/另外」 |
| AI 高频词 | HIGH | 「此外/确保/强调/关键/总之」 | 删除或用口语替代 |
| 总结收尾 | HIGH | 「总之/综上所述」开头 | 直接结束或用「反正」 |
| 夸张用词 | MEDIUM | 「颠覆/震撼/革命性/绝了」 | 用克制表达 |
| 缺少口语 | LOW | 口语词 <2 个 | 增加「说实话/对吧」等 |

检测到 HIGH 级别风险应阻止发布。

## 注意事项

1. **Cookie 有效期**：知乎 Cookie 一般 7-30 天有效，过期后需重新登录提取（由选题/发布技能负责）。
2. **发布间隔**：发布时建议设置 120 秒间隔，模拟真人间隔，避免触发风控。
3. **文章发布频率**：建议每天不超过 1 篇。
4. **草稿审核**：所有内容仅保存为草稿，需用户在知乎后台手动审核发布。
5. **看板数据**：先生成数据文件，再看板支持日期筛选查看历史记录。

## 安全原则

- 只保存草稿，不自动发布。
- Cookie 仅本地存储。
- 每篇发布间隔 ≥90 秒防审核。
- 用户手动审核后最终发布。

## 参考文件

- `references/workflow_guide.md` — 工作流详细指南、自定义项、发布命令示例、去 AI 味检查规则。
- `references/knowledge_base_template.md` — 领域知识库模板。
- `scripts/generate_dashboard.py` — 看板生成器（自包含，读取 JSON 数据渲染 `assets/dashboard_template.html`）。
- `assets/dashboard_template.html` — 看板 HTML 模板。
