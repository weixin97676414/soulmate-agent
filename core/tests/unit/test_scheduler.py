










from __future__ import annotations

import json
import time
from datetime import datetime
from types import SimpleNamespace

import pytest

from my_agent.agent.scheduler import STATE_FILENAME, STATE_VERSION, TaskScheduler
from my_agent.agent.task_store import describe_schedule
from my_agent.config.schemas import ScheduledTaskSpec


class FakeRuntime:






    def __init__(self, tasks: list[ScheduledTaskSpec], data_dir: str | None = None) -> None:
        agent = SimpleNamespace(scheduled_tasks=tasks, scheduler_tick_seconds=60)
        self.config = SimpleNamespace(settings=SimpleNamespace(agent=agent))
        self.paths = SimpleNamespace(data_dir=data_dir)
        self.published: list[tuple[str, dict]] = []
        self.events = SimpleNamespace(publish=self._publish)
        
        self.ops: list[dict] = []
        
        
        
        
        self.audit = SimpleNamespace(op=self._record_op)

    def _publish(self, event_type: str, **data) -> None:
        self.published.append((event_type, data))

    async def _record_op(self, **payload) -> None:
        self.ops.append(payload)


def make_task(**overrides) -> ScheduledTaskSpec:
    payload = {
        "id": "daily",
        "name": "每日汇总",
        "prompt": "汇总一下",
        "interval_minutes": 60,
        "enabled": True,
    }
    payload.update(overrides)
    return ScheduledTaskSpec(**payload)


def make_scheduler(tasks, monkeypatch, data_dir: str | None = None) -> tuple[TaskScheduler, FakeRuntime]:
    runtime = FakeRuntime(tasks, data_dir=data_dir)
    scheduler = TaskScheduler(runtime)

    async def fake_execute(spec, *, resume=None):
        return f"session-{spec.id}"

    monkeypatch.setattr(scheduler, "_execute", fake_execute)
    return scheduler, runtime


class TestStartup:
    @pytest.mark.asyncio
    async def test_no_tasks_means_no_loop(self, monkeypatch):

        scheduler, _ = make_scheduler([], monkeypatch)

        await scheduler.start()

        assert scheduler.running is False

    @pytest.mark.asyncio
    async def test_no_history_means_seed_only(self, monkeypatch):






        scheduler, _ = make_scheduler([make_task()], monkeypatch)

        await scheduler.start()
        await scheduler._tick()

        assert scheduler._catch_up == {}
        assert scheduler.describe()[0]["running"] is False
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_disabled_task_never_fires(self, monkeypatch):
        scheduler, runtime = make_scheduler([make_task(enabled=False)], monkeypatch)
        await scheduler.start()
        
        scheduler._last_run["daily"] = time.time() - 99999

        await scheduler._tick()

        assert scheduler.describe()[0]["running"] is False
        assert runtime.published == []
        await scheduler.stop()


class TestTick:
    @pytest.mark.asyncio
    async def test_due_task_runs(self, monkeypatch):
        scheduler, _ = make_scheduler([make_task()], monkeypatch)
        await scheduler.start()
        scheduler._last_run["daily"] = time.time() - 3601  

        await scheduler._tick()
        await _drain()

        assert any(item["running"] is False for item in scheduler.describe())
        assert scheduler.describe()[0]["last_run_at"] is not None
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_reentry_does_not_double_fire(self, monkeypatch):






        scheduler, _ = make_scheduler([make_task()], monkeypatch)
        await scheduler.start()
        scheduler._last_run["daily"] = time.time() - 3601

        await scheduler._tick()
        await scheduler._tick()

        
        assert scheduler.describe()[0]["next_run_in_seconds"] > 3000
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_not_yet_due_is_skipped(self, monkeypatch):
        scheduler, _ = make_scheduler([make_task(interval_minutes=60)], monkeypatch)
        await scheduler.start()
        scheduler._last_run["daily"] = time.time() - 60  

        await scheduler._tick()

        assert scheduler.describe()[0]["running"] is False
        await scheduler.stop()


