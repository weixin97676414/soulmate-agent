"""Excel 相关技能：读取、写入、聚合分析。

**为什么只用 openpyxl 不用 pandas**：pandas 会连带 numpy，是打包体积与
首次启动时间的大头（见开发计划风险表）。本技能需要的读取与聚合用标准库
加 openpyxl 就能完成，代价是代码稍多，但换来的是安装包小、启动快。

所有路径都经过 ``ctx.resolve_input_file`` / ``ctx.artifact_output``，
保证不会越出白名单目录。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ....errors import SkillExecutionError
from ....skill.base import BaseSkill, SkillContext
from ....skill.decorator import skill
from .._deps import require

# Excel 自身的列上限。这里把"最多读多少列"的天花板对齐**事实上限**，
# 而不是自己拍一个 40 —— 那个数会让"把整张表读出来"变成做不到的事。
MAX_COLS = 16_384


# --------------------------------------------------------------------------- #
# 公共工具
# --------------------------------------------------------------------------- #
def _stringify(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool, str)):
        return value
    # ⚠️ **不做字符截断**：这里以前是 ``text[:500]``，一个长公式或长文本会被
    # 静默砍掉一半，而表格内容恰恰是用户最需要看全的东西。
    return str(value)


def _dedupe_headers(raw: list[Any], width: int) -> list[str]:
    """把表头行整理成唯一、非空的列名。

    真实表格里经常出现空表头或重复列名，直接当字典键会导致数据互相覆盖，
    这里统一补成「列N」并加后缀去重。
    """
    headers: list[str] = []
    seen: dict[str, int] = {}
    for index in range(width):
        cell = raw[index] if index < len(raw) else None
        name = str(cell).strip() if cell is not None else ""
        if not name:
            name = f"列{index + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        headers.append(name)
    return headers


def _read_table(
    path: Any,
    *,
    sheet_name: str | None,
    max_rows: int,
    max_cols: int = MAX_COLS,
) -> dict[str, Any]:
    """读取表格为 ``{columns, rows, total_rows, sheet}``。

    用 ``read_only=True`` 流式读取，几十万行的文件也不会把内存吃满。
    """
    openpyxl = require("openpyxl")

    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise SkillExecutionError(f"无法打开 Excel 文件：{exc}") from exc

    try:
        names = list(workbook.sheetnames)
        target = sheet_name or names[0]
        if target not in names:
            raise SkillExecutionError(
                f"工作表「{target}」不存在。该文件包含的工作表：{', '.join(names)}"
            )

        sheet = workbook[target]
        rows_iter = sheet.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return {"sheet": target, "sheets": names, "columns": [], "rows": [], "total_rows": 0}

        width = min(max(len(header_row), 1), max_cols)
        columns = _dedupe_headers(list(header_row), width)

        records: list[dict[str, Any]] = []
        total = 0
        for row in rows_iter:
            if row is None:
                continue
            if all(cell is None for cell in row[:width]):
                continue  # 跳过整行为空的填充行
            total += 1
            if len(records) >= max_rows:
                continue  # 继续计数但不入结果，这样 total_rows 是准确的
            records.append(
                {columns[i]: _stringify(row[i] if i < len(row) else None) for i in range(width)}
            )

        # openpyxl 的 ``data_only=True`` 读的是单元格的**缓存值**。公式若从未
        # 在 Excel 里打开计算并保存过（脚本生成的文件很常见），读出来就是 None ——
        # 在结果里看起来和"这一列本来是空的"完全一样。
        # 不二次加载整个工作簿就无法区分这两种情况，所以只给一句提示，
        # 免得模型把公式列当成空值直接参与统计，并据此得出错误结论。
        has_empty = any(cell is None for record in records for cell in record.values())

        return {
            "sheet": target,
            "sheets": names,
            "columns": columns,
            "rows": records,
            "total_rows": total,
            "truncated": total > len(records),
            "note": (
                "表格中存在空单元格。如果原表里有公式，且该文件从未在 Excel 中"
                "打开计算过，那些单元格的真实值读不出来（只能读缓存值），"
                "请勿直接当作空值参与统计。"
                if has_empty
                else None
            ),
        }
    finally:
        workbook.close()


def _load_writable(path: Any, *, create_if_missing: bool) -> Any:
    openpyxl = require("openpyxl")
    if path.exists():
        try:
            return openpyxl.load_workbook(path)
        except Exception as exc:  # noqa: BLE001
            raise SkillExecutionError(f"无法打开 Excel 文件进行写入：{exc}") from exc
    if not create_if_missing:
        raise SkillExecutionError(f"文件不存在：{path}")
    return openpyxl.Workbook()


# --------------------------------------------------------------------------- #
# excel_read
# --------------------------------------------------------------------------- #
class ExcelReadParams(BaseModel):
    file_path: str = Field(..., description="Excel 文件的绝对路径（.xlsx / .xlsm）")
    sheet_name: str | None = Field(None, description="工作表名；留空则读取第一个工作表")
    # 上限对齐 Excel 的事实上限（1048576 行 × 16384 列）。
    # 这里刻意不设"人为"的天花板：想读全表就把 max_rows 填够，
    # 内容装不下模型的一次上下文时由 memory/spill.py 无损外置。
    max_rows: int = Field(50, ge=1, le=1_048_576, description="最多返回多少行数据")
    max_cols: int = Field(20, ge=1, le=MAX_COLS, description="最多读取多少列")


@skill(
    name="excel_read",
    display_name="读取 Excel",
    description=(
        "读取 Excel 文件的结构与数据，返回工作表列表、列名和前若干行记录。"
        "当用户提供了 .xlsx 文件并要求查看、统计、分析或整理其内容时，先调用本工具了解数据长什么样，"
        "再决定后续用 excel_analyze 聚合还是 excel_write 写回。"
        "注意：只适用于 Excel 文件；CSV 请用 doc_parse，PDF/Word 也用 doc_parse。"
    ),
    params_model=ExcelReadParams,
    category="office",
    permission_level="safe",
    tags=["表格", "数据"],
)
class ExcelReadSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ExcelReadParams(**params)
        path = ctx.resolve_input_file(args.file_path)
        table = _read_table(
            path,
            sheet_name=args.sheet_name,
            max_rows=args.max_rows,
            max_cols=args.max_cols,
        )
        return {"file": str(path), **table}


# --------------------------------------------------------------------------- #
# excel_analyze
# --------------------------------------------------------------------------- #
class ExcelAnalyzeParams(BaseModel):
    file_path: str = Field(..., description="Excel 文件的绝对路径")
    group_by: str = Field(..., description="用于分组的列名（例如「月份」「部门」「产品」）")
    value_column: str | None = Field(
        None, description="要汇总的数值列名；留空表示只统计每个分组出现的次数"
    )
    aggregation: Literal["sum", "avg", "count", "max", "min"] = Field(
        "sum", description="聚合方式：求和 / 平均 / 计数 / 最大值 / 最小值"
    )
    sheet_name: str | None = Field(None, description="工作表名；留空用第一个")
    top_n: int = Field(20, ge=1, le=100_000, description="最多返回多少个分组")
    sort_desc: bool = Field(True, description="是否按聚合值从大到小排序")


@skill(
    name="excel_analyze",
    display_name="Excel 聚合分析",
    description=(
        "对 Excel 数据做分组聚合：按某一列分组，对另一列求和/平均/计数/最大/最小。"
        "当用户提出「按月份汇总销售额」「每个部门有多少人」「哪个产品卖得最多」这类统计需求时使用。"
        "调用前应先用 excel_read 确认准确的列名。返回聚合结果与总计，可直接用于生成图表。"
    ),
    params_model=ExcelAnalyzeParams,
    category="office",
    permission_level="safe",
    tags=["表格", "统计"],
)
class ExcelAnalyzeSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ExcelAnalyzeParams(**params)
        path = ctx.resolve_input_file(args.file_path)

        # 需要完整数据才能聚合，这里放宽行数上限；列数保持收敛
        table = _read_table(path, sheet_name=args.sheet_name, max_rows=200_000)
        columns: list[str] = table["columns"]
        rows: list[dict[str, Any]] = table["rows"]

        if args.group_by not in columns:
            raise SkillExecutionError(
                f"列「{args.group_by}」不存在。可用列：{', '.join(columns)}\n"
                f"请先用 excel_read 查看表结构。"
            )
        if args.aggregation != "count" and not args.value_column:
            raise SkillExecutionError(
                f"聚合方式为 {args.aggregation} 时必须提供 value_column（要汇总的数值列）。"
            )
        if args.value_column and args.value_column not in columns:
            raise SkillExecutionError(
                f"列「{args.value_column}」不存在。可用列：{', '.join(columns)}"
            )

        buckets: dict[str, list[float]] = {}
        counts: dict[str, int] = {}
        skipped = 0
        for row in rows:
            key_raw = row.get(args.group_by)
            key = str(key_raw).strip() if key_raw is not None else ""
            if not key:
                key = "(空)"
            counts[key] = counts.get(key, 0) + 1

            if args.aggregation == "count":
                continue
            raw = row.get(args.value_column or "")
            try:
                value = float(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                skipped += 1
                continue
            buckets.setdefault(key, []).append(value)

        if args.aggregation == "count":
            items = [{"group": key, "value": count} for key, count in counts.items()]
        else:
            items = []
            for key, values in buckets.items():
                if not values:
                    continue
                if args.aggregation == "sum":
                    aggregated = sum(values)
                elif args.aggregation == "avg":
                    aggregated = sum(values) / len(values)
                elif args.aggregation == "max":
                    aggregated = max(values)
                else:
                    aggregated = min(values)
                items.append({"group": key, "value": round(aggregated, 4), "count": len(values)})

        items.sort(key=lambda item: item["value"], reverse=args.sort_desc)
        top = items[: args.top_n]

        total = round(sum(item["value"] for item in items), 4) if items else 0
        return {
            "file": str(path),
            "sheet": table["sheet"],
            "group_by": args.group_by,
            "value_column": args.value_column,
            "aggregation": args.aggregation,
            "source_rows": table["total_rows"],
            "groups": len(items),
            "total": total,
            "items": top,
            "skipped_non_numeric": skipped,
            "note": (
                f"仅返回前 {len(top)} 个分组（共 {len(items)} 个）"
                if len(items) > len(top)
                else None
            ),
        }


# --------------------------------------------------------------------------- #
# excel_write
# --------------------------------------------------------------------------- #
class ExcelWriteParams(BaseModel):
    file_path: str = Field(..., description="目标 Excel 文件路径，不存在时按 create_if_missing 决定")
    rows: list[dict[str, Any]] = Field(
        ..., min_length=1, description="要写入的数据，每项是一个字典，键为列名"
    )
    sheet_name: str = Field("Sheet1", description="工作表名")
    mode: Literal["append", "overwrite"] = Field(
        "append",
        description="append 追加到现有数据末尾（沿用已有表头）；overwrite 清空该表后重写",
    )
    create_if_missing: bool = Field(True, description="文件不存在时是否新建")


@skill(
    name="excel_write",
    display_name="写入 Excel",
    description=(
        "把数据写入 Excel 文件，支持追加到现有表格或整体覆盖。"
        "当用户要求「把结果导出成 Excel」「把这些数据保存到表格里」「在表格里补一列」时使用。"
        "append 模式下会沿用已有表头，只写入键名匹配的列。"
        "这是写操作，会修改用户磁盘上的文件，执行前需要用户确认。"
    ),
    params_model=ExcelWriteParams,
    category="office",
    permission_level="confirm",
    tags=["表格", "写入"],
)
class ExcelWriteSkill(BaseSkill):
    async def run(self, ctx: SkillContext, **params: Any) -> dict[str, Any]:
        args = ExcelWriteParams(**params)
        # 写入目标可能是新文件，因此只校验目录白名单（由 artifact_output 与 policy 共同保证）
        path = ctx.resolve_path(args.file_path, mode="write")
        path.parent.mkdir(parents=True, exist_ok=True)

        workbook = _load_writable(path, create_if_missing=args.create_if_missing)
        try:
            if args.sheet_name in workbook.sheetnames:
                sheet = workbook[args.sheet_name]
                if args.mode == "overwrite":
                    workbook.remove(sheet)
                    sheet = workbook.create_sheet(args.sheet_name)
                    headers: list[str] = []
                else:
                    headers = self._existing_headers(sheet)
            else:
                sheet = workbook.create_sheet(args.sheet_name)
                # openpyxl 新建工作簿自带一个空 Sheet，避免留下无用页
                if "Sheet" in workbook.sheetnames and len(workbook.sheetnames) > 1:
                    default = workbook["Sheet"]
                    if default.max_row == 1 and default.max_column == 1:
                        workbook.remove(default)
                headers = []

            incoming = list(args.rows[0].keys())
            if not headers:
                headers = incoming
                sheet.append(headers)
            else:
                # 追加时保留原表头结构，新出现的键补到末尾
                extra = [key for key in incoming if key not in headers]
                if extra:
                    headers = headers + extra
                    for index, key in enumerate(extra, start=len(sheet[1]) + 1):
                        sheet.cell(row=1, column=index, value=key)

            for row in args.rows:
                sheet.append([self._cell(row.get(header)) for header in headers])

            workbook.save(path)
        finally:
            workbook.close()

        artifact = await ctx.register_artifact(path, note=f"写入 {len(args.rows)} 行")
        return {
            "file": str(path),
            "sheet": args.sheet_name,
            "written_rows": len(args.rows),
            "columns": headers,
            "mode": args.mode,
            "artifact": artifact,
        }

    @staticmethod
    def _existing_headers(sheet: Any) -> list[str]:
        """取出已有表头。

        **必须按列位保留空列**，不能把空表头"过滤掉"。
        过滤之后返回的列名比表格实际列数少，而下面 ``sheet.append([...])``
        是从第 1 列开始依次写入的 —— 于是已有表头是 ``["名称", None, "金额"]``
        时，「金额」的数据会落到第 2 列，**数据与表头整体错位**，
        而且表格打开来一切正常，只有对照表头才能看出问题。

        空列名补成「列N」并复用 ``_dedupe_headers``，是为了让这里的命名
        与读取路径（``_read_table``）完全一致：读写用两套列名的话，
        读回来的列名和写进去的对不上，append 一次就多出一堆``列N``。
        """
        if sheet.max_row < 1:
            return []
        row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not row:
            return []
        return _dedupe_headers(list(row), len(row))

    @staticmethod
    def _cell(value: Any) -> Any:
        """把无法直接写入单元格的类型转成字符串。"""
        if value is None or isinstance(value, (int, float, bool, str)):
            return value
        if isinstance(value, (list, tuple, dict)):
            import json

            return json.dumps(value, ensure_ascii=False)
        return str(value)
