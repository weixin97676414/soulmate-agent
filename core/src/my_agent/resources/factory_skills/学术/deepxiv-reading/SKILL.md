---
name: deepxiv-reading
description: 用 deepxiv CLI 对开放获取文献（arXiv/PMC/Semantic Scholar）做检索分诊、渐进式分节精读、热门论文追踪、引用与作者背景调查、baseline 对比。触发：讲论文、读论文、读某篇文献、找热门论文、文献综述、deepxiv。
author: Soulmate Agent团队成员：岸
---

# 论文渐进式阅读与热门追踪（deepxiv CLI）

## 适用场景

- 用 `deepxiv` 对开放获取文献（arXiv / PMC / Semantic Scholar）做检索、分诊、分节精读。
- 需要热门论文追踪、引用查询、作者背景调查、baseline 对比、文献综述。
- 目标是**用最少的阅读量回答当前问题**：只读到够用的那一层。

## 步骤

1. **确认可用**：`deepxiv --help`。缺失则**停止并告知用户**，不要自行安装；用户明确要求安装时按 `assets/deepxiv/install.md` 的按系统步骤执行（需用户显式批准）。需 Python 3.10+。
2. **按需检索**：`search`（带过滤）/ `trending`（热门）/ `wsearch`（非论文背景）。
3. **沿阅读阶梯推进**（见下表），停在能回答问题的最低层。
4. **作答时说明停在第几层**。

### 渐进式阅读阶梯（从便宜到贵）

| 层 | 命令 | 得到 | 何时用 |
|----|------|------|--------|
| 1 | `paper <id> --brief` | 标题、TLDR、关键词、引用数、GitHub | 初次分诊（首选） |
| 2 | `paper <id> --head` | 元数据 + 章节列表（JSON） | 决定读哪些章节 |
| 3 | `paper <id> --preview` | 前 ~10k 字符（引言+方法开头） | TLDR 不够、又不必读全节 |
| 4 | `paper <id> --section <Name>` | 单个命名章节 | 定向取答案（Method/Results 等） |
| 5 | `paper <id>` / `--raw` | 全文 markdown | 仅当明确需要全文 |

## 输入输出

- 输入：查询词（search/trending/wsearch）、论文 ID（paper/pmc/sc）。
- 输出：文本或 `--json` 结构化结果（可用 `jq` 处理）。

## 常用命令

```bash
# 检索（过滤可自由组合）
deepxiv search "agent memory" --limit 5
deepxiv search "retrieval" --categories cs.IR,cs.CL --date-from 2025-01-01 --min-citations 50
deepxiv search "chain of thought" --mode bm25      # 精确措辞
deepxiv search "models that can think..." --mode vector  # 模糊概念
deepxiv search "multimodal reasoning" --limit 10 --format json

# 阅读（逐层）
deepxiv paper 2409.05591 --brief
deepxiv paper 2409.05591 --head
deepxiv paper 2409.05591 --section Method
deepxiv paper 2409.05591 --popularity

# 其他来源 / 热门 / 网络 / 代理
deepxiv pmc PMC544940 --head
deepxiv sc 258001 --json
deepxiv trending --days 7 --limit 10 --json      # --days 仅支持 7/14/30
deepxiv wsearch "karpathy" --json
deepxiv agent query "Compare RAG vs long-context for code QA" --max-turn 10 --verbose

# 健康检查
deepxiv health
deepxiv debug
```

## 注意事项

- **不要直接跳第 5 层全文**，除非用户明确要求全文或任务确实需要。
- 章节名因论文而异，先用 `--head` 列出真实章节名再 `--section`，不要猜。
- 检索默认 `--limit 3~5` 分诊，最多 10；需要后处理时用 `--format json`。
- `agent query` 是多轮 LLM 研究代理：需用户先 `deepxiv agent config`，消耗用户 LLM 额度，较慢且不稳定——默认用手动 `search + paper`，仅在真正开放式多步问题且用户同意成本时使用。
- 遇到鉴权/限流：先 `deepxiv health`；被限流或未授权就如实说明并停止，不要静默重试。
- ID 格式：arXiv `2409.05591`、PMC `PMC544940`、Semantic Scholar `258001`；不确定来源时先 `wsearch`。
- Python 3.9 下可能装得上但首次运行崩溃，需切到 3.10+。

## 可复用示例

**主题探索**：`search "agent memory" --limit 5 --format json` → 逐个 `--brief` → 挑 1~2 篇深读。

**单篇讲解**：`--brief` → `--head` → 读 1~2 个最相关章节（或 `--preview`）→ 说明停在第几层。

**baseline 对比表**：按 `--categories`/`--min-citations` 收窄 → 全部 `--brief` → 只读入选者的 `Method`/`Experiments`/`Results` → 提取 论文/任务/数据集/指标/分数/关键思路。

**本周热门**：`trending --days 7 --limit 10 --json` → 对头部 `--brief` → 可选 `--popularity` → 输出 主题概览 → 每篇一行 → 哪些值得深读。

**JSON 后处理**

```bash
deepxiv trending --days 7 --limit 20 --json \
  | jq -r '.[] | select(.categories[]? | test("cs\\.(AI|CL|LG)")) | .arxiv_id'
```
