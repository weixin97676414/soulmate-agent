---
name: student-record-ops
description: "少儿英语学员成长档案运营，覆盖咨询建档、试听测评、课后记录、每周跟进、月度学情总结与续费跟进，用统一档案结构落档。用于学员建档、试听测评、课后或每周或月度跟进、家长反馈、续费沟通等场景。"
author: Soulmate Agent团队成员：岸
---

# 功能：少儿学员成长档案


## 适用场景

- 少儿（英语）学员的咨询建档、试听测评、在读课后记录、每周跟进、月度学情总结、续费跟进。
- 家长诉求与反馈的记录与落档。
- 需要把「对话填写」或「网页填写」两种采集方式统一写入同一套档案结构。

触发词：学员建档、咨询建档、试听测评、课后记录、每周跟进、月度学情总结、家长反馈、续费沟通。

## 目录与文件规则

学生根目录（每条记录放在对应状态子目录下）：

```
<学生根目录>/
├── Leads/           # 咨询线索
├── Active/          # 在读
├── RenewalWatch/    # 续费关注
└── Archived/        # 归档
```

学生目录命名：`{grade}-{studentName}-{startDate}`，例如 `G3-Luna-2026-04-15`。

学生目录内文件：
- 老师可读层：`02-家长需求.txt`（家长诉求与跟进摘要）、`03-课后跟进记录.txt`（学习情况与课后跟进，按日期追加）。
- 系统数据层：`_data/student-record.json`（唯一结构化存档，字段见 `assets/student-file-schema.json`；课次在 `lessonLog.rows` 中追加对象）。
- 网页中间采集：`form-submissions/{studentName}-{timestamp}.txt`（逐行 `字段名：内容`，需再合并进正式档案，**不是**最终存档）。

根目录可通过环境变量指定：`STUDENT_GROWTH_OPS_ROOT` 指向包含 `assets/student-form.html` 的技能根路径。

## 强制规则

1. 第一问先确认学生名称。
2. 进入任何阶段前，先按学生名称检查是否已有档案；有则进「跟踪/更新」，无则进「新建档案」，不重复建档。
3. 先从用户自然语言提取已明确信息，已明确的字段不重复问。
4. 先问一次填写方式（网页 / 对话），不要一开始连续提问。
5. 对话填写每轮只问 1–2 个问题，题目来自 `assets/question-bank.json`；每确认一轮就立即写入对应文件。
6. 网页填写与对话填写**最终写入同一套文件与字段语义**，不允许两套结构。
7. 业务记录：系统数据为单个 `_data/student-record.json`；老师可读层为 `02`、`03`。
8. 给家长的即时沟通话术（微信 / 短信 / 课后反馈）**默认只在对话里输出完整文本**，语气礼貌、温柔、有共情；除非用户明确要求落档，否则不覆盖 `02`。
9. 回复用户时不贴 `student-record.json` 全文，用「系统数据已同步更新」概括；若更新了 `02`、`03`，用纯文本绝对路径标出。

## 工作流

1. **识别阶段**：`intake`（咨询/报名/家长需求）、`assessment`（试听/测评/首诊）、`lesson-log`（单次课后）、`weekly-followup`（一周汇总）、`monthly-report`（月度总结）、`renewal-watch`（续费沟通）。
2. **先提取再提问**：优先提取 `studentName / grade / status / currentLevel / primaryGoals / painPoints / sourceChannel / parentNeeds`，不重复追问。
3. **先确认姓名，再查档**：拿到姓名后先在根目录各状态子目录查找；有档案 → 跟踪更新，无 → 新建。
4. **确认填写方式**（网页 / 对话），并说明两者优势（网页：更快更精准；对话：方便，微信也能完成）。
5. **网页填写**：启动已有页面服务，不重新生成网页代码。
   - 一键启动：`node scripts/open_student_form.js`
   - 带参数：`node scripts/open_student_form.js --studentName=张三 --grade=G3 --status=active --stage=monthly-report`
   - 单独启动服务：`node scripts/index.js`（页面地址 `http://127.0.0.1:8766/student-form`）
   - 端口冲突：`lsof -nP -iTCP:8766 -sTCP:LISTEN`，或用环境变量 `STUDENT_GROWTH_PORT` 改端口
   - 页面按姓名调用 `GET /api/lookup-student?name=...` 扫描各状态子目录，识别 `_data/student-record.json` 中 `studentProfile.studentName` 一致的目录，并提示「新建档案 / 已找到档案·跟踪更新」。
   - 用户点「完成填写」后回到对话回复「填写完成」，再读取 `form-submissions/` 下的文本，回写正式档案。
6. **对话填写**：以 `assets/question-bank.json` 为唯一题库；每轮 1–2 个未完成字段，有用稳定选项的问题优先用选择式；每轮结束先写入再继续。
7. **确保目录存在**：不存在则按状态选根目录，用脚手架初始化：
   ```bash
   python scripts/scaffold_student.py --student-name "学生名" --grade "G3" --status "leads" --start-date "2026-04-15"
   ```
   已存在则原地更新，不重复建目录。
8. **按阶段写入正确文件**：
   - `intake` → `studentProfile`、`parentNeeds`、`tags`（需要建档摘要时才更新 `02`）
   - `assessment` → `learningBaseline`、`tags`
   - `lesson-log` → `lessonLog.rows` 追加一行（字段与 `lessonLog.columns` 一致）+ `03` 记摘要
   - `weekly-followup` / `monthly-report` → `weeklyFollowup`、`tags`（必要时 `03` 记摘要）
   - `renewal-watch` → `parentNeeds`、`tags`，必要时目录转入 `RenewalWatch`

   写入规则：旧值只在新信息明确覆盖时替换；数组去重；标签简短可搜索；日期统一 `YYYY-MM-DD`；小步确认、小步写入。

## 输入输出

- **输入**：学生名称、年级、状态、家长诉求、学习情况、课后记录等（对话或网页采集）。
- **输出**：学生目录下 `02`、`03` 文本 + `_data/student-record.json`；网页模式的中间文件在 `form-submissions/`。
- **脚本 / 页面**：`scripts/`（`open_student_form.js`、`scaffold_student.py`、`index.js`）、`assets/student-form.html`、`assets/question-bank.json`、`assets/student-file-schema.json`、`assets/visual-output-config.json`。

## 注意事项

1. 不要创建额外的 Markdown 总结文档；不要创建分叉的文件结构。
2. 网页实现已存在，运行时只启动服务与打开页面，不重写网页代码。
3. 学生根目录属于用户数据，路径应可配置，不写死到本仓库绝对路径。

## 可复用示例

**新建档案**：用户「新学员小明，三年级，家长想提分和练口语」→ 提取 `studentName=小明`、`grade=G3`、`parentNeeds=[提分, 口语表达]` → 查无档案 → 问填写方式 → 用 `scaffold_student.py` 在 `Leads/` 建 `G3-小明-2026-04-15` → 对话每轮 1–2 题写入 `_data/student-record.json`，收尾用纯文本给出目录路径。

**网页填写**：启动页面 → 用户填写并点「完成填写」→ 生成 `form-submissions/小明-<timestamp>.txt` → 用户回复「填写完成」→ 读取该文件并合并进正式档案。
