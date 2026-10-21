---
name: debugging-and-bug-fixing
description: 零回归 Bug 修复与系统性根因调试：12 条铁律 + 4 门/5 门确认闸 + Phase 0-6 全流程，含复现证据、影响链、副作用预测、回归验证、知识沉淀与自省。触发场景：debug、报错、异常、堆栈、崩溃、测试失败、生产 bug、not working、fix bug、根因分析。
author: Soulmate Agent团队成员：岸
---

# 功能：Bug 修复与系统性调试

## 适用场景
任何技术问题：测试失败、生产 bug、意外行为、性能问题、构建失败、集成问题、编译/运行时异常、依赖冲突。触发词：debug、报错、异常、堆栈、崩溃、not working、broken、fix bug、修 bug、为什么 X 不工作。
不适用：新功能（走开发流程）、纯代码审查（走 code-review）、性能优化（走性能基线）。

## 铁律（不可违反）
```
1  根因必须先过 4 门：可复现 + 因果 + 可逆 + 机制可指认
2  范围必须先过 5 门：消费者 + 契约 + 不变量 + 调用点 + 重复实现扫描
3  必须追踪影响链（代码→数据→时间→事件）+ 修前全仓扫同模式
4  必须预测副作用 + 检查盲区
5  修复后必须跑回归验证（功能 + 性能 + 并发 + 全部影响层级）
6  必须验证修复在运行时真正生效（清 __pycache__ + 重启 + 走一遍代码路径）
7  框架行为先读源码，不轻信文档/注释/假设
8  UI bug 必须先取运行时证据（截图 + DevTools DOM/Console + 用户复现步骤），不得只读代码就修
9  未输出 Bug Summary + 通过 code-review + 更新知识文件 + 完成自省 = 未完成
10 动手前先判定问题所在层：代码 bug？缺配置？架构错？AI 能力？在根层修，不在症状层修
11 模式匹配（正则/字符串/名称查找）必须检查边界条件（词边界/锚点/精确匹配）
12 动手前先搜 bug 模式库 + bug 记录，复用已知修法与历史上下文
+ 未经根因调查不许修复；同一问题修 3 次仍失败 → 停止并质疑架构，与用户讨论，不得再叠加第 4 次修补
```

## 工作流
```
Phase 0 分诊 → 定严重度 P0–P3 + 层级 Trivial/Standard/Complex
   ├ Trivial → 快速修复 → 测试 → 完成
   ├ Standard ┐
   └ Complex ─┘
Phase 1 复现（必须有证据）
Phase 2 根因分析（2A 假设阶梯 + 5 Whys / 2B 搜知识库 / 2C 影响链 / 2D 同模式全仓扫描）
Phase 3 范围 + 预测（3A 5 门 / 3B 副作用预测 + 盲区检查 / 3C 方案比较）
Phase 4 修复（最小改动，尽量 ≤50 行）
Phase 5 验证 + 审查（回归 + 运行时部署验证 + Bug Summary + code-review）
Phase 6 知识沉淀 + 自省
```

### Phase 0 分诊
- **严重度**（控制深度）：P0 生产宕机/数据丢失/安全（全流程，4h 升级）；P1 核心功能壞/数据损坏（全流程，8h）；P2 非核心/UI（跳过 3C）；P3 外观/边角（跳过 2C/2D/3A–3C）。
- **层级**：Trivial（拼写/配置/单行，无行为变更）→ 快速修复；Standard（逻辑 bug，1–3 文件，无跨模块风险）；Complex（跨模块、>3 文件、共享工具、schema 变更、多进程）→ 全流程。误判为 trivial 但动了 >1 文件或改行为 → 升级为 Standard。
- 自动初始化知识文件：`assets/bug-fixing-references/bug-patterns.md`、`bug-records.md`、`blind-spots.md`，存在则查、缺则修后建。

### Phase 1 复现（无证据不修）
| Bug 类型 | 需要的证据 |
|---|---|
| 后端错误 | 堆栈 + 请求/响应 |
| 前端 UI | 截图 + 浏览器 console + 用户复现步骤 |
| 性能 | 前后指标 + profiler 输出 |
| 间歇性 | 时序条件 + 频率估计 |

证据包模板：触发条件（输入/环境/时序）、可观测输出（完整报错/日志/截图）、关联 ID（requestId/traceId/sessionId）。

### Phase 2 根因
- 假设阶梯：列 3–5 条假设 → 按可能性排序 → 每条可证伪 → 先跑「否定」测试 → 一次只测一个 → 5 Whys 到根因。
- **4 门确认**：可复现 / 因果（最小改动使 bug 消失）/ 可逆（还原使 bug 重现）/ 机制（能指认确切代码路径）。
- 2C 影响链四维：代码（本文件→直接→间接→深层调用者）、数据（DB/文件/缓存是否损坏、是否需修复脚本）、时间（何时引入、暴露多久、影响多少用户）、事件（消息队列/WebSocket/后台 worker）。
- 2D：`rg -n "function_name\|similar_pattern" --glob "*.{ts,tsx,py,js}"` 全仓扫同模式，不只修报告的那个文件。

