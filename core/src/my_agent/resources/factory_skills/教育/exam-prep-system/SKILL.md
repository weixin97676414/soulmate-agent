---
name: exam-prep-system
description: "备考体系生成：从学习材料生成题库、闪卡、限时模拟考、缺口分析、学习计划、章节总结、概念图与速查表，并按主题追踪表现。用于备考、复习计划、模拟考、闪卡、薄弱点分析等场景。"
author: Soulmate Agent团队成员：岸
---

# 功能：备考练习系统

**定位**：备考体系——题库 / 闪卡 / 限时模拟考 / 缺口分析 / 学习计划。

## 适用场景

- 从任意学习材料生成完整备考体系：练习题、闪卡、模拟考、缺口分析、学习计划、总结、概念图、速查表。
- 适用于大学考试、认证考试（AWS、PMP 等）、标准化考试、职业执照考试。
- 用户说「从材料出题」「考我」「开始限时模拟」「看我的薄弱点」「做闪卡」「排学习计划」。

触发词：备考、复习计划、模拟考、闪卡、错题复盘、薄弱点分析、考点总结、概念图。

## 步骤（核心工作流）

1. **提供来源材料**：笔记、教材章节、幻灯片、文档、历年真题。
2. **按难度生成题目**：
   - **Easy**：回忆、定义、基本概念。
   - **Medium**：应用、比较、分析。
   - **Hard**：综合、边界情况、多步推理。
3. **练习并追踪**：用户作答，系统判分并按主题记录表现。
4. **聚焦薄弱点**：识别缺口，生成针对性练习。

## 快速参考（细分资源）

| 任务 | 加载 |
|------|------|
| 题目生成模式 | `assets/questions.md` |
| 闪卡格式与策略 | `assets/flashcards.md` |
| 限时模拟设置 | `assets/simulations.md` |
| 表现追踪 | `assets/tracking.md` |

## 题型

| 类型 | 格式 | 适用 |
|------|------|------|
| 单选 | 4 选项 1 正确 | 快速评估、认证 |
| 多选 | N 选项 M 正确 | 复杂主题 |
| 判断 | 语句 + T/F | 快速复习 |
| 简答 | 1–3 句 | 定义、解释 |
| 填空 | 句中留 ___ | 术语 |
| 匹配 | 配对 | 关系 |
| 论述 | 开放作答 | 深入理解 |

## 练习会话示例

```
📝 Practice: AWS S3 (10 questions)

Q1/10 [Medium]
Which S3 storage class has the lowest cost for infrequently accessed data with millisecond retrieval?

A) S3 Standard
B) S3 Intelligent-Tiering
C) S3 Standard-IA ✓
D) S3 Glacier

Your answer: _
```

答后反馈：`✅ Correct!` + 解析（含为什么不选其他），并提供 `[Next] [Skip] [End session]`。

## 存储结构

```
~/exams/
├── {subject}/
│   ├── questions.jsonl    # 题库
│   ├── sessions.jsonl     # 练习历史
│   ├── performance.json   # 按主题的统计
│   └── flashcards.json    # 生成的卡片
```

## 输入输出

- **输入**：学习材料 + 考试日期 / 可用时间等；或指定主题、难度、题量。
- **输出**：题目 / 闪卡 / 模拟考 / 缺口分析 / 学习计划 / 章节总结 / 概念图 / 速查表；练习记录与表现统计。
- **脚本**：无（数据以本地文件存储）。

## 常用指令

```
"Generate 20 questions from [material]"
"Quiz me on [topic]"
"Start a timed simulation (50 questions, 60 minutes)"
"Show my weak areas"
"Create flashcards for [topic]"
"Review mistakes from last session"
"Grade my essay answer and suggest improvements"
"Create a study schedule — exam in 2 weeks, 3 hours/day available"
"Summarize chapter 5 focusing on what's likely to be on the exam"
"Make a concept map for [topic]"
"Generate a 1-page quick review sheet for [subject]"
```

## 注意事项

1. 题目与解析必须来自所给材料，不编造；材料未覆盖的标「未验证」。
2. 学习计划要按考试日期与每日可用时间生成，量力而行。
3. 定时提醒（如「每天 7 点提醒我学习」）走宿主定时 / 调度能力，不另造系统。

## 可复用示例

**输入**：`Create a study schedule — exam in 2 weeks, 3 hours/day available`。

**输出要点**：按 14 天排期，每天 3 小时，先覆盖高频 / 高权重主题，穿插模考与错题复盘，标注每日目标与检验方式；薄弱主题由 `performance.json` 统计驱动。
