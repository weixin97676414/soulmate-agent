---
name: dev-workflow
description: 全栈开发总控：六步闭环（工作记忆加载→分析指令→需求澄清→制定方案→执行→验证→交付→复盘）+ 子技能意图路由（API 设计、代码生成/审查/重构、测试、性能基准、技术选型、MySQL、CMS、前端设计、项目记忆与知识图谱）+ 工程纪律层。触发场景：完整项目从需求到交付、补接口、写脚本、改逻辑、建站、上线、发布、技术选型、威胁建模。
author: Soulmate Agent团队成员：岸
---

# 功能：全栈开发总控

领域参考文档见 `assets/dev-expert-references/`（39 个文件）；知识图谱脚本见 `scripts/dev-expert/build_graph.py`。

## 适用场景
从需求到交付的通用软件/网站项目总控，以及单点开发任务的细分路由（API 设计、Bug 诊断、代码生成/审查/重构、测试用例、性能基准、技术选型、文档、任务拆解、Spec 驱动、MySQL、CMS、前端设计、项目记忆、项目知识图谱，及工程纪律层）。触发：实现功能、补接口、写脚本、改逻辑、完整项目、建站、上线、发布、审查、重构、性能、依赖引入、威胁建模等。

## 执行流程（六步闭环，禁止跳过验证与复盘）

1. **Step 0 工作记忆加载**：新会话先按 `project-memory-management` 恢复上下文；启用「写后即记」——实质工作完成后立即向 `{PROJECT_ROOT}/.ai-memory/{YYYYMMDD}/daily.md` 追加记录（append-only，UTF-8 无 BOM）。纯查询/只读不触发。
2. **Step 1 分析指令**：恢复历史记忆 → 意图识别与路由匹配。
3. **Step 1.5 需求澄清门控**：复杂任务强制——先提案再纠、边界追问、验收口径对齐、假设显式化、范围确认（In/Out of scope）。
4. **Step 2 制定方案**：加载对应 reference 模板 → 前置检查（安全闸门）→ 规划门禁 PLAN-GATE → 复杂任务查项目知识图谱依赖闭包 → 确认输入与验收口径 → 专项纪律预判。
5. **Step 3 执行**：按模板执行；遵守「写码前实码确认」「审计修复分离」「不卡死计数器」「批量修改 7 防线」「架构一致性铁律」「防 AI 通病五戒」。
6. **Step 4 验证**：证据是交付硬前提（命令+输出 / 测试报告 / 截图+步骤 / API 响应之一）；清单化质量自审 10 条 + 安全红线 10 条 + 覆盖完整性枚举。
7. **Step 5 交付**：SELF-AUDIT 17 条 + 步骤号一致性校验 + 变更摘要 + 验证证据 + 已知限制与剩余风险 + 收尾报告；命中 `production-readiness` 时过 PRR 六维。
8. **Step 6 复盘沉淀**：Session Summary / Decision Record / Convention Capture / 已知问题 / 判断回溯录（`error-ledger`）/ 事故复盘 / 阶段导航。

## 子技能路由（`@英文标识` 可显式调用跳过路由）
| 子技能 | 标识 |
|---|---|
| 软件项目总控 | `software-project` |
| 网站项目总控 | `website-project` |
| API 设计 | `api-design` |
| Bug 诊断 | `bug-diagnosis` |
| Karpathy 编码规范 | `karpathy-coding-guidelines` |
| Spec 驱动开发 | `spec-driven-development` |
| 代码审查 | `code-review` |
| 代码生成 | `code-generation` |
| 任务拆解与执行 | `task-decomposition-and-execution` |
| 技术选型 | `tech-selection` |
| 文档生成 | `doc-generation` |
| 测试用例生成 | `test-generation` |
| 性能基准测试 | `performance-benchmark` |
| 重构建议 | `refactoring` |
| 项目记忆管理 | `project-memory-management` |
| CMS 二次开发 | `cms-development` |
| 前端设计 | `frontend-design` |
| MySQL 数据库 | `mysql-database` |
| 项目知识图谱 | `project-knowledge-graph` |

**领域路由**（按任务领域选首选 + 协同 reference）、**专项 reference**（laravel/java/javascript/execution-safety/delivery-assurance/error-ledger/style-alignment/architecture-decision/domain-driven-design/distributed-systems/root-cause-debugging/design-critique/dev-navigation/incident-review/threat-modeling/production-readiness）与**优先级矩阵/协同顺序**详见 `assets/dev-expert-references/` 中对应文件。

## 意图三分法（决定自主度）
- **信息查询**：只读回答，不改文件。
- **简单任务**：目标明确、范围小、风险低 → 快速通道，直接执行并给验证证据。
- **复杂任务**（多文件/跨模块/DB/配置/构建链/安全/批量/业务规则不明）→ 先方案、影响范围与验证路径，必要时等确认。

## 输入输出
- 输入：用户需求（原始描述）、项目代码/上下文。
- 输出：按子技能模板的交付物 + 验证证据 + 变更摘要 + 已知限制 + 收尾报告；记忆沉淀文件。

## 注意事项（关键边界）
- **安全闸门**：涉生产配置、DB 写入、权限、凭证、隐私或不可回滚操作时退出快速通道，先给方案与验证路径；发现密钥/Token 只说明风险不展开值。
- **非 Git 安全协议**：改前先读、优先局部补丁、中文/编码安全、验证失败不交付。
- **上下文延迟加载**：默认只读入口/目标/直接引用文件，避免上下文污染。
- **子 Agent 边界（L0）**：检索型只回 `文件:行号 + 原文` 不推理；执行型须授权；审查型只出问题清单；子 Agent 不执行 DB 写入/生产配置/权限变更/凭证处理。
- **轮次与熔断**：默认 3 轮、安全上限 6 轮、每轮 ≤3 改动点；同一 Bug 2 轮未修 → 标记已知限制；数据/安全类失败 0 重试。
- **未验证项强制披露（L0）**：无法验证/降级/部分失败的条目必须显式列出，禁止隐藏。
- 需要深度领域内容时读 `assets/dev-expert-references/<name>.md`；知识图谱查询 `python scripts/dev-expert/build_graph.py --root {PROJECT_ROOT} --query <文件> --direction both --depth 3`（图谱仅作加速器，动刀前 grep 复核）。

## 可复用示例
> 「给现有 Laravel 项目加一个导出报表接口」
> Step 1 路由命中 `laravel-development` + `api-design`；Step 1.5 澄清导出格式/数据范围/权限；Step 2 加载对应 reference、过 PLAN-GATE、查依赖闭包；Step 3 按 Laravel 约定实现（Form Request 校验 + Service + 队列）；Step 4 跑 PHPUnit + PHPStan + 手工验证证据；Step 5 输出变更摘要与收尾报告；Step 6 写入 daily.md 与项目记忆。