class TestRunNow:
    @pytest.mark.asyncio
    async def test_unknown_task_returns_false(self, monkeypatch):
        scheduler, _ = make_scheduler([make_task()], monkeypatch)

        assert await scheduler.run_now("nope") is False

    @pytest.mark.asyncio
    async def test_second_click_is_refused_while_running(self, monkeypatch):





        scheduler, _ = make_scheduler([make_task()], monkeypatch)
        scheduler._running.add("daily")

        assert await scheduler.run_now("daily") is False

    @pytest.mark.asyncio
    async def test_success_publishes_event(self, monkeypatch):
        scheduler, runtime = make_scheduler([make_task()], monkeypatch)

        assert await scheduler.run_now("daily") is True
        await _drain()

        events = [name for name, _ in runtime.published]
        assert "scheduled_task_done" in events
        payload = runtime.published[0][1]
        assert payload["session_id"] == "session-daily"
        
        
        assert runtime.ops and runtime.ops[-1]["action"] == "run"
        assert runtime.ops[-1]["target"] == "daily"
        assert runtime.ops[-1]["kind"] == "task"

    @pytest.mark.asyncio
    async def test_failure_publishes_failure_event(self, monkeypatch):
        scheduler, runtime = make_scheduler([make_task()], monkeypatch)

        async def boom(spec):
            raise RuntimeError("模型挂了")

        monkeypatch.setattr(scheduler, "_execute", boom)

        await scheduler.run_now("daily")
        await _drain()

        assert runtime.published[0][0] == "scheduled_task_failed"
        
        assert scheduler.describe()[0]["running"] is False


class TestSilent:







    @pytest.mark.asyncio
    async def test_done_is_quiet_but_still_recorded(self, monkeypatch):
        scheduler, runtime = make_scheduler([make_task(silent=True)], monkeypatch)

        assert await scheduler.run_now("daily") is True
        await _drain()

        assert runtime.published == []
        assert runtime.ops[-1]["action"] == "run"
        assert runtime.ops[-1]["target"] == "daily"

    @pytest.mark.asyncio
    async def test_failure_is_quiet_but_still_recorded(self, monkeypatch):
        scheduler, runtime = make_scheduler([make_task(silent=True)], monkeypatch)

        async def boom(spec):
            raise RuntimeError("模型挂了")

        monkeypatch.setattr(scheduler, "_execute", boom)
        await scheduler.run_now("daily")
        await _drain()

        assert runtime.published == []
        assert runtime.ops[-1]["action"] == "fail"

    @pytest.mark.asyncio
    async def test_loud_task_still_publishes(self, monkeypatch):

        scheduler, runtime = make_scheduler([make_task()], monkeypatch)

        await scheduler.run_now("daily")
        await _drain()

        assert [name for name, _ in runtime.published] == ["scheduled_task_done"]


async def _drain() -> None:




    import asyncio

    for _ in range(5):
        await asyncio.sleep(0)


def _ts(text: str) -> float:

    from datetime import datetime

    return datetime.strptime(text, "%Y-%m-%d %H:%M").timestamp()





