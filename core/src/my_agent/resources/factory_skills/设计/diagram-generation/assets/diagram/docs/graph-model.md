# 统一图模型 `graph.json`（schema: vgraph/v1）

**所有产物都由这一份文件生成。** 不允许为 Mermaid 写一份、为 drawio 再写一份——那等于同一张图维护两份，改一处其余失真。

## 完整结构

```json
{
  "schema": "vgraph/v1",
  "meta": {
    "title": "订单系统架构图",
    "graph_type": "architecture",
    "purpose": "表达下单链路涉及的组件、职责与数据流向",
    "direction": "TB",
    "author": "",
    "date": "2026-09-09"
  },
  "groups": [
    {"id": "g1", "label": "接入层", "desc": "对外暴露能力的部分", "parent": null}
  ],
  "nodes": [
    {
      "id": "n1", "label": "Web 前端", "type": "service",
      "group": "g1", "layer": 0,
      "desc": "面向 C 端用户的下单页面",
      "note": ""
    }
  ],
  "edges": [
    {
      "id": "e1", "source": "n1", "target": "n2",
      "label": "HTTPS 下单请求", "type": "sync",
      "desc": "携带商品、数量与收货信息"
    }
  ]
}
```

## `meta`

| 字段 | 必填 | 说明 |
|------|------|------|
| `title` | ✅ | 图标题，用于 drawio 页名、SVG 标题、说明文档标题 |
| `graph_type` | ✅ | `architecture` / `flowchart` / `er` / `sequence` / `state` / `c4` |
| `purpose` | ✅ | 一句话说明这张图表达什么。写不出来说明需求没理解透，回去问 |
| `direction` | ⬜ | `TB`（自上而下，默认）/ `LR`（从左到右） |
| `author` / `date` | ⬜ | 署名与日期 |

## `nodes`

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 全局唯一，建议 `n1…n99`。边只认 id，不认 label |
| `label` | ✅ | 显示文字。**≤ 8 字优先**，长名称用换行标签会撑破图元 |
| `type` | ✅ | 语义类型，**必须从下表选取**，决定形状与配色 |
| `group` | ⬜ | 所属分组 id，用于画系统边界框 |
| `layer` | ⬜ | 层级序号（0 起）。不给则由布局引擎按拓扑推断 |
| `desc` | ✅ | 一句话解释这个节点是什么/干什么。**图形说明直接引用它**，不许留空 |
| `note` | ⬜ | 补充说明、约束、或待确认项 |

### 节点类型表

| type | 含义 | 形状 | 配色 |
|------|------|------|------|
| `actor` | 用户 / 角色 / 外部参与者 | 椭圆 | 灰 |
| `gateway` | 网关 / 负载均衡 / 入口 | 六边形感矩形（圆角） | 深蓝 |
| `service` | 应用服务 / 微服务 | 圆角矩形 | 蓝 |
| `component` | 系统内部组件 / 模块 | 矩形 | 靛 |
| `container` | C4 容器（应用 / 数据库） | 矩形 | 蓝 |
| `db` | 数据库 / 存储 | 圆柱 | 绿 |
| `cache` | 缓存 | 圆柱 | 橙 |
| `queue` | 消息队列 / 中间件 | 矩形（扁） | 紫 |
| `external` | 外部系统 / 第三方 | 矩形虚线边 | 灰 |
| `process` | 流程步骤 | 矩形 | 蓝 |
| `decision` | 判断 / 分支 | 菱形 | 黄 |
| `start` | 流程起点 | 圆角（小） | 深灰 |
| `end` | 流程终点 | 圆角（小） | 深灰 |
| `entity` | ER 实体 | 矩形 | 蓝 |
| `attribute` | ER 属性 | 椭圆 | 浅灰 |
| `state` | 状态 | 圆角矩形 | 蓝 |
| `note` | 批注 | 便签 | 黄 |

## `groups`（系统边界）

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 唯一，建议 `g1…g9` |
| `label` | ✅ | 边界名，如"接入层""数据层""外部依赖" |
| `desc` | ⬜ | 这个边界的职责 |
| `parent` | ⬜ | 父分组 id，支持嵌套（C4 常用） |

**这是"正确反映系统边界"的落地手段。** 需求里提到分层、子系统、内外之分，就必须建分组，不能只画一堆散节点。

## `edges`

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 唯一，建议 `e1…e99` |
| `source` / `target` | ✅ | **必须是已存在的 node id**。拼错就是悬挂连线，校验会拦 |
| `label` | ⬜ | 连线文字。要写"传什么/为什么"，如"HTTPS 下单请求"，不要只写"调用" |
| `type` | ⬜ | 线型语义，见下表 |
| `desc` | ⬜ | 这条连线承载什么，用于图形说明 |

### 连线类型表

| type | 含义 | 线型 |
|------|------|------|
| `sync` | 同步调用 / 请求 | 实线箭头（默认） |
| `async` | 异步消息 / 事件 | 虚线箭头 |
| `data` | 数据读写 / 数据流 | 粗实线箭头 |
| `return` | 响应 / 返回 | 虚线无箭头 |
| `assoc` | ER 关联（基数写在 label，如 `1:N`） | 实线 |
| `inherit` | 继承 / 泛化 | 实线空心箭头 |
| `flow` | 流程推进（流程图默认） | 实线箭头 |

## 各图类型的建模要点

### architecture 架构图
- 用 `groups` 表达分层（接入层 / 业务层 / 数据层 / 外部依赖）
- `layer` 显式给出，保证纵向分层正确
- 外部系统一律 `external`，第三方与自建必须视觉可分

### flowchart 流程图
- 必须有且只有一个 `start`；`end` 可以有多个
- 分支用 `decision`，**每条出边都要写 label**（如"是"/"否"、"金额 > 1 万"）
- 不要出现没有出边也没有入边的孤立步骤

### er ER 图
- 实体用 `entity`，关系用 `assoc` 边，基数写在 label：`1:N` / `N:M` / `1:1`
- 属性**不要**建成一堆 attribute 节点（会让图爆炸）；写在实体 `desc` 里即可
- 弱实体 / 关联表要显式建节点

### sequence 时序图
- 参与者用 `actor` 或 `service`，**按从左到右的期望顺序排列**
- 消息用边表达，**必须给 `seq` 字段**标明顺序（1,2,3…），否则时序会乱
- 自调用用 `source == target`

### state 状态图
- 状态用 `state`，**初态建议 id 前缀 `init`、终态 `final`**
- 转移的 label 写触发条件/事件，如"支付成功"

### c4 C4 容器图
- 用 `groups` + `parent` 嵌套表达系统边界 → 容器
- 外部系统放最外层，用 `external`

## 校验规则（check_graph.py 执行）

| 级别 | 规则 |
|------|------|
| **ERROR** | `source`/`target` 指向不存在的 node |
| **ERROR** | node / edge / group 的 id 重复 |
| **ERROR** | 缺少 `meta.title` / `meta.graph_type` / `meta.purpose` |
| **ERROR** | `graph_type` 不在六类之内 |
| **ERROR** | flowchart 缺 `start` 节点 |
| **ERROR** | sequence 图的消息缺 `seq` |
| **WARN** | 存在孤立节点（既无入边也无出边） |
| **WARN** | node 缺 `desc` |
| **WARN** | node `type` 不在类型表内 |
| **WARN** | 边的 `label` 为空（架构图建议写清传什么） |
| **WARN** | 标签超过 12 字（可能撑破图元） |

有 ERROR 时脚本退出码 1，**不许继续产出**。
