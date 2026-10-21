---
name: diagram-generation
description: 可视化图形生成：用统一图模型 graph.json 一次建模、多格式输出可编辑的架构图/流程图/ER/时序/状态/C4 图（Mermaid/PlantUML、drawio/Excalidraw、SVG/PNG），并附图形说明。触发场景：画架构图、流程图、ER 图、时序图、状态图、C4 图、生成 drawio/Excalidraw、导出 mermaid/PlantUML/SVG/PNG、要可编辑的图。
author: Soulmate Agent团队成员：岸
---

# 可视化图形生成（架构图/流程图/ER/时序/状态/C4）
## 适用场景

- 根据业务描述或系统需求，生成可编辑的架构图、流程图、ER 图、时序图、状态图、C4 容器图
- 需要同时拿到：可嵌文档/进 Git 的结构化文本（Mermaid/PlantUML）、可拖拽二次修改的图形文件（drawio/Excalidraw）、静态图（SVG/PNG）
- 触发词：画架构图、画流程图、画 ER 图、画时序图、画状态图、C4 图、系统架构图、部署架构图、数据流程图、实体关系图、生成 drawio、生成 Excalidraw、导出 mermaid、导出 PlantUML、导出 SVG、导出 PNG、可编辑的图、图转可编辑、画图、出图

## 四条硬规则

1. **统一图模型是唯一真相源** —— 所有产物都由同一份 `graph.json` 生成；禁止为不同格式各写一份图。
2. **可编辑性是交付底线** —— 只给 PNG = 交付不合格；结构化文本与可编辑文件至少各出一种。
3. **节点必须有语义类型** —— 每个节点标 `type`（service / db / queue / external / actor / decision / entity / state…），由样式系统统一配色与形状；禁止随手指定颜色。
4. **图要配说明** —— 必须输出「图的含义 + 关键节点解释 + 关键连线解释」。

## 步骤

### Step 1 · 分诊图类型

| 图类型 | 适用场景 | 信号词 |
|--------|----------|--------|
| `architecture` 架构图 | 系统由哪些组件构成、如何协作 | 系统架构、部署、组件、服务划分、技术选型 |
| `flowchart` 流程图 | 业务流程、判断分支、审批流 | 流程、审批、如果…则、环节、步骤 |
| `er` ER 图 | 数据实体与关系 | 表结构、实体、字段、一对多、关联 |
| `sequence` 时序图 | 跨系统/对象的调用时序 | 调用链、请求顺序、接口时序、交互过程 |
| `state` 状态图 | 单个对象的状态流转 | 状态、流转、生命周期、状态机 |
| `c4` C4 容器图 | 分层表达系统上下文与容器 | 系统上下文、容器图、边界、外部依赖 |

复杂需求可拆多张图（如先架构图、再核心链路时序图），**每张图单独建一份 graph.json**。不确定就问，不要瞎猜。

### Step 2 · 建模：填 graph.json

复制模板 `assets/diagram/graph-model.json` 后填写；schema 见 `assets/diagram/docs/graph-model.md`。

- **节点**：`id` 全局唯一；`label` 简洁（≤8 字优先）；`type` 必须从类型表选；`desc` 一句话解释。
- **边**：`source`/`target` 必须指向已存在的节点 id；`label` 写"传什么/为什么"（如"HTTPS 下单请求"），不写"调用"。
- **分组**：用 `groups` 表达系统边界（接入层/业务层/数据层）。
- **分层**：`layer` 决定纵向排布；不给则由布局引擎自动推断。

### Step 3 · 产出：一次建模，多格式输出

```bash
# 0. 校验（必跑，有 ERROR 不许往下走；仅依赖标准库）
python3 scripts/diagram/check_graph.py graph.json

# 1. 结构化文本（嵌 Markdown / 进 Git）
python3 scripts/diagram/gen_mermaid.py graph.json -o out/diagram.mmd
python3 scripts/diagram/gen_mermaid.py graph.json --format plantuml -o out/diagram.puml

# 2. 可编辑文件（图形化工具打开二次修改）
python3 scripts/diagram/gen_drawio.py graph.json -o out/diagram.drawio
python3 scripts/diagram/gen_excalidraw.py graph.json -o out/diagram.excalidraw

# 3. 静态图
python3 scripts/diagram/render_svg.py graph.json -o out/diagram.svg   # 自渲染，零依赖
# PNG 转换命令见 assets/diagram/docs/export-guide.md
```

然后按 `assets/diagram/图说明.md` 骨架写图形说明，与图一起交付。

## 脚本清单

| 脚本 | 作用 | 何时用 |
|------|------|--------|
| `scripts/diagram/check_graph.py` | 校验：id 唯一、边引用有效、无孤立节点、type 合法、说明齐全 | 建模后、产出前**必跑** |
| `scripts/diagram/gen_mermaid.py` | graph.json → Mermaid / PlantUML 文本 | 嵌文档或进 Git |
| `scripts/diagram/gen_drawio.py` | graph.json → .drawio（mxGraph XML，含自动布局） | 需图形化二次修改（**首选**） |
| `scripts/diagram/gen_excalidraw.py` | graph.json → .excalidraw（文本绑定容器） | 需草图风格评审 |
| `scripts/diagram/render_svg.py` | graph.json → SVG（自研布局引擎，零依赖） | 只读展示 |

## 参考文档（在 assets 中）

| 文档 | 内容 |
|------|------|
| `assets/diagram/docs/graph-model.md` | 统一图模型 schema：字段定义、类型枚举、六类图建模要点 |
| `assets/diagram/docs/type-guide.md` | 六类图的选型、建模范式与常见错误 |
| `assets/diagram/docs/style-system.md` | type → 形状/配色/线型映射，命名与标签规范 |
| `assets/diagram/docs/export-guide.md` | 各格式打开方式、PNG 转换命令、嵌入 Markdown/Git 的做法 |
| `assets/diagram/graph-model.json` | 空模型模板 |
| `assets/diagram/图说明.md` | 图形说明骨架 |

## 输入输出

- **输入**：业务描述 / 系统需求 / 已有 graph.json。
- **输出**：至少一种结构化文本 + 一种可编辑文件 +（可选）SVG/PNG + 图形说明。

## 注意事项

- **PNG 需外部工具**：本技能自渲染 SVG；PNG 由 drawio 桌面版 / `npx @mermaid-js/mermaid-cli` 转换（脚本只给命令不代跑）。
- **自动布局非完美**：分层布局对 DAG 效果好；含大量回边或密集交叉的复杂图，建议在 drawio 里微调。
- **SVG 字体宽度按估算**：中文按全角、英文按半角估算，极长标签可能溢出框，生成后手调。
- 所有脚本仅依赖 Python 标准库，无需额外安装。

## 交付前自检

- [ ] 先跑了 `check_graph.py` 且零 ERROR？
- [ ] 至少出一种结构化文本 + 一种可编辑文件？
- [ ] 节点均来自业务描述，无凭空捏造组件？
- [ ] 系统边界（分组）反映描述层次？
- [ ] 每个节点 `type` 从类型表选取？
- [ ] 边的 `label` 写明"传什么/为什么"？
- [ ] 附了图形说明（含义 + 关键节点 + 关键连线）？
- [ ] 四种产物由**同一份** graph.json 生成？

## 可复用示例

```bash
python3 scripts/diagram/check_graph.py graph.json --md 校验报告.md
python3 scripts/diagram/gen_mermaid.py graph.json -o out/system.mmd
python3 scripts/diagram/gen_drawio.py graph.json -o out/system.drawio
python3 scripts/diagram/render_svg.py graph.json -o out/system.svg
```
