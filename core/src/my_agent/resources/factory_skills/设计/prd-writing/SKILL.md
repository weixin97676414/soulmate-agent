---
name: prd-writing
description: PRD 撰写：先做需求分析，再按中文十节模板输出 PRD 文档；可选另出 prd.json 机器可执行任务清单。触发场景：写 PRD、生成 PRD、产品需求文档、用户故事拆解、验收标准、AI agent 可执行任务清单。
author: Soulmate Agent团队成员：岸
---

# PRD 撰写

## 适用场景

- 新功能/优化需求的产品需求文档撰写
- 把用户故事转化为 PRD、快速生成 PRD 初稿
- 把需求拆成给 AI agent（Claude Code / OpenCode 等）顺序执行的用户故事清单
- 触发词：写PRD、生成PRD、产品需求文档、PRD文档、user stories、acceptance criteria

## 步骤

### 路线 A · 中文 PRD 文档（默认）

1. **先做需求分析，不要跳过**：收集功能背景、目标用户、核心场景、业务目标（数据指标）、竞品参考、约束条件。产出「需求摘要」（功能名称/背景/目标用户/核心场景/业务目标/优先级 P0-P2/期望上线时间）。
2. **按十节模板输出 PRD**（模板见下，完整版见 `assets/prd/prd-writer-template.md`）。
3. **自检**：每条需求可测试可验证；版本记录完整。

### 路线 B · 机器可执行任务清单（`prd.json`）

用于把一个功能拆成 AI agent 可顺序执行的小故事。文件放项目 `agents/prd.json`。

```json
{
  "project": "MyApp",
  "branchName": "ralph/feature-name",
  "description": "Short description of the feature",
  "userStories": [
    {
      "id": "US-001",
      "title": "Add priority field to database",
      "description": "As a developer, I need to store task priority.",
      "acceptanceCriteria": ["Add priority column: 'high' | 'medium' | 'low'", "Generate and run migration", "Typecheck passes"],
      "priority": 1,
      "passes": false,
      "notes": ""
    }
  ]
}
```

字段：`project` / `branchName`（前缀 `ralph/`）/ `description` / `userStories[]`（`id`、`title`、`description`、`acceptanceCriteria`、`priority`、`passes`、`notes`）。

**故事粒度**：每个故事应在一个上下文窗口内可完成。✅ 加一列并迁移 / 给现有页面加组件 / 改服务端逻辑 / 加一次筛选。❌ "搭整个仪表盘"、"加认证"——要拆开。

**排序**：按 priority 执行，前面的不得依赖后面的。正确顺序：① schema/迁移 → ② 服务端逻辑 → ③ 用后端的 UI 组件 → ④ 仪表盘/汇总视图。

**验收标准示例**：✅ "给 tasks 表加 `status` 列，默认 'pending'"、"筛选下拉含 All/Active/Completed"、"Typecheck passes"。❌ "工作正常"、"用户能轻松完成 X"。**始终包含 `"Typecheck passes"`**。

**进度跟踪**：完成后把 `passes` 改 `true`，用 `notes` 记运行时观察。

常用命令：

```bash
cat prd.json | jq '.userStories[] | {id, passes}'
jq '.userStories[] | select(.passes == false)' prd.json
```

## PRD 十节模板（路线 A）

```markdown
# PRD：{功能名称}
## 1. 文档信息   （版本/创建日期/作者/评审人/状态）
## 2. 背景与目标 （2.1 背景 2.2 目标 2.3 成功指标：指标+目标值）
## 3. 用户场景   （3.1 目标用户 3.2 用户故事："作为…我希望…以便…" 3.3 使用场景：触发条件/用户行为/预期结果）
## 4. 功能需求   （4.1 功能清单：模块|功能点|优先级|备注
                   4.2 功能详情：需求描述/交互流程/页面元素表/异常处理/埋点需求）
## 5. 非功能需求 （性能/安全/兼容性）
## 6. 界面原型   （页面流程图/关键页面说明）
## 7. 数据需求   （埋点事件/数据报表）
## 8. 风险评估   （风险类型|描述|影响程度|应对措施）
## 9. 项目计划   （里程碑表 + 依赖项）
## 10. 附录      （术语表/参考文档/变更记录）
```

**页面元素表**列建议：元素 | 类型 | 说明 | 校验规则。

## 输入输出

- **输入**：产品需求描述 / 用户故事 / 竞品信息 / 约束条件。
- **输出**：Markdown 格式的 PRD 文档；或 `agents/prd.json` 任务清单。

## 注意事项

1. **先分析，后输出**——不跳过需求分析直接写 PRD。
2. **保持简洁**——PRD 不是越厚越好，关键信息清晰即可。
3. **可验证**——每个需求都可测试、可验证。
4. **及时同步**——PRD 是协作工具，需与团队同步评审。
5. **版本管理**——重大变更记录变更历史。
6. 输出用 Markdown；表格放结构化信息，列表放枚举项，代码块放示例数据。

## 可复用示例

**输入**："我们要做一个『智能股价提醒』功能，用户可以设置股价提醒，达到设定价位时通过飞书通知。"

**需求分析**：背景=用户需实时监控股价及时获取信号；目标用户=个人投资者；核心场景=设置提醒价位→系统监控→触发通知；业务目标=提升交易效率、增加粘性。

**输出**：按十节模板产出完整 PRD；功能清单中"设置提醒价位"为 P0、"飞书通知渠道"为 P0、"多股票批量设置"为 P1；异常处理覆盖"股价接口超时→重试 3 次后记录失败"；埋点含"提醒创建成功/失败"。
