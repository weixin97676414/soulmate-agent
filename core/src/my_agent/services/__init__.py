"""**窄服务**：把"某个子系统能做的事"包成一个对象，交给路由与技能用。

## 为什么要这个包（审计 L-01）

`AppRuntime` 是 1760 行的"上帝对象"：所有路由 `get_runtime(request)` 之后就能顺手摸到
任意子系统（`usage_repo` / `audit_repo` / `task_scheduler` / `mcp` / `config` …）。

问题不是"能不能"，而是**没有任何地方规定"这个路由需要什么"**：
改一个仓库的方法签名，得全仓搜谁在用它；而路由里那段取数/组装的逻辑
既不属于 HTTP 层，也不属于仓库层，于是只能待在路由文件里（正是 H-06 的另一副面孔）。

窄服务的做法：路由只认识 `runtime.usage` 这一个对象 —— **它需要什么，接口上就有什么**。
`AppRuntime` 随之退化为**组合根**（构造并接线这些服务）。

## 进度：用量与审计已**走完**过渡（第 98 / 101 / 102 批）

`usage`（读 + 写：统计查询 / `record` / `price_of`）与 `audit`（读 + 写：查询 / `record` / `op`）
已整块搬进这里，**调用点全部切过来**，`AppRuntime` 上那几个同名转发方法也删掉了。

⚠️ 删除转发是**有意的，别加回来**：留着它们的时候它们是"旧入口"，
调用点切完之后继续留着，只会有人接着走旧路 —— 服务里那份实现就永远成不了唯一真相。
需要审计/用量的调用方该拿的是 `runtime.audit` / `runtime.usage` 这两个服务本身。

⚠️ 做法仍然有效，下一个子系统照它走：**实现搬进服务 → runtime 保留同名转发（调用点零改动）
→ 单独一批把调用点切过去 → 删转发**。搬运与改调用点分在两批，
回归时才分得清是哪一步引起的（第 102 批就是"只切调用点"的一批）。

⚠️ 还剩两块大的在 runtime 上：**记忆**（`memory_for` / `archive_turn`，含群聊归档）
与**调度**（`task_scheduler` / `task_store`）。

## 已有的同类先例

`CalendarService`（`calendar/service.py`）与技能那套 `ctx.service("team"/"buddy"/"history")`
本来就是"把 runtime 成员包成门面"的形态；这个包只是把同一件事**规定下来**。
"""

from __future__ import annotations

from .audit import AuditService
from .usage import UsageService

__all__ = ["AuditService", "UsageService"]
