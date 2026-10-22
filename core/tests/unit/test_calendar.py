










from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from my_agent.calendar.ics import (
    CalendarEvent,
    apply_changes,
    build_ics,
    date_range,
    events_in_range,
    parse_events,
)
from my_agent.calendar.service import CalDavBackend, CalendarError, CalendarService
from my_agent.config.paths import AppPaths
from my_agent.config.schemas import CalendarSettings
from my_agent.errors import SkillExecutionError
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.calendar import (
    CalendarCreateSkill,
    CalendarDeleteSkill,
    CalendarListSkill,
    CalendarUpdateSkill,
)


def make_event(**overrides) -> CalendarEvent:
    payload = {
        "uid": "e1",
        "summary": "和产品过需求",
        "start": datetime(2026, 9, 25, 14, 30),
        "end": datetime(2026, 9, 25, 15, 30),
    }
    payload.update(overrides)
    return CalendarEvent(**payload)


class TestIcs:
    def test_round_trip_keeps_every_field(self):
        event = make_event(location="三楼会议室", description="带上上一版原型\n与数据")

        parsed = parse_events(build_ics([event]))

        assert len(parsed) == 1
        back = parsed[0]
        assert back.uid == "e1"
        assert back.summary == "和产品过需求"
        assert back.start == event.start
        assert back.end == event.end
        assert back.location == "三楼会议室"
        
        assert back.description == "带上上一版原型\n与数据"

    def test_utc_time_is_converted_to_local(self):

        text = (
            "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:u\r\n"
            "DTSTART:20260925T063000Z\r\nDTEND:20260925T073000Z\r\nSUMMARY:跨时区\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n"
        )

        event = parse_events(text)[0]

        expected = (
            datetime(2026, 9, 25, 6, 30, tzinfo=UTC).astimezone().replace(tzinfo=None)
        )
        assert event.start == expected

    def test_all_day_event_round_trip(self):
        event = make_event(
            start=datetime(2026, 9, 25),
            end=datetime(2026, 9, 26),
            all_day=True,
        )

        back = parse_events(build_ics([event]))[0]

        assert back.all_day is True
        assert back.start == datetime(2026, 9, 25)

    def test_recurrence_is_preserved_not_expanded(self):

        event = make_event(recurrence="FREQ=WEEKLY;BYDAY=MO")

        back = parse_events(build_ics([event]))[0]

        assert back.recurrence == "FREQ=WEEKLY;BYDAY=MO"

    def test_long_chinese_lines_are_folded_by_bytes(self):

        event = make_event(summary="很长的标题" * 30)

        text = build_ics([event])

        for line in text.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75
        
        assert parse_events(text)[0].summary == event.summary

    def test_range_filter_uses_overlap(self):
        early = make_event(uid="a", start=datetime(2026, 9, 25, 8), end=datetime(2026, 9, 25, 9))
        crossing = make_event(uid="b", start=datetime(2026, 9, 24, 23), end=datetime(2026, 9, 25, 1))
        late = make_event(uid="c", start=datetime(2026, 10, 1, 8), end=datetime(2026, 10, 1, 9))

        start, end = date_range(datetime(2026, 9, 25).date(), datetime(2026, 9, 25).date())
        picked = events_in_range([early, crossing, late], start, end)

        
        assert [item.uid for item in picked] == ["b", "a"]

    def test_apply_changes_shifts_end_when_only_start_changes(self):





        event = make_event(
            start=datetime(2026, 9, 25, 10, 0), end=datetime(2026, 9, 25, 10, 30)
        )

        updated = apply_changes(event, {"start": datetime(2026, 9, 25, 15, 0)})

        assert updated.start == datetime(2026, 9, 25, 15, 0)
        assert updated.end == datetime(2026, 9, 25, 15, 30)

    def test_apply_changes_with_explicit_end_does_not_shift(self):

        event = make_event(
            start=datetime(2026, 9, 25, 10, 0), end=datetime(2026, 9, 25, 10, 30)
        )

        updated = apply_changes(
            event,
            {"start": datetime(2026, 9, 25, 15, 0), "end": datetime(2026, 9, 25, 16, 0)},
        )

        assert updated.end == datetime(2026, 9, 25, 16, 0)

    def test_apply_changes_rejects_inverted_range(self):

        event = make_event()

        with pytest.raises(ValueError, match="结束时间必须晚于开始时间"):
            apply_changes(
                event,
                {"start": datetime(2026, 9, 25, 15, 0), "end": datetime(2026, 9, 25, 14, 0)},
            )

    def test_apply_changes_falls_back_when_original_duration_is_broken(self):

        broken = make_event(
            start=datetime(2026, 9, 25, 10, 0), end=datetime(2026, 9, 25, 10, 0)
        )

        updated = apply_changes(
            broken,
            {"start": datetime(2026, 9, 25, 15, 0)},
            default_duration=timedelta(minutes=45),
        )

        assert updated.end == datetime(2026, 9, 25, 15, 45)


