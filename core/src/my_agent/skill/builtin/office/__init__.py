"""内置办公技能。"""

from .chart import ChartGenerateSkill
from .document import DocParseSkill
from .excel import ExcelAnalyzeSkill, ExcelReadSkill, ExcelWriteSkill
from .report import ReportGenerateSkill

__all__ = [
    "ChartGenerateSkill",
    "DocParseSkill",
    "ExcelAnalyzeSkill",
    "ExcelReadSkill",
    "ExcelWriteSkill",
    "ReportGenerateSkill",
]
