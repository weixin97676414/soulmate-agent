---
name: log-analysis
description: 用 grep/awk/jq 与堆栈解析检索分析应用日志：按请求 ID/时间窗过滤、JSON 结构化日志查询、访问日志解析、跨服务关联、实时监控与错误频次报告。触发场景：从日志排障、按 requestId 追踪、解析堆栈、访问日志分析、生成错误报告。
author: Soulmate Agent团队成员：岸
---

# 功能：日志分析与排障

依赖 `grep`/`awk`/`jq`/`python3`。

## 适用场景
从日志文件排障、按模式/错误/请求 ID 检索、解析堆栈、设置结构化（JSON）日志、跨服务关联事件、实时监控日志、生成错误频次报告。

## 步骤

1. **先找请求 ID / 关联 ID**，再按时间窗口过滤——比直接用时间或错误消息更快缩小范围。
2. **常见检索**：
   ```bash
   grep -i 'error\|exception\|fatal\|panic\|fail' app.log
   grep -i -C 3 'error\|exception' app.log
   grep -oP '(?:Error|Exception): \K[^\n]+' app.log | sort | uniq -c | sort -rn | head -20
   awk '$9 >= 500' access.log                       # HTTP 5xx
   grep -rH 'correlation-id-xyz' /var/log/service-a/ /var/log/service-b/
   ```
3. **时间范围过滤**：
   ```bash
   awk '$0 >= "2026-02-03T10:00" && $0 <= "2026-02-03T11:00"' app.log
   tail -1000 app.log | grep -i error
   awk -v start="$(date -d '30 minutes ago' '+%Y-%m-%dT%H:%M')" '$1 >= start' app.log
   ```
4. **JSON/结构化日志用 jq**：
   ```bash
   cat app.log | jq 'select(.level == "error")'
   cat app.log | jq -r '[.timestamp, .level, .message] | @tsv'
   cat app.log | jq -r '.level' | sort | uniq -c | sort -rn
   cat app.log | jq 'select(.context.userId == "user-123")'
   ```
5. **堆栈解析**：按语言提取并去重（Java `\tat`、Python `Traceback`、Node 缩进 `at`），按根因首行分组统计。Python 可用 `extract_tracebacks` 思路实现。
6. **实时监控**：
   ```bash
   tail -f app.log | grep --line-buffered -i 'error\|exception'
   tail -f /var/log/service-a/app.log /var/log/service-b/app.log
   ```
7. **访问日志解析**（Apache/Nginx）：`awk '{print $1, $9, $7}' access.log`、TOP IP/路径、状态码分布、慢请求（末字段微秒 >1000000）。
8. **跨服务关联**：合并多文件按时间排序 `sort -t'T' -k1,1 service-*.log > merged.log`；JSON 日志加 `source` 字段并 `sort_by(.timestamp)`。
9. **生成错误报告**：统计总行/错误/警告数、TOP 15 错误消息、每小时错误数、各错误类型首次出现。

## 输入输出
- 输入：日志文件（纯文本/JSON/访问日志/多服务）。
- 输出：检索结果、错误频次报告、关联时间线、实时监控管道。

## 注意事项
- `tail -f | grep` 务必加 `--line-buffered`，否则输出被缓冲延迟。
- 分组前先归一化 ID/数字（`sed 's/[0-9a-f]\{8,\}/ID/g'`），否则仅 ID 不同的重复项无法合并。
- 大数据文件用 `awk` 做计数/聚合比 `grep | sort | uniq -c` 管道更快。
- 生产排障：先拿**时间窗口**和**受影响用户/请求 ID**，过滤到该范围再看内容。
- 建议长期采用结构化（JSON）日志；Node 用 pino、Python 用 structlog、Go 用 zerolog。
- 轮转/压缩日志用 `zgrep`/`zcat`；超大文件可采样（`shuf -n 1000`、每 100 行取 1、首尾各 500 行）。

## 可复用示例
```bash
# 复盘一次线上 500：先锁定时间窗与请求ID，再看该请求全链路
REQUEST_ID="req-abc-123"
for f in /var/log/services/*.log; do
  jq --arg rid "$REQUEST_ID" 'select(.requestId == $rid) | {timestamp, level, message}' "$f" 2>/dev/null
done | jq -s 'sort_by(.timestamp)[]'
```
