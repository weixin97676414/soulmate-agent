---
name: system-architecture
description: 系统架构设计与脚手架：目录结构、技术栈选型、规范配置、README/ARCHITECTURE 文档模板与安全可扩展性复核。触发场景：新项目立项、重构系统、搭架子、高层设计评审、design a system、architect this。
author: Soulmate Agent团队成员：岸
---

# 功能：系统架构设计

规范与模板：`assets/python-standards.md`、`assets/js-ts-standards.md`、`assets/security-checklist.md`、`assets/scaffolding.md`、`assets/system-architect-templates/`（README.md / ARCHITECTURE.md）。

## 适用场景
新项目立项、重构既有项目、讨论高层系统设计。触发：design a system、start a new app、architect this、review structure、系统设计、搭架子、技术栈选型。

## 步骤
1. **明确角色与产出**：以严格但务实的技术负责人身份，产出目录结构、技术栈建议、架构图（Mermaid）。
2. **项目脚手架**：按 `assets/scaffolding.md` 给出标准目录布局（Python / JS-TS）。
3. **技术栈选型**：按需求推荐（如 Flask vs FastAPI、React vs Vue），说明取舍。
4. **代码规范**：提供 `pylintrc` / `.eslintrc` / `.editorconfig` 等 lint/格式配置，并参照 `assets/system-architect-templates/` 中的文档模板。
5. **文档**：用模板生成 `README.md` 与 `ARCHITECTURE.md`（组件、数据流、部署、决策）。
6. **安全与可扩展性复核**：对照 `assets/security-checklist.md`。

## 规则
- 始终优先**安全**与**可扩展性**。
- 偏好**极简**（YAGNI）。
- 默认用 **Docker** 容器化。
- 所有代码示例遵守严格 lint 规则。

## 输入输出
- 输入：需求、约束、团队偏好。
- 输出：目录结构、技术栈建议、架构图、规范配置模板、README/ARCHITECTURE 文档。

## 注意事项
- 选型要结合团队能力与约束，不追新。
- 架构图用 Mermaid，保持与代码一致。
- 规范模板是起点，须按项目调整，不要原样硬套。

## 可复用示例
> 「做一个内部数据看板」→ 建议 React + Vite（前端）/ FastAPI + PostgreSQL（后端）+ Docker Compose；给出 `frontend/`、`backend/app/{api,core,models,schemas,services}` 目录；附 `.eslintrc.json` + `.pylintrc` + `ARCHITECTURE.md`（组件图 + 数据流 + 部署 + 决策记录）。
