---
name: medical-entity-extraction
description: 医疗实体抽取：从非结构化患者消息或文本中抽取症状、用药、化验值、诊断、生命体征与待办事项，输出结构化 JSON。触发场景：批量结构化患者文本、消息分诊、把患者消息转成结构化数据。
author: Soulmate Agent团队成员：岸
---

# 医疗实体抽取

## 适用场景

从非结构化患者消息/文本中抽取结构化医疗信息：症状、用药、化验值、诊断、时间、待办事项。

## 步骤

1. 准备输入消息数组（JSON）。
2. 调用技能：
   ```bash
   openclaw skill run medical-entity-extraction --input '[{"id":"msg-1","priority_score":78,...}]' --json
   ```
   或程序化调用（`execFileAsync('openclaw', ['skill','run','medical-entity-extraction','--input', JSON.stringify(scoredMessages), '--json'])`）。
3. 按实体类型抽取并输出结构化 JSON。

## 输入输出

- 输入格式：
  ```json
  [{"id":"msg-123","priority_score":78,"priority_bucket":"P1","subject":"Medication side effects","from":"patient@example.com","date":"2026-02-27T10:30:00Z","body":"I've been feeling dizzy since starting the new blood pressure medication (Lisinopril 10mg) three days ago. My BP this morning was 145/92."}]
  ```
- 输出格式：
  ```json
  [{"id":"msg-123","entities":{"symptoms":[{"name":"dizziness","severity":"moderate","duration":"3 days","onset":"since starting new medication"}],"medications":[{"name":"Lisinopril","dosage":"10mg","frequency":null,"context":"new medication"}],"lab_values":[{"type":"blood_pressure","value":"145/92","unit":"mmHg","timestamp":"this morning"}],"diagnoses":[{"name":"hypertension","context":"implied by blood pressure medication"}],"action_items":[{"type":"medication_review","reason":"possible side effect (dizziness)"}]},"summary":"Patient reports dizziness after starting Lisinopril 10mg 3 days ago. BP elevated at 145/92. Possible medication side effect requiring review."}]
  ```
- 实体类型与字段：
  - Symptoms：name、severity（mild/moderate/severe）、duration、onset、progression（improving/stable/worsening）
  - Medications：name、dosage、frequency、route、context（new/existing/stopped）
  - Lab Values：type（BP/glucose/cholesterol…）、value、unit、timestamp、normal range
  - Diagnoses：name、context（confirmed/suspected/ruled out）
  - Vital Signs：体温、心率、呼吸频率、血氧、血压
  - Action Items：type（appointment/refill/question/callback）、urgency、reason

## 注意事项

- 术语处理：识别常见缩写（BP、HR、RR、O2 sat 等）、商品名与通用名、口语化病名（"sugar"→diabetes、"heart attack"→MI）、时间表达（"since yesterday"、"for the past week"）。
- 推荐模型：Claude Sonnet 4.5（`openclaw models set anthropic/claude-sonnet-4-5`）；未验证。
- 隐私：处理在本地经 OpenClaw 完成；除 LLM 处理外不外发第三方服务；抽取结果留在本地环境。

## 可复用示例

输入 `[{"id":"msg-1","body":"cough for the past week, took ibuprofen 200mg twice a day"}]` →
输出 symptoms: `{name:"cough", duration:"the past week"}`；medications: `{name:"ibuprofen", dosage:"200mg", frequency:"twice a day"}`；action_items 视上下文生成。
