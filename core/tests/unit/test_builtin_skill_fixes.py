






from __future__ import annotations

import ast
from datetime import datetime

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.skill.builtin.life.reminder import parse_when
from my_agent.skill.builtin.office.excel import ExcelWriteSkill, _dedupe_headers
from my_agent.skill.builtin.system import _eval_node
from my_agent.utils.chart import _nice_ceil, _nice_floor





def eval_expr(text: str):
    return _eval_node(ast.parse(text, mode="eval"))


class TestCalcExponentGuard:
    def test_normal_power_still_works(self):
        assert eval_expr("2 ** 10") == 1024
        assert eval_expr("9 ** 2") == 81

    def test_huge_exponent_is_rejected(self):






        with pytest.raises(ValueError, match="过大"):
            eval_expr("9 ** 9 ** 9")

    def test_boundary_exponent_allowed(self):
        
        assert eval_expr("2 ** 1024") > 0

    def test_non_numeric_exponent_rejected(self):
        with pytest.raises(ValueError):
            eval_expr("2 ** 'x'")

    def test_other_operators_unaffected(self):
        assert eval_expr("(1200-350) * 0.13") == pytest.approx(110.5)
        assert eval_expr("7 // 2") == 3





class TestReminderDayHandling:
    NOW = datetime(2026, 9, 18, 19, 0)

    def test_bare_time_rolls_to_tomorrow(self):

        result = parse_when("18:00", now=self.NOW)

        assert result.date() == datetime(2026, 9, 19).date()
        assert (result.hour, result.minute) == (18, 0)

    def test_explicit_today_in_the_past_is_refused(self):





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





class TestExcelHeaderAlignment:
    def test_empty_header_keeps_its_column(self):






        headers = _dedupe_headers(["名称", None, "金额"], 3)

        assert headers == ["名称", "列2", "金额"]

    def test_naming_matches_read_path(self):

        assert _dedupe_headers([None, "金额"], 2) == ["列1", "金额"]

    def test_duplicates_are_suffixed(self):
        
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





class TestChartNumericSafety:
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_nice_ceil_does_not_raise(self, value: float):

        assert _nice_ceil(value) == 1.0

    @pytest.mark.parametrize("value", [float("nan"), float("inf")])
    def test_nice_floor_does_not_raise(self, value: float):
        assert _nice_floor(value) == 0.0

    def test_normal_values_unchanged(self):
        assert _nice_ceil(123) == 150
        assert _nice_floor(-123) == -150
        assert _nice_floor(5) == 0.0