### Phase 3 范围 + 预测
- **5 门**：消费者清单 / 契约清单 / 不变量检查 / 调用点枚举 / 重复实现扫描。
- 副作用预测：变更蓝图 → 影响涟漪 L0(代码)→L1(模块)→L2(功能)→L3(系统)→L4(用户) → 读 `blind-spots.md` 逐项检查 → Go/No-Go。
- >10 行的 Complex 改动做方案比较（改动行数/影响范围/回归风险/可否回滚）。

### Phase 4 修复
- 最小改动（尽量 ≤50 行）、一次只改一个、不捆绑无关修复。
- **层级规则**：参数/配置问题 → 改配置或参数传递；单组件问题 → 改该组件；多组件同问题 → 改框架/基类；文档与代码不一致 → 两侧同步。
- 模式匹配加边界（词边界/锚点/精确匹配）。
- DB schema 变更 → `cd backend && alembic revision --autogenerate -m "..."`。

### Phase 5 验证 + 审查
- 回归：功能（单元/集成/API/E2E/手动）、性能（无 N+1、无泄漏、响应时间不增）、并发（线程安全、原子操作、无竞态）；测整条影响链 L0–L3。
- 运行时部署验证：清 `__pycache__` → 重启服务（PID 变化）→ 健康检查（如 `/docs` 返回 200）→ 走一遍修复的代码路径。
- 输出 Bug Summary（症状/根因/修复/改动文件/严重度）→ 跑 code-review → 有问题则修后再验。

### Phase 6 沉淀 + 自省
- 更新 `bug-records.md`（每次修复）、`bug-patterns.md`（新模式/新修法）、`blind-spots.md`（新盲区）。
- 自省 6 维打分（1–5）：首次正确率 / 范围准确度 / 最小改动 / 副作用预测 / 根因深度；合计 /25。出现回归时做「回归尸检」（原 bug / 新 bug / 为何没预测到 / 归类）。

## 输入输出
- 输入：报错/异常/复现步骤/日志/相关代码。
- 输出：Bug Summary + 回归验证报告 + code-review 结论 + 自省评分；必要时修复脚本、迁移文件。

## 注意事项
- 反模式（禁止）：无 RCA 就修；只列一个假设就修；只读代码修 UI bug；跳过消费者清单；测试过但服务跑旧代码；只修一份漏掉重复实现；无边界模式匹配；改了模型没出迁移；用全流程修拼写；跳过自省。
- **技术栈排障速查**：
  - Node/TS：`node --version && npx tsc --version`；`npm ls <pkg>`、`npm outdated`；`rm -rf node_modules && npm install` / `npm cache clean --force`。
  - Python：`python --version && which python`、`pip list | grep <pkg>`、`pipdeptree -p <pkg>`、`pip install --force-reinstall <pkg>`。
  - Go：`go version`、`go env GOPATH GOROOT`、`go mod graph | grep <pkg>`、`go mod tidy`。
  - Rust：`rustc --version && cargo --version`、`cargo tree -p <crate>`、`cargo clean && cargo build`。
- 常见根因速查：类型错误从第一条改起、导入错误查路径/大小写/`__init__.py`、`Cannot read property of undefined` 查异步未加载/可选链、浮点不直接比较用 epsilon、异步并发查竞态、平台差异查路径分隔符与 CRLF/LF。
- 「没有根本原因」的结论须谨慎：95% 的情况是调查不完整；确属环境/时序/外部时，记录调查过程并加处理（重试/超时/日志/监控）。
- 详细清单见随技能复制的 `assets/bug-fixing-references/`（backend-patterns / frontend-patterns / bug-patterns / blind-spots / system-rca / regression-matrix）。

## 可复用示例
> 现象：`test_divide_by_zero` 报 `TypeError: divide is not a function`。
> Phase 0：P1、Standard。Phase 1：拿到完整堆栈 + Node 版本。Phase 2：堆栈指向导入处 → 假设阶梯列出「导入路径错/名称覆盖/调用过早」，用最小改动逐个否定 → 命中「默认导出 vs 具名导出不匹配」，4 门通过。Phase 3：全仓 `rg "divide"` 发现另一处相同写法一并修。Phase 4：改导入（1 行）。Phase 5：`pytest` 全绿、清缓存重启、走一遍路径。Phase 6：记录到 `bug-records.md`，自省 22/25。