class TestTimeTriggers:






    def _pair(self, monkeypatch, **overrides):
        spec = make_task(**overrides)
        scheduler, _ = make_scheduler([spec], monkeypatch)
        return scheduler, spec

    def test_daily_not_due_before_its_time(self, monkeypatch):
        scheduler, spec = self._pair(monkeypatch, trigger="daily", at_time="09:00")
        scheduler._last_run[spec.id] = _ts("2026-09-22 10:00")

        assert scheduler._is_due(spec, _ts("2026-09-23 08:00")) is False

    def test_daily_due_after_its_time(self, monkeypatch):
        scheduler, spec = self._pair(monkeypatch, trigger="daily", at_time="09:00")
        scheduler._last_run[spec.id] = _ts("2026-09-22 10:00")

        assert scheduler._is_due(spec, _ts("2026-09-23 09:30")) is True

    def test_daily_does_not_backfill_today(self, monkeypatch):





        scheduler, spec = self._pair(monkeypatch, trigger="daily", at_time="09:00")
        
        scheduler._last_run[spec.id] = _ts("2026-09-23 09:30")

        assert scheduler._is_due(spec, _ts("2026-09-23 18:00")) is False

    def test_weekly_only_on_its_weekday(self, monkeypatch):
        
        scheduler, spec = self._pair(monkeypatch, trigger="weekly", at_time="09:00", weekday=2)
        scheduler._last_run[spec.id] = _ts("2026-09-16 09:00")

        assert scheduler._is_due(spec, _ts("2026-09-23 09:30")) is True
        
        scheduler._last_run[spec.id] = _ts("2026-09-23 09:30")
        assert scheduler._is_due(spec, _ts("2026-09-23 20:00")) is False

    def test_weekly_waits_a_week(self, monkeypatch):
        scheduler, spec = self._pair(monkeypatch, trigger="weekly", at_time="09:00", weekday=2)
        scheduler._last_run[spec.id] = _ts("2026-09-23 09:30")

        
        assert scheduler._is_due(spec, _ts("2026-09-24 09:30")) is False
        assert scheduler._is_due(spec, _ts("2026-09-25 09:30")) is False

    def test_next_run_countdown_skips_finished_occurrence(self, monkeypatch):

        scheduler, spec = self._pair(monkeypatch, trigger="daily", at_time="09:00")
        scheduler._last_run[spec.id] = _ts("2026-09-23 09:10")

        remaining = scheduler._next_run_in_seconds(spec, _ts("2026-09-23 10:00"))

        assert 22 * 3600 < remaining < 23.5 * 3600, "应当指向明天 09:00"





class TestStartAt:






    def _pair(self, monkeypatch, **overrides):
        spec = make_task(**overrides)
        scheduler, _ = make_scheduler([spec], monkeypatch)
        return scheduler, spec

    def test_not_due_before_start(self, monkeypatch):
        scheduler, spec = self._pair(
            monkeypatch, trigger="interval", interval_minutes=30, start_at="2026-09-30T10:00"
        )
        scheduler._last_run[spec.id] = _ts("2026-09-30 09:00")

        assert scheduler._is_due(spec, _ts("2026-09-30 09:59")) is False

    def test_first_run_is_exactly_at_start(self, monkeypatch):






        scheduler, spec = self._pair(
            monkeypatch, trigger="interval", interval_minutes=30, start_at="2026-09-30T10:00"
        )
        scheduler._last_run[spec.id] = _ts("2026-09-30 09:55")

        assert scheduler._is_due(spec, _ts("2026-09-30 10:00")) is True

    def test_waits_a_full_interval_after_start(self, monkeypatch):
        scheduler, spec = self._pair(
            monkeypatch, trigger="interval", interval_minutes=30, start_at="2026-09-30T10:00"
        )
        scheduler._last_run[spec.id] = _ts("2026-09-30 10:00")

        assert scheduler._is_due(spec, _ts("2026-09-30 10:29")) is False
        assert scheduler._is_due(spec, _ts("2026-09-30 10:30")) is True

    def test_empty_start_keeps_old_behaviour(self, monkeypatch):

        scheduler, spec = self._pair(monkeypatch, trigger="interval", interval_minutes=60)
        assert spec.start_at == ""
        scheduler._last_run[spec.id] = _ts("2026-09-30 10:00")

        assert scheduler._is_due(spec, _ts("2026-09-30 10:30")) is False
        assert scheduler._is_due(spec, _ts("2026-09-30 11:00")) is True

    def test_countdown_points_at_start(self, monkeypatch):

        scheduler, spec = self._pair(
            monkeypatch, trigger="interval", interval_minutes=30, start_at="2026-09-30T10:00"
        )
        scheduler._last_run[spec.id] = _ts("2026-09-30 09:00")

        assert scheduler._next_run_in_seconds(spec, _ts("2026-09-30 09:40")) == 20 * 60

    def test_future_start_is_never_treated_as_missed(self, monkeypatch):

        spec = make_task(
            id="hourly", trigger="interval", interval_minutes=30, start_at="2026-09-30T10:00"
        )
        scheduler, _ = make_scheduler([spec], monkeypatch)
        scheduler._first_seen[spec.id] = _ts("2026-09-30 08:00")

        assert scheduler._overdue_point(spec, _ts("2026-09-30 09:00")) is None

    def test_bad_start_at_is_ignored(self, monkeypatch):

        scheduler, spec = self._pair(monkeypatch, trigger="interval", interval_minutes=60)
        spec.start_at = "2026-09-30 10:00"  
        scheduler._last_run[spec.id] = _ts("2026-09-30 10:00")

        assert scheduler._start_point(spec) is None
        assert scheduler._is_due(spec, _ts("2026-09-30 11:00")) is True

    def test_schema_rejects_bad_format(self):

        with pytest.raises(ValueError):
            make_task(start_at="2026/09/30 10:00")

    def test_describe_mentions_start(self):

        spec = make_task(trigger="interval", interval_minutes=120, start_at="2026-09-30T10:03")

        assert describe_schedule(spec) == "自 2026年9月30日 10:03 起，每 2 小时"





