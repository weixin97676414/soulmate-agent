---
name: nursing-docs
description: 护理文档与监护计划：生成交接班（ISBAR）、病程（SOAP）、护理计划（PES）等临床护理文书，并可检索中华护理学会团体标准生成护理监护计划 HTML 报告。触发场景：写交接班、护理计划、护理监护计划、患者宣教、出院小结。
author: Soulmate Agent团队成员：岸
---

# 护理文档与监护计划

## 适用场景

面向护士与一线医护。触发：

- 交接班记录（ISBAR）、病程记录（SOAP）、护理计划（PES）、入院/观察/事件记录、出院小结
- 患者/家属沟通与健康宣教（通俗化解释）
- 用药查询、给药记录、PRN 依据、绩效自评、执业范围、职场沟通
- **护理监护计划生成**：输入诊断/症状/病历 → 检索中华护理学会团体标准 → 输出完整护理监护计划 HTML 报告

## 步骤

### A. 护理文书（ISBAR / SOAP / PES 框架）

1. **识别临床情境**：handover / care_plan / documentation / discharge / communication / medication / professional / assessment（从描述推断，仅当显著改变输出时才追问）。
2. **套用对应临床框架**：
   - 交接班 → **ISBAR**（Identification / Situation / Background / Assessment / Recommendation）
   - 病程记录 → **SOAP**（Subjective / Objective / Assessment / Plan）
   - 疼痛 → PQRST；病情恶化 → BETWEEN；跌倒 → STRATIFY 或本地工具；压疮 → Braden；精神心理 → MSE；生命体征 → Track and trigger（HR/RR/SpO2/BP/Temp/GCS/尿量）
3. **生成文书**：合理用药必须在药学或资深临床医师复核后执行；医嘱范围不确定先上报；哨兵事件走事件上报流程；知情同意须 RN 或医师参与。
4. **患者沟通**：通俗语言（Grade 6–8 阅读水平，关键指示句 ≤15 词）；结构"发生什么 → 为何重要 → 患者要做什么 → 何时求助"；结尾用 teach-back（"能用你自己的话告诉我你会怎么做吗？"）。
5. **专科适配**：ICU（呼吸机文档、镇静评分、MAP 目标、液体平衡）；急诊（分诊、时间敏感干预）；儿科（按体重计算、发育性语言、家长沟通）；老年（跌倒预防、认知评估、预立医疗照护）；精神科（MSE、治疗性沟通、风险评估）；社区（居家评估、功能独立性、照护者支持）。
6. **记录标准**：及时（越接近事件越好，回顾性记录需注明）；准确（记录观察到和做到的，非计划或假定）；客观（解释性语言须标注为评估）；完整（"没记录=没做"）；更正（单线划改、签名与日期，绝不删除）；上报（记录所沟通的临床顾虑及对象）。

### B. 护理监护计划 HTML（nursing-care-plan 管线）

1. **信息收集与理解**：识别主要诊断、临床症状/主诉、病历摘要、护理级别（默认推断为一级护理）、住院天数/临床路径周期；复述确认后继续。
2. **检索中华护理学会团体标准**：WebFetch `https://hltb.kxj.org.cn/index/tuanti/index.html` 获取标准列表；按诊断/症状匹配最相关 1–3 项（呼吸/气管→气道护理、氧气吸入、机械通气；肿瘤/化疗→化疗药外渗预防、癌性疼痛护理；消化/造口→肠造口护理；约束/认知障碍→身体约束护理、激越行为非药物管理；手术→器械清洗；通用→成人氧气吸入 T/CNAS 08-2019）。详情页形如 `https://hltb.kxj.org.cn/index/tuanti/standard.html?team_standard_id=N`，从"标准下载"区取 PDF 链接下载（脚本 `scripts/fetch_standards.py` 已随附）。
3. **PDF 结构化分析**：`scripts/nursing_analyze_pdf.py`（pdfplumber 提取全文 → 规则提取）输出 JSON：`standard_name`、`standard_code`、`nursing_assessment`、`indications`、`contraindications`、`preparations`（drugs/equipment/patient_prep/environment_prep）、`operation_key_points`、`complications`、`intervention_measures`、`precautions`。
4. **生成 HTML 报告**：`scripts/nursing_generate_html.py --diagnosis "..." --standards_json <阶段三JSON> --output <out.html>`。
   报告结构：患者基本信息 → 一、护理监护医嘱（护嘱+物资）→ 二、护理巡查计划（频率+登记表）→ 三、护理服务计划（3.1 评估 / 3.2 宣教 / 3.3 操作 / 3.4 风险因素清单 / 3.5 会诊 / 3.6 巡查记录表 / 3.7 随访计划）。设计要求：医疗专业风格、时间轴、A4 可打印、核查框、标准来源引用、响应式。
5. **输出**：展示 HTML 文件；告知引用的标准号与名称、PDF 是否成功下载/分析、需用户补充的信息。

## 输入输出

- 护理文书输入：情境描述 / 患者信息；输出：ISBAR、SOAP、PES 护理计划等结构化文本。
- 监护计划输入：诊断 + 症状（+病历、护理级别、住院天数）；输出：护理监护计划 HTML 报告。

## 注意事项

- 用药相关查询 → 先与药学或资深临床医师核实；执业范围不确定 → 先上报再行动。
- 脚本环境（未验证）：Python 3.13、依赖 `pdfplumber`/`requests`/`beautifulsoup4`；PDF 结构化分析走本地规则提取。请按本机实际路径调用脚本。
- PDF 需登录无法下载时，改用 WebFetch 读详情页文本；无法匹配标准时用 T/CNAS 08-2019 通用兜底；诊断不全先追问；PDF 文本为空则跳过并在报告注明"标准内容待人工补充"。
- 生成的计划仅供临床参考，须由执业护士按患者实际确认；引用标准以中华护理学会最新版为准。

## 可复用示例

1) 交接班：输入"67 岁男性，NSTEMI 入院第 3 天，PCI 后"→ 输出 ISBAR 五段（含 bed/MRN/admitting dx、当前concern、PMHx 与用药、Obs 趋势、待办与 watch points）。

2) 监护计划：输入"结肠造口术后护理"→ 匹配中华护理学会肠造口护理标准 → 导出 PDF 结构化 JSON → 生成含护理监护医嘱、巡查计划、风险评估、宣教、随访的 HTML 报告。
