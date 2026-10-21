---
name: exam-paper-generation
description: "K12 成品卷生成：为中国中小学九大学科按知识点、题型、难度、题量组卷，对齐课标并多源交叉验证答案，导出可打印试卷 Word 与参考答案。用于生成试卷、出题、组卷、出数学题或英语试卷等场景。"
author: Soulmate Agent团队成员：岸
---

# 功能：中小学试卷生成

**定位**：K12 成品卷——课标对齐 + Word 排版 + 难度 / 题量配比。

## 适用场景

- 为中国中小学各学科生成试卷（语文、数学、英语、物理、化学、生物、历史、地理、政治）。
- 按知识点、题型、难度、题量生成，遵循官方课程标准，输出标准排版、可直接打印。
- 需要配套参考答案。
- 用户说「生成一份试卷」「出一套数学题」「帮我出英语试卷」「根据知识点出题」「exam-generator」。

触发词：生成试卷、出题、考试卷、组卷、出数学题、出英语试卷。

## 支持范围

| 学科 | 年级 | 题型 |
|------|------|------|
| 语文 | 小学/初中 | 选择、填空、阅读、作文 |
| 数学 | 小学/初中 | 选择、填空、计算、应用 |
| 英语 | 小学/初中 | 选择、填空、阅读、写作 |
| 物理 | 初中 | 选择、填空、实验、计算 |
| 化学 | 初中 | 选择、填空、实验、计算 |
| 生物 | 初中 | 选择、填空、简答 |
| 历史 | 初中 | 选择、填空、简答 |
| 地理 | 初中 | 选择、填空、读图 |
| 政治 | 初中 | 选择、填空、简答 |

题型全集：选择题、填空题、判断题、简答题、计算题、作文题。

## 步骤

1. **理解需求**：确认学科、年级、知识点、题型、题量、难度（简单/中等/困难）、考试时长。
2. **联网验证知识**：用联网搜索取得知识点、标准答案、官方课程标准，走「生成试题 → 搜索标准答案 → 交叉验证 → 标记置信度 → 输出」的流程。
3. **生成试卷**：按标准试卷格式排版（题头：试卷名 / 学科·年级 / 考试时间·满分；学生信息栏：姓名/班级/学号；按题型分大题）。
4. **生成答案**：输出参考答案页，与试题分文件。
5. **导出**：可用 python-docx 导出 `exam.docx` 与 `answer.docx`。

## 试卷格式标准

```
┌─────────────────────────────────────────────────────────┐
│  2026年春季期中考试                                      │
│  数学 · 初中一年级                                       │
│  考试时间：90分钟 · 满分：100分                          │
└─────────────────────────────────────────────────────────┘

姓名：__________ 班级：__________ 学号：__________

一、选择题（每题2分，共20分）
1. 下列哪个是质数？
   A. 4    B. 6    C. 7    D. 9

二、填空题（每题2分，共20分）
1. 12的平方根是__________

三、计算题（共60分）
1. 解方程：2x + 5 = 13（10分）
```

## 输入输出

- **输入**：学科、年级、知识点、题型、题量、难度、考试时长。
- **输出**：试卷文本 / 试卷 Word（`exam.docx`）+ 参考答案（`answer.docx`）。
- **依赖**：`python3`、`curl`（联网验证）；导出 Word 需 `python-docx`。

## 试题准确性保证

- 生成后搜索标准答案并**多源交叉验证**，按置信度标记：✅ 高（多源一致）、⚠️ 中（单源）、❌ 低（需人工确认）。
- 低置信度题目必须标注，不得冒充高置信度。

## 可复用示例

核心生成代码（`ExamGenerator` 类，摘录关键方法）：

```python
from datetime import datetime

class ExamGenerator:
    def __init__(self, subject, grade, title='考试试卷'):
        self.subject, self.grade, self.title = subject, grade, title
        self.questions, self.answers = [], []

    def add_choice_question(self, question, options, answer, score=2):
        self.questions.append({'type': 'choice', 'question': question,
                               'options': options, 'score': score})
        self.answers.append({'type': 'choice', 'answer': answer, 'score': score})

    def add_fill_blank(self, question, answer, score=2):
        self.questions.append({'type': 'fill', 'question': question, 'score': score})
        self.answers.append({'type': 'fill', 'answer': answer, 'score': score})

    def add_true_false(self, question, answer, score=1):
        self.questions.append({'type': 'true_false', 'question': question, 'score': score})
        self.answers.append({'type': 'true_false', 'answer': answer, 'score': score})

    def add_calculation(self, question, answer, score=15):
        self.questions.append({'type': 'calculation', 'question': question, 'score': score})
        self.answers.append({'type': 'calculation', 'answer': answer, 'score': score})

    def add_essay(self, question, requirements, score=30):
        self.questions.append({'type': 'essay', 'question': question,
                               'requirements': requirements, 'score': score})
        self.answers.append({'type': 'essay', 'answer': '见评分标准', 'score': score})
```

用法：

```python
exam = ExamGenerator('数学', '初中一年级', '2026年春季期中考试')
exam.add_choice_question('下列哪个是质数？', ['4', '6', '7', '9'], 'C', 2)
exam.add_fill_blank('12的平方根是____', '±2√3', 2)
exam.add_true_false('0是最小的自然数', '×', 1)
exam.add_calculation('计算：2x + 5 = 13，求x的值', 'x = 4', 10)
exam.save('/path/to/output')   # 导出 exam.docx 与 answer.docx
```

## 注意事项

1. 答案必须交叉验证后再输出；无法验证的标 ⚠️/❌。
2. 支持中英文输出；Word 导出依赖 `python-docx`。
3. 试卷满分由各题分值汇总得出，题头「满分」应与实际一致。
4. 联网搜索不可用时，改用宿主的搜索能力并说明来源，不凭记忆编标准答案。
