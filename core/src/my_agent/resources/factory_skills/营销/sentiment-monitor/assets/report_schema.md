# 舆情报告数据结构规范

## JSON Schema

```json
{
  "report_meta": {
    "keyword": "监控关键词",
    "generated_at": "2026-03-30T12:00:00+08:00",
    "time_range": "2026-03-23 ~ 2026-03-30",
    "total_items": 45,
    "platforms_covered": ["微博", "腾讯新闻", "网易新闻", "知乎", "B站", "今日头条", "搜狐", "新浪", "澎湃新闻", "抖音"],
    "sentiment_summary": {
      "positive": 20,
      "negative": 15,
      "neutral": 10,
      "mixed": 0,
      "overall_sentiment": "偏正面",
      "sentiment_score": 0.65,
      "risk_level": "低风险",
      "hot_index": 85,
      "overview": "本期舆情整体偏正面，共监控到45条内容..."
    }
  },
  "items": [
    {
      "id": 1,
      "title": "文章/帖子标题",
      "url": "https://example.com/article/123",
      "source": "平台名称",
      "source_type": "social|news|community|video|official",
      "author": "作者/发布者（可选）",
      "published_at": "2026-03-28",
      "sentiment": "positive|negative|neutral|mixed",
      "sentiment_score": 0.85,
      "summary": "200字以内的内容摘要",
      "key_points": ["要点1", "要点2"],
      "risk_level": "high|medium|low|none",
      "engagement": {
        "views": 100000,
        "likes": 5000,
        "comments": 800,
        "shares": 200
      },
      "tags": ["标签1", "标签2"]
    }
  ],
  "risk_alerts": [
    {
      "level": "high|medium|low",
      "title": "风险标题",
      "description": "风险描述",
      "related_items": [1, 3, 7],
      "recommendation": "应对建议"
    }
  ],
  "risk_analysis": {
    "level": "低风险|中风险|高风险",
    "factors": ["风险因素1", "风险因素2"],
    "suggestions": ["建议1", "建议2"]
  },
  "trend_analysis": {
    "overall_sentiment": "mixed|positive|negative",
    "sentiment_trend": "improving|stable|declining",
    "hot_topics": ["热点话题1", "热点话题2"],
    "key_findings": ["核心发现1", "核心发现2"],
    "recommendations": ["建议1", "建议2"]
  },
  "platform_breakdown": [
    {
      "platform": "微博",
      "count": 8,
      "positive": 3,
      "negative": 4,
      "neutral": 1,
      "top_topic": "该平台最热话题"
    }
  ],
  "hot_topics": [
    {
      "title": "热门话题标题",
      "heat": 9500,
      "sentiment": "正面",
      "sentiment_en": "positive",
      "source": "微博",
      "url": "https://...",
      "risk_level": "low"
    }
  ],
  "timeline": [
    {
      "date": "2026-03-28",
      "positive": 5,
      "negative": 3,
      "neutral": 2,
      "total": 10
    }
  ],
  "keywords_cloud": [
    { "word": "关键词", "weight": 100 }
  ],
  "sentiment_articles": {
    "positive": [{"title":"...","source":"...","url":"...","summary":"...","date":"...","sentiment":"positive","risk_level":"low","tags":[]}],
    "negative": [{"title":"...","source":"...","url":"...","summary":"...","date":"...","sentiment":"negative","risk_level":"high","tags":[]}],
    "neutral":  [{"title":"...","source":"...","url":"...","summary":"...","date":"...","sentiment":"neutral","risk_level":"none","tags":[]}],
    "mixed":    [{"title":"...","source":"...","url":"...","summary":"...","date":"...","sentiment":"mixed","risk_level":"medium","tags":[]}]
  },
  "opinion_leaders": [
    {
      "name": "KOL名称",
      "platform": "微博",
      "influence": 90,
      "stance": "正面",
      "stance_en": "positive",
      "summary": "该KOL的核心观点摘要"
    }
  ]
}
```

## 字段说明

### report_meta
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | ✅ | 监控的核心关键词 |
| generated_at | string | ✅ | 报告生成时间 ISO 8601 |
| time_range | string | ✅ | 数据覆盖时间范围 |
| total_items | number | ✅ | 舆情条目总数 |
| platforms_covered | array | ✅ | 覆盖的平台列表 |
| sentiment_summary | object | ✅ | 情感分布汇总 |

### items
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | number | ✅ | 唯一编号 |
| title | string | ✅ | 标题 |
| url | string | ✅ | 原始链接 |
| source | string | ✅ | 来源平台 |
| source_type | string | ✅ | 来源类型 |
| sentiment | string | ✅ | 情感倾向 |
| sentiment_score | number | ❌ | 情感得分 0-1 |
| summary | string | ✅ | 内容摘要 |
| key_points | array | ❌ | 关键要点 |
| risk_level | string | ❌ | 风险等级 |
| tags | array | ❌ | 分类标签 |

### risk_alerts
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| level | string | ✅ | 风险等级 |
| title | string | ✅ | 风险标题 |
| description | string | ✅ | 详细描述 |
| recommendation | string | ✅ | 应对建议 |

## 数据质量要求

1. **最低条目数**: 30 条（推荐 40-60 条）
2. **平台覆盖**: 至少 8 个平台
3. **情感标注**: 每条必须标注 sentiment
4. **内容摘要**: 每条 summary 不少于 50 字
5. **去重**: 相同内容不同平台只保留最详尽版本
6. **时效性**: 优先最近 7 天内容
