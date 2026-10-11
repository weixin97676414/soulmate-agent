---
name: quiz-generation
description: "通用出题引擎：从任意主题或材料生成多难度、多题型测验，含题干、答案、详细解析与答案速查，可输出 Markdown、JSON 或纯文本。用于出测验、考考我、生成题目、做练习等场景。"
author: Soulmate Agent团队成员：岸
---

# 功能：通用测验生成

**定位**：通用出题引擎——任意主题 / 材料，不限学段与教材。

## 适用场景

- 从任意主题或材料生成测验 / 评估题。
- 需要多难度（easy / medium / hard）、多题型（选择 / 判断 / 填空 / 简答 / 匹配），并带答案与详细解析。
- 用户要求「出一份测验」「考考我」「生成题目」「做一套练习」。

触发词：生成测验、出quiz、考考我、生成题目、做练习、quiz。

## 测验结构（必备要素）

1. **标题与说明**：清晰的标题、主题焦点、目标读者水平、预计完成时间、题目数量。
2. **题目**：每道题必须含题干、难度（easy/medium/hard）、题型、正确答案、详细解析，可选来源引用。
3. **答案速查**：末尾给出所有正确答案的快速索引。
4. **评分指南（可选）**：每题分值、多少分算掌握、按分数段的后续建议。

## 题型与难度

**题型**
- 多选（默认）：3–5 个选项，1 个正确，干扰项应为常见误解；选项标 A–E。
- 判断：待判语句 + 为什么对/错。
- 填空：句中留空；建议大小写不敏感，列出可接受的其他答案。
- 简答：开放题；给出示例可接受答案与应包含的关键点。
- 匹配：两列配对（术语↔定义、日期↔事件等），关系写清。

**难度**
- **Easy**：基本事实、定义、术语；通读材料一遍即可作答（例：API 全称是什么）。
- **Medium**：需理解概念、推断或应用，可能要串联多条信息（例：更新已有资源用哪个 HTTP 方法）。
- **Hard**：需综合、分析或批判性思考；复杂场景或边界情况；比较或评估选项（例：为实时聊天对比 REST 与 GraphQL）。

## 步骤

1. **读懂来源**：读主题或所给材料，识别关键概念、事实、关系，记下常见误区。
2. **规划分布**：目标 40% easy / 40% medium / 20% hard；按内容混合题型；覆盖所有关键主题。
3. **生成题目**：题干 + 答案 + 解析，逐条检查清晰与正确。
4. **复核精简**：删重复题、统一难度、核对答案、按需加一道练习题或加分题。
5. **按偏好格式输出**：Markdown（默认）/ JSON（程序或测验平台用）/ 纯文本。

## 编写准则

- 每题都要考有意义的东西；避免歧义措辞；题目相互独立（不依赖上题答案）；题型与难度均衡；综合测验 10–20 题。
- 解析不仅解释正确答案，还要说明其他选项为什么错；可引用来源、补充相关概念，帮助理解而非死记。
- 干扰项要合理，取自常见误解；避免「以上都对 / 都不对」这类靠猜的选项；干扰项长度与语气应接近正确答案。

## 输入输出

- **输入**：主题或材料；可选难度、题量、题型、输出格式、目标读者。
- **输出**：Markdown / JSON / 纯文本测验，含题干、难度、题型、答案、解析、答案速查。
- **脚本**：无。

## 输出格式示例（JSON）

```json
{
  "title": "Web Development Fundamentals Quiz",
  "description": "Test your knowledge of HTML, CSS, and JavaScript basics",
  "questions": [
    {
      "id": 1,
      "difficulty": "easy",
      "type": "multiple_choice",
      "question": "What does HTML stand for?",
      "options": [
        "Hyper Text Markup Language",
        "High Tech Modern Language",
        "Hyper Transfer Markup Language",
        "Home Tool Markup Language"
      ],
      "correct_answer": 0,
      "explanation": "HTML stands for Hyper Text Markup Language. It's the standard markup language for creating web pages."
    }
  ],
  "answer_key": {"1": "A"}
}
```

## 注意事项

1. 输出前逐项核对质量清单：题干清晰无歧义、答案准确、解析有帮助、难度适配读者、题型多样、覆盖关键主题、干扰项合理、标题说明信息完整、答案速查完整准确。
2. 不编造事实；材料未覆盖的事实不要当作考点。

## 可复用示例

**输入**：`为「环境变量在应用配置中的作用」出一份 10 题测验`

**示例题（Medium）**：

```markdown
### Question 3 (Medium)
What is the primary purpose of environment variables in application configuration?

A) To store sensitive credentials securely
B) To configure application behavior across environments
C) To manage database connections
D) To handle user authentication

**Correct Answer:** B

**Explanation:** Environment variables allow applications to be configured differently across development, testing, and production environments without changing code. While they can store credentials (A), their primary purpose is configuration flexibility. Database connections (C) and authentication (D) are specific use cases, not the primary purpose.
```