def _hhmm(ts: float) -> str:





    return datetime.fromtimestamp(ts).strftime("%H:%M")


class TestCatchUp:






    def _state(self, tmp_path, task_id: str = "daily", **entries: float) -> None:

        (tmp_path / STATE_FILENAME).write_text(
            json.dumps({"version": STATE_VERSION, "tasks": {task_id: entries}}),
            encoding="utf-8",
        )

    @pytest.mark.asyncio
    async def test_missed_daily_is_caught_up_once(self, monkeypatch, tmp_path):
        now = time.time()
        spec = make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))
        self._state(tmp_path, first_seen_at=now - 5 * 86400, last_run_at=now - 3 * 86400)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()

        assert spec.id in scheduler._catch_up, "两小时前那一次没跑过，应当补"

        await scheduler._tick()
        await _drain()

        assert runtime.published[0][0] == "scheduled_task_done"
        
        
        assert "补跑" in runtime.published[0][1]["message"]
        assert "补跑" in runtime.ops[-1]["detail"]
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_missed_silent_task_is_caught_up_quietly(self, monkeypatch, tmp_path):





        now = time.time()
        spec = make_task(silent=True, interval_minutes=60)
        self._state(tmp_path, first_seen_at=now - 2 * 86400, last_run_at=now - 3 * 3600)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        assert spec.id in scheduler._catch_up, "关着的时候错过的那一轮应当补"
        await scheduler._tick()
        await _drain()

        assert runtime.published == []
        
        assert "补跑" in runtime.ops[-1]["detail"]
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_already_ran_before_restart_is_not_caught_up(self, monkeypatch, tmp_path):




        now = time.time()
        spec = make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))
        self._state(tmp_path, first_seen_at=now - 5 * 86400, last_run_at=now - 3600)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()
        await _drain()

        assert scheduler._catch_up == {}
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_interval_overdue_is_caught_up_and_recounted(self, monkeypatch, tmp_path):

        now = time.time()
        spec = make_task(interval_minutes=60)
        self._state(tmp_path, first_seen_at=now - 2 * 86400, last_run_at=now - 3 * 3600)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        assert spec.id in scheduler._catch_up

        await scheduler._tick()
        await _drain()

        assert runtime.published[0][0] == "scheduled_task_done"
        
        
        assert 3500 < scheduler.describe()[0]["next_run_in_seconds"] <= 3600
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_interval_just_ran_is_not_caught_up(self, monkeypatch, tmp_path):

        now = time.time()
        spec = make_task(interval_minutes=60)
        self._state(tmp_path, first_seen_at=now - 2 * 86400, last_run_at=now - 600)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()
        await _drain()

        assert scheduler._catch_up == {}
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_interval_missed_too_long_ago_is_not_caught_up(self, monkeypatch, tmp_path):

        now = time.time()
        spec = make_task(interval_minutes=60)
        self._state(tmp_path, first_seen_at=now - 9 * 86400, last_run_at=now - 5 * 86400)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()
        await _drain()

        assert scheduler._catch_up == {}
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_weekly_missed_two_days_ago_is_not_caught_up(self, monkeypatch, tmp_path):






        now = time.time()
        spec = make_task(
            trigger="weekly",
            at_time=_hhmm(now - 2 * 3600),
            weekday=(datetime.fromtimestamp(now).weekday() - 2) % 7,
        )
        self._state(tmp_path, first_seen_at=now - 30 * 86400, last_run_at=now - 20 * 86400)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()
        await _drain()

        assert scheduler._catch_up == {}
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_new_task_is_not_caught_up(self, monkeypatch, tmp_path):

        now = time.time()
        spec = make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()
        await _drain()

        assert scheduler._catch_up == {}
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_condition_task_only_rebuilds_baseline(self, monkeypatch, tmp_path):





        import my_agent.utils.http as http_module

        holder = {"body": b"<html>v1</html>"}
        monkeypatch.setattr(http_module, "async_client", lambda **kw: _FakeClient(holder))
        now = time.time()
        spec = make_task(
            trigger="daily",
            at_time=_hhmm(now - 2 * 3600),
            condition="url_changed",
            condition_target="https://example.com/feed",
        )
        self._state(tmp_path, first_seen_at=now - 5 * 86400, last_run_at=now - 3 * 86400)
        scheduler, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        assert spec.id in scheduler._catch_up

        await scheduler._tick()
        await _drain()
        assert runtime.published == []

        
        assert scheduler._catch_up == {}
        await scheduler._tick()
        await _drain()
        assert runtime.published == []
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_manual_run_also_marks_handled(self, monkeypatch, tmp_path):

        now = time.time()
        spec = make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))

        first, _ = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))
        await first.start()
        assert await first.run_now(spec.id) is True
        await _drain()
        await first.stop()
        handled_at = first._last_exec[spec.id]

        second, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))
        await second.start()
        await second._tick()
        await _drain()

        assert second._catch_up == {}
        assert runtime.published == []
        
        
        assert second.describe()[0]["last_run_at"] == handled_at
        await second.stop()

    @pytest.mark.asyncio
    async def test_catch_up_is_not_repeated_across_restarts(self, monkeypatch, tmp_path):

        now = time.time()
        spec = make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))
        self._state(tmp_path, first_seen_at=now - 5 * 86400, last_run_at=now - 3 * 86400)

        first, _ = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))
        await first.start()
        await first._tick()
        await _drain()
        await first.stop()

        second, runtime = make_scheduler([spec], monkeypatch, data_dir=str(tmp_path))
        await second.start()
        await second._tick()
        await _drain()

        assert second._catch_up == {}
        assert runtime.published == []
        await second.stop()

    @pytest.mark.asyncio
    async def test_corrupt_state_file_does_not_break_startup(self, monkeypatch, tmp_path):

        (tmp_path / STATE_FILENAME).write_text("{ 这不是 JSON", encoding="utf-8")
        scheduler, _ = make_scheduler([make_task()], monkeypatch, data_dir=str(tmp_path))

        await scheduler.start()
        await scheduler._tick()

        assert scheduler.running is True
        assert scheduler._catch_up == {}
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_unknown_state_version_is_discarded(self, monkeypatch, tmp_path):

        now = time.time()
        (tmp_path / STATE_FILENAME).write_text(
            json.dumps({"version": 999, "tasks": {"daily": {"last_run_at": now - 86400}}}),
            encoding="utf-8",
        )
        scheduler, _ = make_scheduler(
            [make_task(trigger="daily", at_time=_hhmm(now - 2 * 3600))],
            monkeypatch,
            data_dir=str(tmp_path),
        )

        await scheduler.start()

        assert scheduler._catch_up == {}
        await scheduler.stop()





