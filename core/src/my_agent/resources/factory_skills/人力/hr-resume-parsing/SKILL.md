---
name: hr-resume-parsing
description: 简历结构化解析：把简历纯文本解析为标准化 JSON（basic_info、education、work_experience、projects、skills、certificates、awards、self_assessment），用于字段对齐、入库与后续匹配打分。触发场景：结构化简历、解析简历字段、导出结构化简历、简历入库。
author: Soulmate Agent团队成员：岸
---

# 简历结构化信息提取（文本 → JSON）

## 适用场景

- 把简历文本转成可对比、可归档的结构化数据
- 多份候选人字段对齐、后续 JD 匹配打分的前置输入
- 需要统一 JSON 字段做二次处理（排序、导出、入库）

## 步骤

1. 先用 [hr-text-extraction](references/hr-text-extraction.md) 把简历转成纯文本。
2. 运行解析脚本：
   ```bash
   python scripts/parse_resume.py <extracted-text-file>
   ```
   脚本输出一段**结构化提示词**；实际 JSON 由当前会话模型按该提示词解析生成（脚本本身不调用任何外部模型）。
3. 模型按提示词返回标准 JSON，字段为：
   `basic_info` / `education[]` / `work_experience[]` / `projects[]` / `skills{}` / `certificates[]` / `awards[]` / `self_assessment`。
4. 逐字段核对：缺失留空或 `null`，不得编造。
5. 字段提取细则见 `assets/field_extraction_guide.md`（姓名/电话/邮箱/教育/工作/项目/技能的提取规则与优先级）。

## 输入输出

- 输入：简历纯文本文件
- 输出：结构化 JSON（可作为 [hr-jd-matching](references/hr-jd-matching.md) 的输入）

## 注意事项

- 所有信息必须完全来自简历原文，信息不确定时留空，不猜测。
- 日期统一为 `YYYY-MM`，只有年份时填 `YYYY`；「至今」的结束时间填「至今」。
- 技术栈、成果尽量拆成数组项，不要合并成大段文字。
- **已知限制**：`parse_resume.py` 只负责生成解析提示词，不是可独立跑出结果的引擎；解析质量取决于执行模型，字段提取需按 `field_extraction_guide.md` 复核。

## 可复用示例

```bash
python scripts/parse_resume.py /tmp/zhangsan.txt
# → 返回解析提示词，交由模型输出如下结构的 JSON：
{
  "basic_info": {"name": "张三", "phone": "", "email": "", "age": null, "gender": "", "location": "", "work_years": 4},
  "education": [{"school": "XX大学", "major": "计算机", "degree": "本科", "start_date": "2016-09", "end_date": "2020-06", "gpa": "", "courses": []}],
  "work_experience": [], "projects": [], "skills": {"technical": [], "soft": [], "languages": []},
  "certificates": [], "awards": [], "self_assessment": ""
}
```
