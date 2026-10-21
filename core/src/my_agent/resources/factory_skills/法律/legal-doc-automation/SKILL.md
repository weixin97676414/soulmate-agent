---
name: legal-doc-automation
description: 英文法务文档自动化：英文合同条款提取、文档摘要、引证核查、期限管理（诉讼时效/合同里程碑）。触发场景：批量处理英文合同，提取赔偿/责任限制等条款，管理诉讼时效与合同里程碑。
author: Soulmate Agent团队成员：岸
---

# 法务文档自动化（条款提取 / 摘要 / 引证核查 / 期限管理）

## 适用场景

- 批量处理英文合同/法律文档：提取特定条款、生成执行摘要、做文档对比。
- 需要核查引证、查找判例/法规，或管理法定期限（诉讼时效、申报期限、合同里程碑）。

## 步骤

本功能的可执行部分是 `scripts/nathan/` 下的脚本（Python），统一入口 `legaldoc.py` 分发到子脚本：

```bash
python3 scripts/nathan/legaldoc.py extract clauses <file> [--type indemnification,liability] [--output json|markdown|table]
python3 scripts/nathan/legaldoc.py summarize <file> [--type executive|detailed|bullet]
python3 scripts/nathan/legaldoc.py research "<query>" [--jurisdiction CA|NY|TX|federal] [--type case_law|statute|regulation]
python3 scripts/nathan/legaldoc.py deadlines list --upcoming 30d
python3 scripts/nathan/legaldoc.py deadlines extract <file> --save
python3 scripts/nathan/legaldoc.py deadlines sol 2024-01-15 personal_injury
python3 scripts/nathan/legaldoc.py compare <file1> <file2> [--type redline|summary|clause-by-clause]
```

（命令依据 `scripts/nathan/legaldoc.py` 的 CLI 定义整理；**未实测运行**，以脚本实际输出为准。）

1. **条款提取**：识别 12+ 类英文合同条款（赔偿、责任限制、终止、不可抗力、保密、竞业、知识产权转让、管辖、争议解决、付款、陈述与保证、控制权变更），定位章节/页码并标注风险等级与修改建议。
2. **文档摘要**：输出执行摘要，突出关键条款与风险等级。
3. **法律研究**：判例/法规检索与引证核查（需相应外部 API 时才完整可用，见下）。
4. **期限管理**：提取/跟踪诉讼时效、申报期限、开庭日期、合同里程碑，支持提前多轮提醒。

## 输入输出

- 输入：英文法律文档（PDF/Word/文本/RTF/HTML/Markdown）、查询语句、日期与期限类型。
- 输出：条款清单（JSON/Markdown/表格，含风险等级与建议）、执行摘要、检索结果、期限清单与提醒。

## 注意事项

- **能力边界**：源包文档宣传的是托管在线服务与 `legaldoc` CLI、`LEGALDOC_API_KEY`/`WESTLAW_API_KEY`/`LEXIS_API_KEY`/`CLIO_API_KEY` 等环境变量与计费档位，**但包内只提供 `scripts/nathan/` 下的本地 Python 脚本**，托管 CLI 与环境变量所对应的服务并未随包交付。这些属宣传内容，实际以本地脚本为准。
- 条款提取结果必须回原文核对；AI 建议在纳入最终文档前需人工复核。
- 本技能的条款提取面向英文合同；中文合同审查不在本技能范围。
- 期限管理属高风险事项，提醒仅为辅助，须以正式日程与人工复核为准。
- 本工具不提供法律意见。

## 可复用示例

用户：「把这份英文 MSA 里的赔偿和责任限制条款提取出来。」
处理：运行 `legaldoc.py extract clauses <file> --type indemnification,liability` → 输出条款文本、章节/页码、风险等级与修改建议 → 提醒回原文核对。

用户：「这份合同有哪些关键期限？」
处理：运行 `deadlines extract <file> --save`，列出付款、续约通知、年审等里程碑，并设置提前提醒。

## 关联资产

- `scripts/nathan/legaldoc.py`、`clause_extractor.py`、`document_summarizer.py`、`legal_research.py`、`deadline_tracker.py`
- `assets/nathan-config.yaml`（配置样例）、`assets/nathan-sample-contract.txt`（示例合同）
