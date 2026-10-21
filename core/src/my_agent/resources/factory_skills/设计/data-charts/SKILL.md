---
name: data-charts
description: 数据图表生成：把表格数据文件转成独立交互式 ECharts HTML（32 类图、3 主题、全离线），先出数据画像再选型，并附基于事实卡的文字解读。触发场景：有表格数据要出图、数据可视化、生成图表、chart、make a graph、把表格渲染成交互式 HTML 图表。
author: Soulmate Agent团队成员：岸
---

# 数据图表生成
## 适用场景

- 用户提供/指向一个表格数据文件（CSV/TSV/TXT/XLSX/XLS/JSON），要求出图、可视化、生成图表
- 提到「画图 / 出图 / 生成图表 / 数据可视化 / chart / make a graph」；想把表格渲染成交互式 HTML 图表
- **不触发**：要带结论叙事的报告/周报/复盘/汇报文档；没有数据文件；需要后端的 dashboard；图片/音频/视频等非表格内容；市级/区县级地图（需自备 GeoJSON）

## 能力概览

把数据文件转成**独立交互式 ECharts HTML**：32 类图表、3 套主题（default/classic/dark），全离线无需 CDN。出图前可取**数据画像**（每列 dtype/基数/缺失/样本/统计、实体粒度、候选洞察信号、疑似非数据行）。每张图内置事实卡（`plot_stats` + `data_preview`），其数值是解读时唯一可引用的数字。本技能负责出图与算事实，**不产出书面报告或叙事文档**。

## 步骤

### A. 用户意图明确（"对比各地区销售额""看月度趋势""占比构成"）
直接按选型表挑图型 + 轴 + 聚合口径，出图。**不要**为了走流程去跑 profile。若数据撑不起该意图（要趋势却没有时间列），如实说明并给可行替代，不要硬画。

### B. 用户只给了数据，没说想看什么（最高频）
1. `python3 assets/chart-engine/scripts/cli.py <file> --profile`（只读不渲染不落盘），拿到每列 dtype/基数/缺失率/样本/统计、`grain`、`signals`、`row_quality`。
2. **由 agent 决定**出哪 1–3 张图：读 `columns` 自行判断哪列是 ID/维度/度量，结合 `signals` 挑发现，定图型 + 轴 + 聚合口径，直接出图（`--transform-code` 聚合 + `--title` 结论 + `--annotation` 解读）。交付时说明"为什么是这几张"。

> 优先出图的信号：`divergent_category`（某类别逆势变化）与 `trend`。
> **MUST NOT** 把选型责任推回用户（"你想看趋势、对比还是占比？"）——选型是 agent 从客观事实自行判断的活。

### 交付解读（MUST）
交付每张图时附一段**由 LLM 写的文字解读**，用 `--annotation` 注入 HTML：结论 → 证据 → 边界（2–4 句，结论先行）。每个数字必须能在 `plot_stats`/`data_preview`/`profile.signals` 找到出处。`--title` 写结论式短语（主谓宾+数值），范围/来源放 `--subtitle`。

## 命令示例

```bash
# 环境自检
python3 assets/chart-engine/scripts/cli.py --doctor

# 数据画像（意图不明确时先跑）
python3 assets/chart-engine/scripts/cli.py data.xlsx --profile

# 1 分类频次 → pie/bar（最高频场景）
python3 assets/chart-engine/scripts/cli.py data.xlsx bar --title "标题" --output-dir ./out \
  --x-axis name --y-axis value \
  --transform-code "result = df['类别列'].fillna('未标注').value_counts().rename_axis('name').reset_index(name='value')"

# 分组聚合 → bar
python3 assets/chart-engine/scripts/cli.py data.xlsx bar --title "标题" --output-dir ./out \
  --x-axis 分组列 --y-axis 数值列 \
  --transform-code "result = df.groupby('分组列')['数值列'].sum().reset_index()"

# 多图批量（≥2 张图 MUST 批量；transform 含中文/引号时写 JSON 文件，避免 shell 转义）
python3 assets/chart-engine/scripts/cli.py data.xlsx --sheet "Sheet1" \
  --charts-file charts.json --output-dir ./out
```

`charts.json` 每项：`type`（必填）+ `title`/`x_axis`/`y_axis`（字符串或数组）/`transform_code`（单图级）/`label_col`/`color_by`/`annotation`。

**依赖**：Python 3.11+；`pandas>=3.0.1,<4`、`numpy>=2.4.3,<3`、`openpyxl>=3.1.5,<4`、`xlrd>=2.0.1,<3`（见 `assets/chart-engine/scripts/requirements.txt`）；ECharts 已离线捆绑（`assets/chart-engine/assets/`：echarts.min.js / echarts-wordcloud.min.js / echarts-liquidfill.min.js / china.json / world.json）。

## 契约（8 条 MUST）

