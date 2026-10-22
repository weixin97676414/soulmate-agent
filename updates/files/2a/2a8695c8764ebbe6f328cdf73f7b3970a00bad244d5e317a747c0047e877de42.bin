---
name: document-templates
description: 生活类法律文书模板库：提供劳务/婚姻家庭/交通/租房/消费等场景的文书模板与撰写指导、纠纷解决途径指引。触发场景：需要生活类文书模板，问「离婚协议/租房押金/劳动仲裁申请书怎么写」，问纠纷解决途径。
author: Soulmate Agent团队成员：岸
---

# 常见法律文书模板库

## 适用场景

- 用户需要常见生活场景的法律文书模板或撰写指导：劳务纠纷、离婚协议、交通事故、房屋租赁、消费纠纷。
- 触发语：「合同」「协议」「纠纷」「仲裁」「起诉」「离婚协议」「交通事故赔偿」「租房押金」。
- 用户只是想先看看某类文书长什么样、该写哪些内容。

## 步骤

1. **场景识别**：判断属于哪类文书。
   - 劳务纠纷 → `assets/doc-templates/labor-dispute-complaint.md`、`assets/doc-templates/employment-contract.md`
   - 婚姻家庭 → `assets/doc-templates/divorce-agreement.md`
   - 交通事故 → `assets/doc-templates/traffic-accident-claim.md`
   - 房屋租赁 → `assets/doc-templates/rental-agreement.md`
2. **提供模板参考**：展示模板核心结构，说明需个性化填写的部分，解释关键条款的法律含义。
3. **个性化修改指导**：区分必填项（当事人信息、时间、地点、金额）与可选条款；给出风险提示与格式规范检查。
4. **纠纷解决途径指引**：结合 `assets/dispute-resolution-guide.md`，按协商 → 调解 → 仲裁 → 诉讼的顺序给建议。
5. **转介专业帮助**：案情复杂、金额较大、法律关系不明、涉及重大人身权益（抚养权/监护权）、需进入诉讼仲裁程序时，明确建议咨询专业律师。

可选生成器（覆盖 labor / consumer / rental / traffic）：

```bash
bash scripts/legal-templates.sh <labor|consumer|rental|traffic> "<问题描述>"
```

- 依赖 bash 4+ 与 python3；脚本内嵌 Python 生成模板文本。**未实测运行**，以实际输出为准。

撰写要点：见 `assets/legal-document-guide.md`（格式规范、常见条款要点）。

## 输入输出

- 输入：场景描述 / 已有文书 / 用户的具体情况（当事人、时间、金额、争议点）。
- 输出：文书模板参考 + 个性化填写指导 + 关键条款解释 + 风险提示 + 解决途径建议。

## 注意事项

- 本技能只提供生活类法律文书模板与撰写指导（劳务 / 婚姻家庭 / 交通 / 租赁 / 消费）；中文商务合同起草与英文标准协议不在本技能范围。
- 模板仅供参考，具体内容须按实际情况调整；法规可能更新，须确认条款符合现行法律。
- 智能体可以：提供模板、解释条款、指导撰写、提示风险；不可以：替代律师出具意见、代理诉讼仲裁、承诺案件结果。
- 重要合同与涉及重大权益的文书，建议由专业律师审核。
- 文书使用正式、规范的法律用语；金额同时用大写与阿拉伯数字，日期用「××××年××月××日」。
- 证据可能灭失时提示申请证据保全；管辖存疑时提示先确认管辖法院。
- 涉及未成年人、第三方隐私的材料注意脱敏与标注。

## 可复用示例

用户：「公司拖欠我三个月工资，我该怎么维权？」
处理：识别为劳动报酬争议 → 读出 `assets/doc-templates/labor-dispute-complaint.md` → 指导准备证据（工资条、考勤记录）→ 展示仲裁申请书模板并指导填写 → 提醒仲裁时效为一年 → 金额大或情形复杂时建议咨询律师。

用户：「房东不退押金，想写个催告函。」
处理：读 `assets/legal-document-guide.md` 的催告函要点 → 指导写清租赁关系、押金金额、退还要求与期限 → 提醒保留催告证据，必要时调解或起诉。

## 关联资产

- `assets/doc-templates/` —— labor-dispute-complaint / employment-contract / divorce-agreement / traffic-accident-claim / rental-agreement
- `assets/legal-document-guide.md`、`assets/dispute-resolution-guide.md`
- `scripts/legal-templates.sh` —— 劳动/消费/租赁/交通模板生成器
