---
name: litigation-drafting
description: 诉讼文书起草与诉讼费估算：生成起诉状/答辩状/证据提纲，估算诉讼费与劳动赔偿、判断是否值得起诉。触发场景：要「起诉/打官司/诉讼材料/答辩状」，问「诉讼费多少/被辞退赔多少/值不值得起诉」。
author: Soulmate Agent团队成员：岸
---

# 诉讼文书起草与诉讼费估算

## 适用场景

- 用户要起诉或应诉，需要起草起诉状、答辩状、证据提纲。
- 用户问「被辞退能拿多少赔偿」「10 万块诉讼费多少」「值不值得起诉」。
- 触发语：「起诉状」「打官司」「起诉」「诉讼材料」「答辩状」「证据清单」。

## 步骤（起诉状 / 答辩状 / 证据提纲）

1. **案情信息收集**：按四组要素收集。
   - 当事人：原告/被告姓名或名称、性别、出生日期、民族、职业、住址、联系方式；代理人信息。
   - 诉讼请求：逐项写明，含金额/数量与诉讼费承担。
   - 事实与理由：争议发生的时间、地点、经过；法律关系；权益受损情况；被告承担责任的法律依据。
   - 证据材料：名称、来源、形成时间、证明目的、存放形式。
2. **要素完整性核查**：对照 `assets/legal-complaint-guide.md` 核查当事人信息、诉讼请求明确性、事实连贯性、证据充分性；缺项主动追问。
3. **撰写文书**：按 `assets/complaint-template.md` 生成——标题、当事人信息、诉讼请求（一、二、三…）、事实与理由（按时间顺序）、证据清单（附证明目的）、结尾（致送法院、落款日期、具状人签名）。
4. **质量审查**：格式规范性、事实与请求对应性、证据关联性、语言规范性（避免情绪化）。
5. **特殊情形处理**：共同诉讼分别列明；告知反诉权利与条件；证据可能灭失提示保全；管辖存疑提示确认管辖法院。

文书骨架（无模板场景）见 `assets/document-skeletons.md`。

## 步骤（诉讼费 / 赔偿估算）

1. 确认关键事实（标的额、案件类型、劳动关系时长、月工资等）。
2. 套用估算规则：诉讼费规则见 `assets/calculation-formulas.md`；劳动补偿情景见 `assets/labor-dispute-scenarios.md`。
3. 快速计算（可选脚本）：

```bash
python3 scripts/calculate_lawsuit_fee.py <claim_amount_rmb>
```

该脚本输出常见中国民事财产案件一审受理费估算（含大额分段费率），不含律师费与其他费用。劳动补偿/是否起诉的结构化模板见 `assets/labor-compensation-output-template.md`、`assets/litigation-worth-it-template.md`。

命令行估算还提供 `fee <amount>`、`complaint <原告> <被告> <类型> [金额]`、`timeline <日期> [类型]`（类型：civil / labor / contract / injury / divorce）：

```bash
bash scripts/court-prep.sh fee 100000
bash scripts/court-prep.sh complaint 张三 李四 labor 50000
```

（命令签名取自脚本 help，**未实测运行**。）

## 输入输出

- 输入：当事人信息、诉讼请求、事实经过、证据情况；或标的额与案情事实。
- 输出：结构化文书（起诉状/答辩状/证据提纲）+ 缺失事实清单 + 证据准备清单 + 律师复核提示点；费用任务输出：已用事实 + 依据 + 计算步骤 + 预估结果 + 提醒 + 下一步。

## 注意事项

- 结尾必须附免责声明：结果仅供初步参考，不构成正式法律意见；重要事项应由执业律师结合完整事实和最新当地规则审核。
- 禁止承诺案件结果；禁止把不完整事实当作充分依据；禁止用旧标准当现行规则。
- 当事人隐私信息准确记录；涉及未成年人、第三方隐私时注意表述与标注。
- 诉讼请求应合理可行、事实客观真实、证据确实充分。
- 时效提示：劳动仲裁时效为一年；接近时效/期限的案件优先提示。
- 本技能产出诉讼文书（起诉状 / 答辩状 / 证据提纲）与诉讼费估算；生活类通用文书模板不在本技能范围。

## 可复用示例

用户：「朋友借了我 5 万块钱不还，我想起诉。」
处理：收集借款时间、方式、凭证、催收记录 → 按 `assets/complaint-template.md` 生成起诉状 → 附证据清单（借条、转账记录、聊天记录）→ 用 `calculate_lawsuit_fee.py 50000` 估算受理费 → 提示民间借贷管辖（被告住所地/合同履行地）。

用户：「我标的 30 万，诉讼费大概多少？值不值得起诉？」
处理：运行 `calculate_lawsuit_fee.py 300000` 给出受理费估算 → 用 `assets/litigation-worth-it-template.md` 结构化列出诉讼成本、时间成本、执行难度与胜诉可能性。

## 关联资产

- `assets/complaint-template.md`、`assets/legal-complaint-guide.md`、`assets/document-skeletons.md`
- `assets/calculation-formulas.md`、`assets/labor-dispute-scenarios.md`、`assets/labor-compensation-output-template.md`、`assets/litigation-worth-it-template.md`
- `scripts/calculate_lawsuit_fee.py`、`scripts/court-prep.sh`