1. 列名解析后规范化：转小写、特殊字符→`_`（如 `总学时`→`总_学时`），中文保留；`--x-axis`/`--y-axis`/transform 必须引用规范化后的列名。
2. transform 沙箱：可用变量仅 `df`/`pd`/`np`；支持多语句（`;` 或换行）；必须产出名为 `result` 的 DataFrame；禁止 import/open/try/类定义（黑名单 + AST 白名单强制校验）。
3. pie/bar/treemap/funnel 等按「1 个分类列 + 1 个数值列」读数据；分类频次图先用 transform 聚合成这两列。
4. 成功时 stdout 含 `success`/`html_path`/`chart_type`/`title`/`source_rows`/`plotted_rows`/`unique_entities`/`data_rows`/`data_preview`/`annotation_source`/`plot_stats`；`assumptions`/`advisories` 仅非空时出现。
5. **校对口径读 stdout 的 `data_preview` + `data_rows`**，不要打开 HTML 搜数据；核对辅助列用 transform 里 `print(...)`（走 stderr）或 `--dry-run`。
6. **聚合对账读 `source_rows`/`plotted_rows`/`unique_entities`**；判断"是否该聚合"要配合图型语义，机械判据是 `advisories` 里的「疑似未聚合」。
7. **意图不明确时 MUST 先跑 `--profile`**。
8. **交付前 MUST 读 `assumptions` + `advisories`**，并在交付语里呼应。

## Hard Constraints（MUST）

1. MUST 走 CLI 工作流（`data_parser.py` → `cli.py`），不要自写脚本替代。
2. 脏表头 MUST 用 CLI flags（`--skiprows N` / `--header-row N` / `--drop-rows 0,1` / `--sheet`）；N 先无 flags 跑一次看原始布局再定，不拍脑袋。两行表头 + 分值行走三段式：`--profile` 定位 → `--drop-rows`/transform 丢行 → 重跑 `--profile` 确认干净。
3. 列重命名/重塑/聚合 MUST 用 `--transform-code`。
4. 改轴名/系列名 MUST 用 `--x-name`/`--y-name`/`--series-name(s)`，不要靠改列名。
5. 不支持的场景 MUST 先说明再给建议，不得静默绕过。
6. MUST NOT 硬编码绝对路径。
7. 不要主动传 `--lang`（CLI 自动跟随数据语言）。
8. MUST 附文字解读并通过 `--annotation` 注入；确认 `annotation_source` 为 `'user'`。
9. MUST 显式传 `--output-dir`（默认 `./charts_output` 随 cwd 落盘，用户不易发现）。
10. `{skill_base}` = 本功能包根目录 `assets/chart-engine/`；命令统一用 `python3 assets/chart-engine/scripts/cli.py`。脚本按自身位置解析同级的 `assets/`，故**不可**把 `scripts/` 与 `assets/` 拆开放置。

## 选型表（32 类，摘要）

| ID | 适合 | 触发关键词 | y_axis | 数据格式 |
|----|------|-----------|:------:|----------|
| line | 时间趋势 | trend, 趋势, 变化, 走势 | 1~N | 1 类/时间 + 1~N 数值 |
| bar | 类别对比 | compare, 对比, 排名, 差异 | 1~N | 1 类 + 1~N 数值 |
| area | 累计变化 | cumulative, 累计 | 1~N | 1 类/时间 + 1~N 数值 |
| pie | 占比构成 | share, 占比, 构成, 比例 | 1 | 1 name + 1 value |
| scatter | 相关性 | correlation, 相关, 散点 | 1 | 2 数值，或 1 类 + 1 数值 |
| radar | 多维对比 | 多维, 综合, 雷达 | N | 1 指标 + N 数值 |
| heatmap | 密度/交叉 | 密度, 交叉, 矩阵, 热力 | 1~N | 1 类 + 1~N 数值 |
| treemap | 层级占比 | 层级, 嵌套 | 1 | 1 name + 1 value |
| graph | 实体关系 | 关系, 网络, 拓扑 | special | source + target (+ value) |
| boxplot | 分布/离群 | 分布, 离群, 四分位 | N | N 数值 |
| waterfall | 增量变化 | 增量, 瀑布 | 1 | 1 类 + 1 数值（增量） |
| gauge | KPI 进度 | 进度, KPI, 达成 | 1 | 1 数值（用均值） |
| sankey | 流向转移 | 流向, 流量, 转移 | special | source + target + value |
| funnel | 转化率 | 转化, 漏斗, 流失 | 1 | 1 name + 1 value |
| sunburst | 单层占比 | 占比, 比例 | 1 | 1 name + 1 value |
| wordcloud | 词频关键词 | 词频, 关键词, 词云 | 1 | 1 name + 1 value |
| histogram | 分布形状 | 分布, 直方图 | 1 | 1 数值列 |
| stacked_bar | 堆叠构成 | 堆叠, 构成 | 1~N | 1 类 + 1~N 数值 |
| bubble | 三变量相关 | 气泡, 三变量 | 2 | 2 数值 + 1 size |
| pareto | 二八分析 | 帕累托, 二八 | 1 | 1 类 + 1 数值 |
| combo | 双轴对比 | 双轴, 组合 | 1~N | 1 类 + 1 bar + 1~N line |
| venn | 集合重叠(2~3) | 交集, 重叠, 韦恩 | 1 | 1 name + 1 value；交集行命名 `A∩B` |
| mindmap | 层级想法 | 思维导图, 脑图, 大纲 | 1 | 1 parent + 1 child |
| orgchart | 组织架构 | 组织架构, 汇报关系 | 1 | 1 parent + 1 child |
| liquid | 百分比/进度 | 水波, 百分比, 完成率 | 1 | 1 数值（用均值） |
| spreadsheet | 原始表格 | 表格, 明细, 清单 | N | 任意列 |
| map | 地理着色 | 地图, 地区, 省份, 地域 | 1 | 1 地区名 + 1 数值（默认中国省级） |
| lines | 路线/迁徙 | 航线, 迁徙, 流向地图 | special | source + target (+ value) |
| effect_scatter | 动态散点 | 涟漪散点, 动态散点 | 1 | 2 数值，或 1 类 + 1 数值 |
| calendar | 日历热力 | 日历热力, 每日活跃 | 1 | 1 date + 1 数值 |
| pictorial_bar | 象形柱 | 象形柱, 图标柱 | 1~N | 1 类 + 1~N 数值 |
| theme_river | 主题河流 | 主题河流, 事件演化 | 1~N | 1 date + 1~N 数值 |

