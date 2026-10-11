---
name: office-task-dispatch
description: 办公任务分流：识别办公请求并分流到 25 类工作流（邮件草拟 / 数据分析透视 / PPT / 合同审查 / 发票入账 / ERP / 翻译 / 招聘 JD / 日程排期 / 新媒体文案 / 流程图 / OKR 等），并守事实纪律与 AI 标识合规。触发场景：一句话办公请求，或会议纪要 / 工作简报 / ASR 校对 / 脱敏之外的办公事务。
author: Soulmate Agent团队成员：岸
---

# 办公任务分流与通用事务


## 适用场景

- 把办公请求识别并分流到 25 类内置工作流：会议纪要、文档总结、邮件草拟、晨间简报、知识库、转 PPT、客户跟进、培训笔记、周报日报、行动项追踪、财务 ERP、办公软件接入、数据分析透视、OCR、合同审查、发票入账、录音转写、翻译、招聘 HR、日程排期、合同起草、新媒体文案、流程图/架构图、OKR 绩效等。
- 一句话触发，例如"整理这份会议纪要""把周报数据做成透视表""审查这份采购合同""把录音转成文字""写个小红书文案"。
- 与会议纪要、工作简报、ASR 校对相关的深流程走对应功能文件（`references/meeting-minutes-tracking.md`、`references/work-brief.md`、`references/asr-transcript-proofread.md`）；本文件负责其余办公事务与总路由。

## 步骤

1. **识别场景**：按主路由表关键词判定场景（`assets/office-task-dispatch/references/dispatch.md`）。歧义时按规则优先（邮件与纪要混用→优先纪要；报告与 PPT 混用→先确认文字稿还是 PPT 大纲；财务与表格混用→优先财务；合同"起草/拟"→起草，"审查/看风险"→审查，含两者则起草后接审查）。
2. **按域加载**（一次只读一个域，不铺开）：
   - 内容创作（§1–§8、§17）→ `assets/office-task-dispatch/references/dispatch-a-content.md`
   - 数据票据（§9–§13、§15、§18）→ `dispatch-b-data.md`
   - 专业服务（§14、§16、§19–§25）→ `dispatch-c-special.md`
3. **任务路由与成本控制**：纯文本场景（纪要/邮件/文案/翻译/总结/OKR）走内置轻工作流，不加载文件处理技能；文件级场景（Excel/PPT/Word/PDF/图片）才调 xlsx/pptx/docx/pdf；单次只解决一个主场景，完成后询问是否继续；单文件 ≥50MB 或表格行数 >5 万时先读结构再决定全量或分块。
4. **执行**：调宿主相应技能或内置轻工作流；模板从 `assets/office-task-dispatch/templates/` 取用。
5. **事实纪律（强制）**：所有产出标置信度（已确认 / 推断 / 待确认）与来源 `[来源: ...]`，缺失标 `[待确认]`；禁止臆造数字、法条、人名、条款、金额；产出前自检，被纠正即改并标【已修正】。
6. **AI 生成合成内容标识合规**：面向公众发布的内容交付时提示显式（文首/文末标"AI 辅助创作"等）+ 隐式（文件元数据）标识义务；对内不强制；新媒体文案叠加广告法自查。
7. **交付后**：询问是否沉淀进知识库。

## 输入输出

- 输入：直接对话文字、上传文件（Excel/Word/PDF/图片/PPT/Markdown/音频 .mp3/.wav/.m4a）、连接器数据、混合输入。
- 输出：按场景的草稿/表格/大纲/清单/文档；**不执行对外动作**（不发邮件、不直连 ERP 入账、不替人审批签字）。

## 注意事项

- **异常统一模板**：外部依赖缺失 → 说缺失项 + 1 个内置降级方案 + 1 个可选增强路径；格式不对 → 给修正选项；输出不满意 → 先问"具体哪部分"，再给调整方向；禁用"可能吧/试试看/你自己处理一下"等模糊话术。
- **零依赖开箱即用**为核心场景；连接器/专用技能为可选增强，未装自动降级，不伪造接口。
- 财务口径必须对齐用户 ERP 科目表与会计期间，禁止臆造科目或金额。
- 默认简体中文；中国股市相关遵循红涨绿跌。
- 性能：单文件默认 <50MB 直接处理，大文件分块；调用外部命令/连接器失败自动重试最多 3 次（间隔 1s→3s→5s），仍失败再报错。
- 检测到敏感字段先问用户脱敏档位（见 `references/sensitive-data-precheck.md`），不默认遮盖内部数据。
- **不做**：自动发邮件、改日程、入账、签字审批、擅自联网抓取、伪造接口。

## 可复用示例

- 「把这份周报数据做成透视表，按地区看销售额」→ 数据分析/表格场景 → `dispatch-b-data.md` → 可选调 xlsx，未装走内置。
- 「写个小红书文案，卖点 XX，种草风」→ 新媒体文案 §23 → `dispatch-c-special.md` → 平台调性 + 标题备选 + 正文 + 标签 + 广告法/AI 标识自查。
- 「把这段会议录音转成文字再整理成纪要」→ §16 转写（走 `references/asr-transcript-proofread.md`）→ §1 纪要。
- 「审查这份采购合同，标出法务和财务风险」→ 合同审查 §14 → 可选调审查技能，未装走内置 + `contract-review-template.md`。

## 支撑文件

- 参考：`assets/office-task-dispatch/references/`（`dispatch.md` 主路由表、`dispatch-a-content.md` / `dispatch-b-data.md` / `dispatch-c-special.md` 分域工作流、`capability-list.md` 25 场景能力边界、`fact_discipline.md` 事实纪律、`privacy_desensitization.md` 脱敏、`examples.md` 示例、`faq.md`、`best-practices.md`）。
- 模板：`assets/office-task-dispatch/templates/`（`weekly-report-template.md`、`email-draft-template.md`、`morning-brief-template.md`、`pptx-outline-template.md`、`customer-followup-template.md`、`learning-notes-template.md`、`action-tracker-template.md`、`finance-erp-template.md`、`data-analysis-template.md`、`ocr-prep-template.md`、`contract-review-template.md`、`invoice-ocr-template.md`、`audio-asr-guide.md`）。
