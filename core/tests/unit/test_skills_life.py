"""生活技能测试：天气、记账、提醒。

天气用假的 httpx 客户端喂固定响应，不打真实网络——测试不应该依赖外部服务
的可用性。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
import pytest

from my_agent.errors import SkillExecutionError
from my_agent.skill.builtin.life.expense import ExpenseAnalyzeSkill, ExpenseRecordSkill
from my_agent.skill.builtin.life.reminder import (
    ReminderCancelSkill,
    ReminderCreateSkill,
    ReminderListSkill,
    parse_when,
)
from my_agent.skill.builtin.life.weather import WeatherQuerySkill, _clothing_advice
from my_agent.skill.manager import SkillManager

WEATHER_PAYLOAD = {
    "current_condition": [
        {
            "temp_C": "28",
            "FeelsLikeC": "31",
            "humidity": "72",
            "windspeedKmph": "12",
            "winddir16Point": "SE",
            "visibility": "10",
            "precipMM": "0.0",
            "lang_zh": [{"value": "多云"}],
        }
    ],
    "nearest_area": [{"areaName": [{"value": "杭州"}]}],
    "weather": [
        {
            "date": "2026-09-17",
            "maxtempC": "30",
            "mintempC": "22",
            "hourly": [{}] * 4
            + [
                {
                    "lang_zh": [{"value": "雷阵雨"}],
                    "chanceofrain": "70",
                }
            ],
        }
    ],
}


@pytest.fixture
def manager(skill_env) -> SkillManager:
    skills = SkillManager()
    for skill_cls in (
        ExpenseRecordSkill,
        ExpenseAnalyzeSkill,
        ReminderCreateSkill,
        ReminderListSkill,
        ReminderCancelSkill,
        WeatherQuerySkill,
    ):
        skills.register(skill_cls)
    return skills


# --------------------------------------------------------------------------- #
# 天气
# --------------------------------------------------------------------------- #
def _install_fake_http(monkeypatch, payload, status: int = 200) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.status_code = status

        def json(self):
            if isinstance(payload, Exception):
                raise payload
            return payload

    class FakeClient:
        last_params: dict = {}
        last_url: str = ""

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> bool:
            return False

        async def get(self, url, **kwargs):
            FakeClient.last_url = url
            FakeClient.last_params = kwargs.get("params", {})
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)


async def test_weather_query_parses_and_advises(manager, skill_env, monkeypatch):
    _install_fake_http(monkeypatch, WEATHER_PAYLOAD)
    result = json.loads(
        await manager.execute("weather_query", {"city": "杭州", "days": 1}, skill_env.ctx)
    )

    assert result["city"] == "杭州"
    assert result["resolved_area"] == "杭州"
    assert result["current"]["temperature"] == 28
    assert result["current"]["description"] == "多云"
    # 28 度 + 雷阵雨 → 既要提示穿短袖，也要提示带伞
    assert "短袖" in result["clothing_advice"]
    assert "带伞" in result["clothing_advice"]
    assert result["forecast"][0]["description"] == "雷阵雨"
    assert result["forecast"][0]["chance_of_rain"] == 70


async def test_weather_query_city_not_found(manager, skill_env, monkeypatch):
    _install_fake_http(monkeypatch, {}, status=404)
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute("weather_query", {"city": "不存在城"}, skill_env.ctx)
    assert "找不到城市" in str(exc.value)


async def test_weather_query_network_error(manager, skill_env, monkeypatch):
    class BrokenClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> bool:
            return False

        async def get(self, url, **kwargs):
            raise httpx.ConnectError("模拟网络不可达")

    monkeypatch.setattr(httpx, "AsyncClient", BrokenClient)
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute("weather_query", {"city": "杭州"}, skill_env.ctx)
    assert "无法连接" in str(exc.value)


async def test_weather_query_handles_bad_json(manager, skill_env, monkeypatch):
    _install_fake_http(monkeypatch, ValueError("bad json"))
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute("weather_query", {"city": "杭州"}, skill_env.ctx)
    assert "非预期" in str(exc.value)


def test_clothing_advice_boundaries():
    assert "短袖" in _clothing_advice(32, "晴", 5)
    assert "薄外套" in _clothing_advice(18, "阴", 5)
    assert "羽绒服" in _clothing_advice(-3, "雪", 5)
    assert "防风" in _clothing_advice(15, "阴", 40)


# --------------------------------------------------------------------------- #
# 记账
# --------------------------------------------------------------------------- #
async def test_expense_record_auto_category(manager, skill_env):
    result = json.loads(
        await manager.execute(
            "expense_record", {"amount": 35, "note": "中午吃拉面"}, skill_env.ctx
        )
    )
    assert result["category"] == "餐饮"
    assert result["auto_category"] is True
    assert result["amount"] == 35.0
    assert result["spent_on"] == datetime.now().date().isoformat()


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("打车去机场", "交通"),
        ("买了双鞋", "购物"),
        ("房租", "居住"),
        ("电影票", "娱乐"),
        ("买药", "医疗"),
        ("话费充值", "通讯"),
        ("老板的红包", "人情"),
        ("说不清的东西", "其他"),
    ],
)
async def test_expense_category_guessing(manager, skill_env, note, expected):
    result = json.loads(
        await manager.execute("expense_record", {"amount": 10, "note": note}, skill_env.ctx)
    )
    assert result["category"] == expected


async def test_expense_record_explicit_category_wins(manager, skill_env):
    result = json.loads(
        await manager.execute(
            "expense_record",
            {"amount": 10, "note": "中午吃饭", "category": "其他"},
            skill_env.ctx,
        )
    )
    assert result["category"] == "其他"
    assert result["auto_category"] is False


async def test_expense_record_relative_date(manager, skill_env):
    result = json.loads(
        await manager.execute(
            "expense_record",
            {"amount": 10, "note": "买菜", "date": "昨天"},
            skill_env.ctx,
        )
    )
    expected = (datetime.now().date() - timedelta(days=1)).isoformat()
    assert result["spent_on"] == expected


async def test_expense_record_normalizes_date_format(manager, skill_env):
    result = json.loads(
        await manager.execute(
            "expense_record",
            {"amount": 10, "note": "买菜", "date": "2026/9/1"},
            skill_env.ctx,
        )
    )
    assert result["spent_on"] == "2026-09-01"


async def test_expense_analyze_summary(manager, skill_env):
    for amount, note in ((35, "午饭"), (20, "打车"), (65, "晚饭"), (10, "地铁")):
        await manager.execute("expense_record", {"amount": amount, "note": note}, skill_env.ctx)

    result = json.loads(
        await manager.execute("expense_analyze", {"period": "month"}, skill_env.ctx)
    )
    assert result["total"] == 130
    assert result["count"] == 4
    assert result["average"] == 32.5

    by_category = {item["category"]: item["total"] for item in result["by_category"]}
    assert by_category["餐饮"] == 100
    assert by_category["交通"] == 30
    # 分类占比之和应为 1
    assert sum(item["ratio"] for item in result["by_category"]) == pytest.approx(1.0)
    assert "餐饮" in result["top_categories_text"]


async def test_expense_analyze_empty_period(manager, skill_env):
    result = json.loads(
        await manager.execute("expense_analyze", {"period": "today"}, skill_env.ctx)
    )
    assert result["count"] == 0
    assert "没有记账记录" in result["message"]


async def test_expense_analyze_invalid_period(manager, skill_env):
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute("expense_analyze", {"period": "本季度"}, skill_env.ctx)
    assert "无法识别的周期" in str(exc.value)


async def test_expense_analyze_filters_by_category(manager, skill_env):
    for amount, note in ((35, "午饭"), (20, "打车")):
        await manager.execute("expense_record", {"amount": amount, "note": note}, skill_env.ctx)
    result = json.loads(
        await manager.execute(
            "expense_analyze", {"period": "month", "category": "交通"}, skill_env.ctx
        )
    )
    assert result["total"] == 20
    assert len(result["recent"]) == 1


# --------------------------------------------------------------------------- #
# 提醒
# --------------------------------------------------------------------------- #
def test_parse_when_absolute_formats():
    assert parse_when("2026-09-20 14:30") == datetime(2026, 9, 20, 14, 30)
    assert parse_when("2026-09-20T09:05") == datetime(2026, 9, 20, 9, 5)
    assert parse_when("2026/09/20 09:00") == datetime(2026, 9, 20, 9, 0)
    assert parse_when("2026年9月20日 9:00") == datetime(2026, 9, 20, 9, 0)


def test_parse_when_relative_day_prefix():
    now = datetime(2026, 9, 17, 10, 0)
    assert parse_when("明天 8:00", now=now) == datetime(2026, 9, 18, 8, 0)
    assert parse_when("后天 18:30", now=now) == datetime(2026, 9, 19, 18, 30)
    assert parse_when("今天 20:00", now=now) == datetime(2026, 9, 17, 20, 0)


def test_parse_when_time_only_rolls_to_tomorrow():
    """只说时间且今天已过 → 顺延到明天，符合用户直觉。"""
    now = datetime(2026, 9, 17, 10, 0)
    assert parse_when("09:00", now=now) == datetime(2026, 9, 18, 9, 0)
    assert parse_when("18:00", now=now) == datetime(2026, 9, 17, 18, 0)


def test_parse_when_date_only_defaults_to_nine():
    now = datetime(2026, 9, 17, 10, 0)
    assert parse_when("2026-09-25", now=now) == datetime(2026, 9, 25, 9, 0)


def test_parse_when_invalid_gives_examples():
    with pytest.raises(SkillExecutionError) as exc:
        parse_when("下午三点左右吧")
    message = str(exc.value)
    assert "无法识别" in message
    # 报错要给出可用格式，模型才能自我修正
    assert "2026-09-20 14:30" in message


async def test_reminder_create_absolute(manager, skill_env):
    target = datetime.now() + timedelta(hours=2)
    result = json.loads(
        await manager.execute(
            "reminder_create",
            {"content": "交周报", "remind_at": target.strftime("%Y-%m-%d %H:%M")},
            skill_env.ctx,
        )
    )
    assert result["content"] == "交周报"
    assert result["status"] == "pending"
    assert result["advance_min"] == 0
    assert "已设置提醒" in result["summary"]


async def test_reminder_create_relative_minutes(manager, skill_env):
    result = json.loads(
        await manager.execute(
            "reminder_create", {"content": "看火", "in_minutes": 10}, skill_env.ctx
        )
    )
    fire_at = datetime.fromtimestamp(result["remind_at"])
    assert 9 <= (fire_at - datetime.now()).total_seconds() / 60 <= 11


async def test_reminder_create_with_advance(manager, skill_env):
    target = datetime.now() + timedelta(hours=1)
    result = json.loads(
        await manager.execute(
            "reminder_create",
            {
                "content": "开会",
                "remind_at": target.strftime("%Y-%m-%d %H:%M"),
                "advance_minutes": 5,
            },
            skill_env.ctx,
        )
    )
    # 提醒时间应比目标时间早 5 分钟
    assert result["base_at"] - result["remind_at"] == pytest.approx(300, abs=1)


async def test_reminder_create_requires_one_time_source(manager, skill_env):
    with pytest.raises(SkillExecutionError):
        await manager.execute("reminder_create", {"content": "没说时间"}, skill_env.ctx)

    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute(
            "reminder_create",
            {"content": "给了两个", "remind_at": "2030-01-01 09:00", "in_minutes": 5},
            skill_env.ctx,
        )
    assert "只能提供一个" in str(exc.value)


async def test_reminder_create_past_time_degrades_gracefully(manager, skill_env):
    """提前量把时间推到过去时，不能静默创建一条永不触发的提醒。"""
    soon = datetime.now() + timedelta(minutes=1)
    result = json.loads(
        await manager.execute(
            "reminder_create",
            {
                "content": "马上",
                "remind_at": soon.strftime("%Y-%m-%d %H:%M"),
                "advance_minutes": 30,
            },
            skill_env.ctx,
        )
    )
    assert result["remind_at"] > datetime.now().timestamp()


async def test_reminder_list_and_cancel(manager, skill_env):
    created = json.loads(
        await manager.execute(
            "reminder_create", {"content": "喝水", "in_minutes": 30}, skill_env.ctx
        )
    )
    listed = json.loads(await manager.execute("reminder_list", {}, skill_env.ctx))
    assert listed["count"] == 1
    assert listed["reminders"][0]["content"] == "喝水"

    cancelled = json.loads(
        await manager.execute("reminder_cancel", {"reminder_id": created["id"]}, skill_env.ctx)
    )
    assert cancelled["status"] == "cancelled"

    listed_after = json.loads(await manager.execute("reminder_list", {}, skill_env.ctx))
    assert listed_after["count"] == 0
    assert "暂无提醒" in listed_after["message"]


async def test_reminder_cancel_unknown_id(manager, skill_env):
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute("reminder_cancel", {"reminder_id": 9999}, skill_env.ctx)
    assert "reminder_list" in str(exc.value)


async def test_life_skills_report_missing_database(skill_env):
    """数据库不可用时，技能的报错必须说明原因，而不是 NoneType 崩栈。"""
    from my_agent.skill.base import SkillContext
    from my_agent.skill.manager import SkillManager

    manager = SkillManager()
    manager.register(ExpenseRecordSkill)
    ctx = SkillContext(paths=skill_env.paths, extra={"expenses": None})
    with pytest.raises(SkillExecutionError) as exc:
        await manager.execute("expense_record", {"amount": 1, "note": "x"}, ctx)
    assert "不可用" in str(exc.value)