> `gauge`/`liquid` 要出"达成率"必须传 `--target <目标值>`，否则 `plot_stats.achievement` 为 `null`。
> `graph`/`sankey`/`lines` 由 `--x-axis`(source) + `--y-axis`(target) 显式指定；scatter/bubble/boxplot 身份列用 `--label-col`。

## Transform 常见模式

- 长转多系列：`result = df.pivot_table(index='<time>', columns='<category>', values='<value>', aggfunc='sum').reset_index()`
- 长转饼（筛选）：`result = df[df['metric']=='revenue'][['category','value']].rename(columns={'category':'name'})`
- 宽转长：`result = df.melt(id_vars=['date'], var_name='name', value_name='value')`
- 聚合转柱：`result = df.groupby('<category>')['<value>'].sum().reset_index()`
- 重命名列：`result = df.rename(columns={'来源':'source','去向':'target','金额':'value'})`
- 算增量转瀑布：`tmp = df.copy(); tmp['delta'] = tmp['profit'].diff().fillna(tmp['profit'].iloc[0]); result = tmp[['month','delta']]`
- 合并单元格前向填充：`result = df.ffill()`
- 丢非数据行：`result = df.drop(index=[0,1])`（位置由 `--profile` 给出）

## Exit Criteria

- ✅ 成功：stdout `{"chart": {"success": true, ...}}`（多图 `{"charts": [...], "summary": ...}`），`html_path` 指向文件存在非空 → 用同一 stdout 校对口径后附解读交付。
- ℹ️ `--dry-run` 不算交付（`html_path` 为 null、不落盘），仅用于试错。
- ❌ 失败：`success:false` 或 exit 1 → 读 `error.details.suggestion` 修正后重试，**同一环节最多重试 2 次**。
- 🛑 仍失败（唯一必须用户介入点）：把 `code_name`/`suggestion`/已尝试修复如实报告并给建议。**不得**静默改用自写脚本兜底。

## 注意事项

- 解读的每个数字必须有出处；`x_cardinality` 是去重个数（x 是「姓名」就说「59 名学生」）。
- `advisories` 出现「疑似未聚合」时，先按提示聚合再写解读，否则引用的是行级值，结论会错。
- 完整规范（全参数、flags 语义、多图/多文件细节、错误码表、FAQ）见 `assets/chart-engine/docs/REFERENCE.md`。

## 可复用示例

```bash
# 画像 → 出 2 张图 → 带解读交付
python3 assets/chart-engine/scripts/cli.py sales.xlsx --profile
python3 assets/chart-engine/scripts/cli.py sales.xlsx bar --output-dir ./out \
  --title "华南 4 月起销售额腰斩" --subtitle "2026 年 1–6 月，按大区" \
  --x-axis 大区 --y-axis 销售额 \
  --transform-code "result = df.groupby('大区')['销售额'].sum().reset_index()" \
  --annotation "华南 4 月起销售额腰斩（由 156 万降至 72 万，plot_stats 口径），其余三区同期仍增长；口径为按大区求和，来自 1–6 月明细。"
```
