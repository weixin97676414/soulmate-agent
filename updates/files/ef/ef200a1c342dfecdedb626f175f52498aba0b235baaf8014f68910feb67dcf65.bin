# 本周追踪事项 Excel 规格

> 适用：周期性例会（周例会/月度例会）产出物之二——追踪事项表。由 `scripts/build_action_tracker.py` 从
> 生成 Word 纪要的同一份 content JSON 直接生成，**不从 Word 反向猜测或人工重录**。

## 一、数据源与列顺序

Excel 仅读取 content JSON 中的 `action_items`，与 Word 纪要"本周待办事项"同源同构。

| 列 | 字段 | 规则 |
|---|---|---|
| A | 编号 | 与 Word 一致，如 `本周-01` |
| B | 会议安排事项 | 与 Word 一致 |
| C | 负责人 | 每行一个主负责人；用于筛选 |
| D | 追踪人 | 与 Word 一致 |
| E | 完成时限 | 与 Word 一致，不自动改口径 |
| F | 状态 | 下拉选项：未启动、进行中、阻塞、完成、取消 |
| G | 来源 | `承接上周-XX` 或 `本周新增` |
| H | 备注 | 与 Word 一致 |

`action_items` 未提供状态时，F 列默认写"未启动"。若输入为"已完成"，仅在 Excel 中规范化为"完成"。

## 二、可用性与样式

- 工作表名：`本周追踪事项`。
- 首行为表头，冻结窗格 `A2`。
- 将数据区创建为 Excel Table，开启所有列的筛选按钮，可按单一负责人筛选。
- 事项、来源、备注自动换行，内容顶端对齐。
- 状态列在第 2–1000 行预置下拉，方便继续新增事项。
- 条件格式覆盖 `A2:H1000`：当同行 F 列精确等于"完成"时，整行填充浅绿色 `#E2F0D9`。
- OOXML 颜色必须写成不透明 ARGB `FFE2F0D9`；禁止使用透明 ARGB `00E2F0D9`。

## 三、交付前校验

1. Excel 数据行数必须等于 Word 本周待办条数。
2. 逐行比对编号、事项、负责人、追踪人、完成时限、来源、备注。
3. 用 Excel 实际选择一条状态为"完成"，确认 A–H 整行变浅绿；改回其他状态后浅绿消失。

## 四、调用方式

```bash
python scripts/build_action_tracker.py --content content.json --out 甲方A-本周追踪事项-YYYYMMDD.xlsx
```

- `--content`：与 `weekly_minutes_docx.py --content` 相同的 JSON。
- `--out`：落点与当期 Word 纪要相同目录，使用相同日期和版本后缀（如有）。
- 脚本内置 `validate_workbook()`，保存后自动复检表头/行数/筛选/下拉/条件格式，任一失败即报错。