class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.content = body

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self, chunk_size: int | None = None):







        
        half = max(1, len(self.content) // 2)
        yield self.content[:half]
        if self.content[half:]:
            yield self.content[half:]


class _FakeStream:


    def __init__(self, body: bytes) -> None:
        self._body = body

    async def __aenter__(self) -> _FakeResponse:
        return _FakeResponse(self._body)

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeClient:


    def __init__(self, holder: dict[str, bytes]) -> None:
        self._holder = holder

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(self, url: str) -> _FakeResponse:
        return _FakeResponse(self._holder["body"])

    def stream(self, method: str, url: str) -> _FakeStream:
        
        return _FakeStream(self._holder["body"])


class TestConditions:
    @pytest.mark.asyncio
    async def test_no_condition_always_passes(self, monkeypatch):
        scheduler, _ = make_scheduler([make_task()], monkeypatch)

        assert await scheduler._condition_met(scheduler._specs()[0]) is True

    @pytest.mark.asyncio
    async def test_url_condition_needs_a_real_change(self, monkeypatch):
        import my_agent.utils.http as http_module

        holder = {"body": b"<html>v1</html>"}
        monkeypatch.setattr(http_module, "async_client", lambda **kw: _FakeClient(holder))
        spec = make_task(condition="url_changed", condition_target="https://example.com/feed")
        scheduler, runtime = make_scheduler([spec], monkeypatch)

        
        assert await scheduler._condition_met(spec) is False
        assert await scheduler._condition_met(spec) is False

        holder["body"] = "<html>v2 有更新</html>".encode()

        assert await scheduler._condition_met(spec) is True
        assert runtime.published == [], "内容变了不是失败，不该推失败通知"

    @pytest.mark.asyncio
    async def test_url_condition_only_reads_up_to_the_cap(self, monkeypatch, caplog):









        import logging

        import my_agent.utils.http as http_module
        from my_agent.agent.scheduler import CONDITION_MAX_BYTES

        holder = {"body": b"<html>" + b"x" * CONDITION_MAX_BYTES + b"</html>"}
        monkeypatch.setattr(http_module, "async_client", lambda **kw: _FakeClient(holder))
        spec = make_task(condition="url_changed", condition_target="https://example.com/big")
        scheduler, _ = make_scheduler([spec], monkeypatch)

        with caplog.at_level(logging.INFO):
            assert await scheduler._condition_met(spec) is False  
        assert "已截断" in caplog.text, "截断必须写进日志，否则事后会当成抓取失败去查"

        
        holder["body"] = holder["body"] + b"<!-- changed far beyond the cap -->"
        assert await scheduler._condition_met(spec) is False

        
        holder["body"] = b"<htmX>" + holder["body"][6:]
        assert await scheduler._condition_met(spec) is True

    @pytest.mark.asyncio
    async def test_url_condition_rejects_metadata_address(self, monkeypatch):

        spec = make_task(
            condition="url_changed",
            condition_target="http://169.254.169.254/latest/meta-data/",
        )
        scheduler, runtime = make_scheduler([spec], monkeypatch)

        assert await scheduler._condition_met(spec) is False
        assert runtime.published[-1][0] == "scheduled_task_failed"

    @pytest.mark.asyncio
    async def test_condition_failure_is_reported_only_once(self, monkeypatch):

        spec = make_task(condition="file_changed", condition_target="D:/根本不存在的目录/x.txt")
        scheduler, runtime = make_scheduler([spec], monkeypatch)

        await scheduler._condition_met(spec)
        await scheduler._condition_met(spec)

        events = [name for name, _ in runtime.published]
        assert events.count("scheduled_task_failed") == 1

    @pytest.mark.asyncio
    async def test_file_condition_needs_an_update(self, monkeypatch, tmp_path):
        target = tmp_path / "report.txt"
        target.write_text("v1", encoding="utf-8")
        spec = make_task(condition="file_changed", condition_target=str(target))
        scheduler, _ = make_scheduler([spec], monkeypatch)

        assert await scheduler._condition_met(spec) is False
        assert await scheduler._condition_met(spec) is False

        target.write_text("v2 更长的内容", encoding="utf-8")

        assert await scheduler._condition_met(spec) is True


class TestTickWithCondition:
    @pytest.mark.asyncio
    async def test_gated_tick_advances_the_clock(self, monkeypatch):





        spec = make_task(condition="url_changed", condition_target="https://example.com/a")
        scheduler, _ = make_scheduler([spec], monkeypatch)
        await scheduler.start()
        scheduler._last_run[spec.id] = time.time() - 3601

        async def not_yet(_spec) -> bool:
            return False

        monkeypatch.setattr(scheduler, "_condition_met", not_yet)

        await scheduler._tick()

        assert scheduler.describe()[0]["running"] is False
        assert scheduler.describe()[0]["next_run_in_seconds"] > 3000
        await scheduler.stop()





class TestSessionOwner:







    class _Assistant:
        def __init__(self, assistant_id: str, sort_order: int = 0) -> None:
            self.id = assistant_id
            self.name = assistant_id
            self.sort_order = sort_order

    class _Assistants:
        def __init__(self, items, default: str = "") -> None:
            self.assistants = items
            self.default_assistant = default

        def get(self, assistant_id: str):
            return next((item for item in self.assistants if item.id == assistant_id), None)

        def sorted(self):
            return sorted(self.assistants, key=lambda item: item.sort_order)

    def _runtime(self, items, default: str = ""):
        assistants = self._Assistants(items, default)
        return SimpleNamespace(
            assistants=assistants,
            resolve_assistant=lambda assistant_id: assistants.get(assistant_id)
            if assistant_id
            else None,
        )

    def _scheduler(self) -> TaskScheduler:
        return TaskScheduler(SimpleNamespace())

    def test_uses_the_task_assistant_when_it_exists(self):
        runtime = self._runtime([self._Assistant("a"), self._Assistant("b", 1)], default="a")

        assert self._scheduler()._resolve_runner(runtime, make_task(assistant_id="b")).id == "b"

    def test_falls_back_to_default_when_assistant_is_missing(self):
        runtime = self._runtime([self._Assistant("a"), self._Assistant("b", 1)], default="b")

        assert self._scheduler()._resolve_runner(runtime, make_task(assistant_id="被删掉的")).id == "b"
        assert self._scheduler()._resolve_runner(runtime, make_task(assistant_id="")).id == "b"

    def test_falls_back_to_first_assistant_without_a_default(self):
        runtime = self._runtime([self._Assistant("later", 5), self._Assistant("first", 1)])

        assert self._scheduler()._resolve_runner(runtime, make_task()).id == "first"

    def test_no_assistant_at_all_keeps_it_empty(self):

        runtime = self._runtime([])

        assert self._scheduler()._resolve_runner(runtime, make_task()) is None


class TestRestart:
    @pytest.mark.asyncio
    async def test_keeps_existing_timers_and_drops_removed(self, monkeypatch):

        first = make_task(id="a", name="甲")
        second = make_task(id="b", name="乙")
        scheduler, runtime = make_scheduler([first, second], monkeypatch)
        await scheduler.start()
        stamp = time.time() - 1000
        scheduler._last_run["a"] = stamp
        scheduler._last_run["b"] = stamp

        runtime.config.settings.agent.scheduled_tasks = [first]
        await scheduler.restart()

        assert scheduler._last_run["a"] == stamp
        assert "b" not in scheduler._last_run
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_new_task_starts_from_now(self, monkeypatch):

        first = make_task(id="a")
        scheduler, runtime = make_scheduler([first], monkeypatch)
        await scheduler.start()
        fresh = make_task(id="c", name="新的")
        runtime.config.settings.agent.scheduled_tasks = [first, fresh]

        await scheduler.restart()

        assert "c" in scheduler._last_run
        assert scheduler._next_run_in_seconds(fresh, time.time()) > 3000
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_restart_starts_the_loop_when_first_task_appears(self, monkeypatch):

        scheduler, runtime = make_scheduler([], monkeypatch)
        await scheduler.start()
        assert scheduler.running is False

        runtime.config.settings.agent.scheduled_tasks = [make_task()]
        await scheduler.restart()

        assert scheduler.running is True
        await scheduler.stop()