class TestLocalBackend:
    @pytest.fixture
    def service(self, tmp_path) -> CalendarService:
        paths = AppPaths(tmp_path / "AgentDesktop").ensure()
        return CalendarService(CalendarSettings(mode="local"), paths)

    @pytest.mark.asyncio
    async def test_crud_round_trip(self, service):
        created = await service.create_event(make_event(uid="x1"))
        assert created.uid == "x1"

        listed = await service.list_events(
            datetime(2026, 9, 25), datetime(2026, 9, 26)
        )
        assert [item.uid for item in listed] == ["x1"]

        updated = await service.update_event("x1", {"summary": "改过的标题"})
        assert updated.summary == "改过的标题"

        assert await service.delete_event("x1") is True
        assert await service.list_events(datetime(2026, 9, 25), datetime(2026, 9, 26)) == []
        assert await service.delete_event("x1") is False

    @pytest.mark.asyncio
    async def test_file_survives_across_service_instances(self, tmp_path):
        paths = AppPaths(tmp_path / "AgentDesktop").ensure()
        first = CalendarService(CalendarSettings(mode="local"), paths)
        await first.create_event(make_event(uid="persist"))

        second = CalendarService(CalendarSettings(mode="local"), paths)
        listed = await second.list_events(datetime(2026, 9, 25), datetime(2026, 9, 26))

        assert [item.uid for item in listed] == ["persist"]


class TestCalendarSkills:


    def _ctx(self, tmp_path) -> SkillContext:
        paths = AppPaths(tmp_path / "AgentDesktop").ensure()
        service = CalendarService(CalendarSettings(mode="local"), paths)
        return SkillContext(paths=paths, session_id="s1", extra={"calendar": service})

    def test_permission_levels(self):
        assert CalendarListSkill.meta.permission_level == "safe"
        assert CalendarCreateSkill.meta.permission_level == "confirm"
        assert CalendarUpdateSkill.meta.permission_level == "confirm"
        assert CalendarDeleteSkill.meta.permission_level == "confirm"

    @pytest.mark.asyncio
    async def test_create_understands_loose_time(self, tmp_path):

        ctx = self._ctx(tmp_path)

        result = await CalendarCreateSkill().run(ctx, summary="晨会", start="明天 8:00")

        start = datetime.fromisoformat(result["start"])
        assert start.hour == 8 and start.minute == 0
        assert start.date() == (datetime.now() + timedelta(days=1)).date()
        
        assert result["duration_minutes"] == 60
        assert "本地日历" in result["backend"]

    @pytest.mark.asyncio
    async def test_create_rejects_inverted_range(self, tmp_path):
        ctx = self._ctx(tmp_path)

        with pytest.raises(SkillExecutionError):
            await CalendarCreateSkill().run(
                ctx, summary="倒着的会", start="2026-09-25 15:00", end="2026-09-25 14:00"
            )

    @pytest.mark.asyncio
    async def test_list_then_update_then_delete(self, tmp_path):
        ctx = self._ctx(tmp_path)
        created = await CalendarCreateSkill().run(
            ctx, summary="周会", start="2026-09-25 10:00", duration_minutes=30
        )

        listed = await CalendarListSkill().run(
            ctx, start_date="2026-09-25", end_date="2026-09-25"
        )
        assert [item["uid"] for item in listed["events"]] == [created["uid"]]

        updated = await CalendarUpdateSkill().run(
            ctx, uid=created["uid"], summary="周会（改期）", location="5 楼"
        )
        assert updated["summary"] == "周会（改期）"
        assert updated["changed"] == ["location", "summary"]

        removed = await CalendarDeleteSkill().run(ctx, uid=created["uid"])
        assert "已删除" in removed["message"]

    @pytest.mark.asyncio
    async def test_delete_unknown_uid_is_reported(self, tmp_path):
        ctx = self._ctx(tmp_path)

        with pytest.raises(SkillExecutionError) as info:
            await CalendarDeleteSkill().run(ctx, uid="不存在")

        assert "没有找到日程" in str(info.value)

    @pytest.mark.asyncio
    async def test_update_only_start_keeps_duration(self, tmp_path):

        ctx = self._ctx(tmp_path)
        created = await CalendarCreateSkill().run(
            ctx, summary="周会", start="2026-09-25 10:00", duration_minutes=30
        )

        updated = await CalendarUpdateSkill().run(
            ctx, uid=created["uid"], start="2026-09-25 15:00"
        )

        assert updated["start"] == "2026-09-25T15:00"
        assert updated["end"] == "2026-09-25T15:30"
        assert updated["duration_minutes"] == 30
        
        assert updated["changed"] == ["start"]

    @pytest.mark.asyncio
    async def test_update_rejects_inverted_range(self, tmp_path):

        ctx = self._ctx(tmp_path)
        created = await CalendarCreateSkill().run(ctx, summary="周会", start="2026-09-25 10:00")

        with pytest.raises(SkillExecutionError) as info:
            await CalendarUpdateSkill().run(
                ctx, uid=created["uid"], start="2026-09-25 15:00", end="2026-09-25 14:00"
            )

        assert "结束时间必须晚于开始时间" in str(info.value)


