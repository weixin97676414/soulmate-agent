---
name: code-analysis
description: 深度分析陌生代码库：架构风格、执行流程、数据流、业务规则、外部依赖、质量评分与 DDD 模式识别（聚合根/实体/值对象/限界上下文），输出 Markdown 报告。触发场景：接手陌生代码库、生成架构文档、代码审查准备、技术债评估、DDD 模式识别。
author: Soulmate Agent团队成员：岸
---

# 功能：深度代码分析

脚本位于 `scripts/code-analyzer/`（`analyze.py`、`ddd-analyzer.py`），方法论见 `assets/code-analyzer-best-practices.md`。

## 适用场景
新代码库熟悉、架构文档生成、代码审查准备、技术债务评估、知识传承、DDD 模式识别（聚合根/实体/值对象/领域服务/仓储/领域事件/限界上下文）。支持 Python、JavaScript、TypeScript、Rust、Java、Go 等 20+ 语言。

## 步骤

1. **完整深度分析**：
   ```bash
   python3 scripts/code-analyzer/analyze.py --path /path/to/project --output report.md
   ```
2. **DDD 专项分析**：
   ```bash
   python3 scripts/code-analyzer/ddd-analyzer.py --path /path/to/project --output ddd-report.md
   ```
3. **排除目录**：
   ```bash
   python3 scripts/code-analyzer/analyze.py --path . --exclude "node_modules,vendor,target" --output analysis.md
   ```
4. **按场景选用**（把输出交给 AI 解读并回答具体问题）：
   - 新项目熟悉 → `onboarding.md`
   - 架构文档生成 → `architecture.md`
   - 代码审查准备 → `pr-analysis.md`
   - 技术债务评估 → `debt-review.md`（`--exclude "tests"`）
   - DDD 模式识别 → `ddd-analysis.md`

## 分析维度
- 架构风格（MVC、Clean Architecture、微服务等）、执行流程（入口点、调用图、执行路径）、数据流动、业务规则、外部依赖（API/DB/第三方）、数据模型、DDD 模式。
- 质量维度：可维护性、可测试性、文档完整性、复杂度。
- 报告结构：执行摘要、质量评分、分级问题清单、按优先级改进建议、Mermaid 架构图。

## 输入输出
- 输入：项目路径（+ 排除目录 + 输出路径）。
- 输出：Markdown 分析报告（含质量指标表、问题分级、架构图）。

## 注意事项
- 不同语言分析深度不同：Python/JS/TS/Rust 为深度（AST 级），Java/Go 中等，C/C++ 为基础。
- 分析结果需结合人工/AI 解读，不要直接把评分当结论。
- 排除 `node_modules`、`vendor`、`target`、`tests` 等目录以免噪声（视场景）。

## 可复用示例
```bash
# 接手陌生仓库：先生成总览与 DDD 视角，再让 AI 回答关键问题
python3 scripts/code-analyzer/analyze.py --path . --exclude "node_modules,vendor,target,dist" --output onboarding.md
python3 scripts/code-analyzer/ddd-analyzer.py --path . --output ddd-analysis.md
# 提问：1) 主要入口点？2) 核心数据模型？3) 编码了哪些业务规则？4) 数据如何流动？
```
