"""内置生活技能。"""

from .expense import ExpenseAnalyzeSkill, ExpenseRecordSkill
from .reminder import ReminderCancelSkill, ReminderCreateSkill, ReminderListSkill
from .weather import WeatherQuerySkill

__all__ = [
    "ExpenseAnalyzeSkill",
    "ExpenseRecordSkill",
    "ReminderCancelSkill",
    "ReminderCreateSkill",
    "ReminderListSkill",
    "WeatherQuerySkill",
]