class TestCalDavBackend:
    @pytest.mark.asyncio
    async def test_internal_address_is_rejected(self):

        backend = CalDavBackend(
            CalendarSettings(
                mode="caldav",
                caldav_url="http://169.254.169.254/caldav/",
                caldav_username="u",
                caldav_password="p",
            )
        )

        with pytest.raises(CalendarError) as info:
            await backend.list_events(datetime.now(), datetime.now() + timedelta(days=1))

        assert "只支持 http/https" in info.value.message or "不允许" in info.value.message

    @pytest.mark.asyncio
    async def test_missing_credentials_are_reported(self):
        backend = CalDavBackend(
            CalendarSettings(mode="caldav", caldav_url="https://cal.example.com/")
        )

        with pytest.raises(CalendarError) as info:
            await backend.list_events(datetime.now(), datetime.now() + timedelta(days=1))

        assert "账号" in info.value.message

    @pytest.mark.asyncio
    @respx.mock
    async def test_report_request_is_well_formed(self):

        base = "https://cal.example.com/"
        respx.route(method="PROPFIND", url=base).mock(
            return_value=httpx.Response(
                207,
                text=(
                    '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
                    "<d:response><d:href>/</d:href>"
                    "<d:propstat><d:prop><d:resourcetype>"
                    '<d:collection/><c:calendar xmlns:c="urn:ietf:params:xml:ns:caldav"/>'
                    "</d:resourcetype></d:prop></d:propstat></d:response></d:multistatus>"
                ),
            )
        )
        report = respx.route(method="REPORT", url=base).mock(
            return_value=httpx.Response(
                207,
                text=(
                    '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" '
                    'xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response>'
                    "<c:calendar-data>BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:r1\r\n"
                    "DTSTART:20260925T140000\r\nDTEND:20260925T150000\r\n"
                    "SUMMARY:在线日程\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
                    "</c:calendar-data></d:response></d:multistatus>"
                ),
            )
        )

        backend = CalDavBackend(
            CalendarSettings(
                mode="caldav",
                caldav_url=base,
                caldav_username="me",
                caldav_password="secret",
            )
        )
        events = await backend.list_events(datetime(2026, 9, 25), datetime(2026, 9, 26))

        assert [item.summary for item in events] == ["在线日程"]
        
        assert report.calls[0].request.headers.get("authorization", "").startswith("Basic ")
        
        assert b"time-range" in report.calls[0].request.content

    @pytest.mark.asyncio
    @respx.mock
    async def test_move_to_calendar_that_does_not_exist_gives_actionable_hint(self):

        respx.route(method="PROPFIND", url="https://cal.example.com/").mock(
            return_value=httpx.Response(207, text='<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"/>')
        )

        backend = CalDavBackend(
            CalendarSettings(
                mode="caldav",
                caldav_url="https://cal.example.com/",
                caldav_username="me",
                caldav_password="secret",
            )
        )

        with pytest.raises(CalendarError) as info:
            await backend.list_events(datetime.now(), datetime.now() + timedelta(days=1))

        assert "日历集合" in info.value.message
