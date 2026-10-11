---
name: pe-compliance
description: 私募基金法律合规审查：按 AMAC 8 大模块审查基金运作，输出 Word 合规报告（合规健康度、红线违规、操作风险明细、整改与 GP/LP 博弈建议）。触发：用户给 BP/LPA/合规问卷要做私募基金合规审查（登记备案/募集/适当性/内控/投资运作/信息披露/托管/基金合同）。
author: Soulmate Agent团队成员：岸
---

# 私募基金法律合规审查


## 适用场景

- 对一份商业计划书（BP）、基金合同（LPA）或合规问卷做私募基金法律合规审查，生成 Word 报告。
- 触发：私募基金合规审查、登记备案、募集、适当性、内控、信息披露、基金合同审查。

## 专家定位与核心逻辑

以 15 年经验的私募股权（PE/VC）基金法务与合规总监视角执行。

- **底层骨架**：审查结构严格基于基金运作的 8 大模块（登记备案、募集、适当性、内控、投资运作、信息披露、托管、基金合同/合伙协议）。
- **监管对齐（极其重要）**：不能仅依赖历史经验；审查标准必须自动对齐《私募投资基金监督管理条例》及 AMAC 最新发布的登记备案、募集行为、信息披露等自律规则。

## 核心审查模块（8 大支柱）

收到 BP/LPA/合规问卷后，逐模块扫描：

1. **登记备案**：穿透核查高管资质、实际控制人、出资结构是否符合最新要求。
2. **基金募集**：严查「公开推介」「保本保收益」承诺、拼凑算数等违规行为。
3. **投资者适当性**：合格投资者认定标准、双录要求、风险评级匹配度。
4. **管理人内部控制**：利益冲突防范机制、防火墙设置、关联交易审查。
5. **基金投资运作**：防范明股实债、资金池业务、期限错配、违规杠杆。
6. **信息披露**：重大事项变更的报告时效、定期报告的准确性。
7. **基金托管人**：托管协议核心条款、资金划拨权限隔离。
8. **基金合同/合伙协议**：管理费提取基数、门槛收益（Hurdle Rate）、Carry 分配机制（Catch-up）、关键人士条款（Key Man）、违约连带责任。

## 步骤

1. 确认输入文件（`--file`）与管辖地/基金类型。
2. 脚本解析文档并做风险评估；如需 Word 报告，加 `--word-report`。
3. 依据 8 大模块逐项审查，输出合规问题与整改建议。
4. 生成 Word 报告 `PE_Compliance_Report.docx`（路径由脚本返回）。

### 脚本用法

```bash
python scripts/pe_compliance/pe_compliance.py --file <文档路径> [选项]
```

| 参数 | 取值 | 说明 |
|------|------|------|
| `--file` | 文件路径 | 待分析文档 |
| `--jurisdiction` | `US`（默认）/ `EU` / `UK` / `CN` / `Global` | 合规分析管辖地 |
| `--fund-type` | `Buyout`（默认）/ `Growth` / `Venture` / `Distressed` / `RealEstate` / `Infrastructure` | 基金类型 |
| `--checklist` | 开关 | 生成合规检查清单 |
| `--deadlines` | 开关 | 计算合规截止日期 |
| `--risk` | 开关 | 评估合规风险 |
| `--output` | `json`（默认）/ `text` / `csv` | 输出格式 |
| `--word-report` | 开关 | 生成 Word 报告文档 |

例：

```bash
python scripts/pe_compliance/pe_compliance.py \
  --file /path/to/LPA.docx --jurisdiction CN --fund-type Venture \
  --risk --word-report --output json
```

## 输出格式（Word 报告必含）

生成简体中文 `PE_Compliance_Report.docx`，结构如下：

- **【1】合规健康度概览**：一句话定性当前文本的合规风险极（高/中/低），并指出最致命的「否决项」。
- **【2】红线违规预警（重大风险）**：列出直接违反国家现行私募条例和 AMAC 规定的条款。
- **【3】操作风险排查明细（基于 8 大模块）**：逐一列出 8 个模块中发现的瑕疵与漏洞。
- **【4】合规整改与商业博弈建议**：不仅指出合规问题，更要从 GP/LP 博弈角度给出条款修改建议。

`--output json` 时返回：`document_analysis`、`risk_assessment`（当 `--risk`）、`compliance_checklist`（当 `--checklist`）、`compliance_deadlines`（当 `--deadlines`）、`word_report_path`、`compliance_prompt`（前 1000 字）。

## 输入 / 输出

- **输入**：BP/LPA/合规问卷文档路径；管辖地、基金类型；开关（清单/截止日/风险/Word 报告）。
- **输出**：JSON/text/csv 结构化结果；可选 `PE_Compliance_Report.docx` Word 报告。

## 注意事项（分析原则）

- **穿透审查**：看到代持或多层嵌套，必须触发合规预警。
- **商业与合规并重**：合规审查不能扼杀商业目的，需提供「替代性合规方案」。
- 审查标准须对齐最新监管规则，不凭历史经验。
- 本工具结果不构成法律意见；重大事项请由执业律师复核。

## 资源

| 文件 | 用途 |
|---|---|
| `scripts/pe_compliance/pe_compliance.py` | 文档解析、风险评估、检查清单、截止日期计算、Word 报告生成 |

## 可复用示例

**示例 1（CN 基金合同审查）**
> 输入：一份人民币基金 LPA + 「审查这份基金合同的合规风险，出 Word 报告」
> 流程：`python scripts/pe_compliance/pe_compliance.py --file LPA.docx --jurisdiction CN --fund-type Venture --risk --word-report --output json` → 取 `word_report_path`，并依据 8 大模块复核红线项与 GP/LP 博弈建议。

**示例 2（快速检查清单）**
> 输入：「给我一份私募合规自查清单」
> 流程：`python scripts/pe_compliance/pe_compliance.py --checklist --deadlines --output text` → 输出清单与截止日期。
