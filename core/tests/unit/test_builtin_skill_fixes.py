"""内置技能里那几个"看起来正常但结果是错的"的缺陷。

这组用例的共同特点是：修复前的失败形态**都不报错** ——
数据静默错位、提醒静默晚一天、坐标轴静默算出 NaN。
正因如此才需要显式锁住，否则回归了也没人发现。
"""

from __future__ import annotations

import ast
from datetime import datetime

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.skill.builtin.life.reminder import parse_when
from my_agent.skill.builtin.office.excel import ExcelWriteSkill, _dedupe_headers
from my_agent.skill.builtin.system import _eval_node
from my_agent.utils.chart import _nice_ceil, _nice_floor


# --------------------------------------------------------------------------- #
# B15：calc 的幂运算可以卡死整个服务
# --------------------------------------------------------------------------- #
def eval_expr(text: str):
    return _eval_node(ast.parse(text, mode="eval"))


class TestCalcExponentGuard:
    def test_normal_power_still_works(self):
        assert eval_expr("2 ** 10") == 1024
        assert eval_expr("9 ** 2") == 81

    def test_huge_exponent_is_rejected(self):
        """``9**9**9`` 的指数是 3.8 亿，CPython 会同步算到内存耗尽。

        而 calc 是 safe 级、不弹确认 —— 模型生成这样一个表达式就够了，
        不需要用户做错任何事。更糟的是 ``wait_for`` 的超时**中断不了同步代码**，
        整个服务（含所有会话的 SSE）会一起卡死。
        """
        with pytest.raises(ValueError, match="过大"):
            eval_expr("9 ** 9 ** 9")

    def test_boundary_exponent_allowed(self):
        # 1024 是上限本身，应当放行（2**1024 约 1.8e308，算得很快）
        assert eval_expr("2 ** 1024") > 0

    def test_non_numeric_exponent_rejected(self):
        with pytest.raises(ValueError):
            eval_expr("2 ** 'x'")

    def test_other_operators_unaffected(self):
        assert eval_expr("(1200-350) * 0.13") == pytest.approx(110.5)
        assert eval_expr("7 // 2") == 3


# --------------------------------------------------------------------------- #
# B18：「今天 18:00」过了 18 点会被静默顺延到明天
# --------------------------------------------------------------------------- #
class TestReminderDayHandling:
    NOW = datetime(2026, 9, 18, 19, 0)

    def test_bare_time_rolls_to_tomorrow(self):
        """只说时间、今天已过 —— 顺延到明天才符合直觉。"""
        result = parse_when("18:00", now=self.NOW)

        assert result.date() == datetime(2026, 9, 19).date()
        assert (result.hour, result.minute) == (18, 0)

    def test_explicit_today_in_the_past_is_refused(self):
        """**明确说了「今天」**时不能悄悄改到明天。

        用户说"今天 18:00"而现在是 19 点，挪到明天会让他晚整整一天收到提醒，
        而界面上看不出任何异常 —— 他只会觉得"这提醒怎么没响"。
        """
        with pytest.raises(SkillExecutionError, match="已经过去"):
            parse_when("今天 18:00", now=self.NOW)

    def test_explicit_today_in_the_future_is_fine(self):
        result = parse_when("今天 23:30", now=self.NOW)

        assert result == datetime(2026, 9, 18, 23, 30)

    def test_explicit_tomorrow_is_fine(self):
        result = parse_when("明天 8:00", now=self.NOW)

        assert result == datetime(2026, 9, 19, 8, 0)

    def test_full_datetime_parses(self):
        assert parse_when("2026-09-20 14:30", now=self.NOW) == datetime(2026, 9, 20, 14, 30)


# --------------------------------------------------------------------------- #
# B16：Excel append 遇空表头会整体错位
# --------------------------------------------------------------------------- #
class TestExcelHeaderAlignment:
    def test_empty_header_keeps_its_column(self):
        """表头 ``["名称", None, "金额"]`` 必须返回三列。

        过滤掉空表头的话，返回的是两列，而 ``sheet.append([...])`` 从第 1 列
        开始写 —— 「金额」的数据会落到第 2 列，**数据与表头整体错位**，
        表格打开来一切正常，只有对照表头才看得出问题。
        """
        headers = _dedupe_headers(["名称", None, "金额"], 3)

        assert headers == ["名称", "列2", "金额"]

    def test_naming_matches_read_path(self):
        """写路径的列名必须与读取路径一致，否则 append 一次就多出一堆「列N」。"""
        assert _dedupe_headers([None, "金额"], 2) == ["列1", "金额"]

    def test_duplicates_are_suffixed(self):
        # 后缀从 `_1` 起（保持既有约定，读取路径也是这么编的）
        assert _dedupe_headers(["金额", "金额"], 2) == ["金额", "金额_1"]


class TestExistingHeadersUsesColumnPositions:
    def test_sheet_with_empty_header_cell(self):
        class FakeSheet:
            max_row = 2

            def iter_rows(self, **_kwargs):
                yield ("名称", None, "金额")

        headers = ExcelWriteSkill._existing_headers(FakeSheet())

        assert len(headers) == 3, "空表头必须占位，否则写入时会错列"
        assert headers[2] == "金额"


# --------------------------------------------------------------------------- #
# B17：图表数值边界
# --------------------------------------------------------------------------- #
class TestChartNumericSafety:
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_nice_ceil_does_not_raise(self, value: float):
        """NaN / inf 会让 ``math.floor(math.log10(...))`` 抛 ValueError / OverflowError。"""
        assert _nice_ceil(value) == 1.0

    @pytest.mark.parametrize("value", [float("nan"), float("inf")])
    def test_nice_floor_does_not_raise(self, value: float):
        assert _nice_floor(value) == 0.0

    def test_normal_values_unchanged(self):
        assert _nice_ceil(123) == 150
        assert _nice_floor(-123) == -150
        assert _nice_floor(5) == 0.0
