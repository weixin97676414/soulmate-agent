




















from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from xml.etree import ElementTree

from ..config.schemas import CalendarSettings
from ..errors import ConfigError
from ..security.urls import validate_endpoint
from ..utils.http import async_client
from .ics import CalendarEvent, apply_changes, build_ics, events_in_range, parse_events

logger = logging.getLogger(__name__)

_DAV_NS = "DAV:"
_CALDAV_NS = "urn:ietf:params:xml:ns:caldav"


class CalendarError(Exception):






    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class CalendarBackend(Protocol):


    label: str

    async def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]: ...

    async def create_event(self, event: CalendarEvent) -> CalendarEvent: ...

    async def update_event(self, uid: str, changes: dict[str, Any]) -> CalendarEvent: ...

    async def delete_event(self, uid: str) -> bool: ...





class LocalIcsBackend:








    def __init__(
        self,
        path: Path,
        *,
        calendar_name: str,
        default_duration: timedelta | None = None,
    ) -> None:
        self.path = path
        self.calendar_name = calendar_name
        
        
        self._default_duration = default_duration or timedelta(minutes=60)

    @property
    def label(self) -> str:
        return f"本地日历（{self.path.name}）"

    def _read(self) -> list[CalendarEvent]:
        if not self.path.is_file():
            return []
        try:
            return parse_events(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CalendarError(f"日历文件读不出来：{exc}") from exc

    def _write(self, events: list[CalendarEvent]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = build_ics(events, calendar_name=self.calendar_name)
        
        tmp = self.path.with_suffix(".ics.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.path)

    async def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        
        import asyncio

        events = await asyncio.to_thread(self._read)
        return events_in_range(events, start, end)

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        import asyncio

        def _create() -> CalendarEvent:
            events = self._read()
            if event.uid in {item.uid for item in events}:
                event.uid = uuid.uuid4().hex
            events.append(event)
            self._write(events)
            return event

        return await asyncio.to_thread(_create)

    async def update_event(self, uid: str, changes: dict[str, Any]) -> CalendarEvent:
        import asyncio

        def _update() -> CalendarEvent:
            events = self._read()
            for index, item in enumerate(events):
                if item.uid != uid:
                    continue
                
                
                try:
                    updated = apply_changes(item, changes, default_duration=self._default_duration)
                except ValueError as exc:
                    raise CalendarError(str(exc)) from exc
                events[index] = updated
                self._write(events)
                return updated
            raise CalendarError(f"没有找到日程：{uid}")

        return await asyncio.to_thread(_update)

    async def delete_event(self, uid: str) -> bool:
        import asyncio

        def _delete() -> bool:
            events = self._read()
            remaining = [item for item in events if item.uid != uid]
            if len(remaining) == len(events):
                return False
            self._write(remaining)
            return True

        return await asyncio.to_thread(_delete)





class CalDavBackend:







    def __init__(self, settings: CalendarSettings) -> None:
        self._settings = settings
        self._collection: str | None = None

    @property
    def label(self) -> str:
        return f"在线日历（{self._settings.caldav_url}）"

    
    def _base_url(self) -> str:
        url = (self._settings.caldav_url or "").strip()
        try:
            validate_endpoint(url, field="CalDAV 地址")
        except ConfigError as exc:
            raise CalendarError(exc.message) from exc
        return url

    def _auth(self) -> Any:
        import httpx

        username = (self._settings.caldav_username or "").strip()
        password = self._settings.caldav_password or ""
        if not username or not password:
            raise CalendarError("还没填 CalDAV 账号或密码，请到「设置 → 日历」补齐。")
        return httpx.BasicAuth(username, password)

    async def _request(
        self, method: str, url: str, *, body: str | None = None, headers: dict[str, str] | None
    ) -> Any:
        import httpx

        request_headers = {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"}
        request_headers.update(headers or {})
        try:
            async with async_client(timeout=30.0) as client:
                response = await client.request(
                    method,
                    url,
                    content=body.encode("utf-8") if body is not None else None,
                    headers=request_headers,
                    auth=self._auth(),
                )
        except httpx.HTTPError as exc:
            raise CalendarError(f"连不上日历服务：{exc}") from exc

        if response.status_code in (401, 403):
            raise CalendarError("日历服务拒绝了这个账号（检查账号密码是否写对）。")
        return response

    
    async def _resolve_collection(self) -> str:
        if self._collection:
            return self._collection

        base = self._base_url()
        
        probe = await self._request(
            "PROPFIND",
            base,
            body=(
                '<?xml version="1.0" encoding="utf-8"?>'
                f'<d:propfind xmlns:d="{_DAV_NS}"><d:prop><d:resourcetype/></d:prop></d:propfind>'
            ),
            headers=None,
        )
        if probe.status_code < 400 and "calendar" in probe.text:
            self._collection = base if base.endswith("/") else f"{base}/"
            return self._collection

        
        principal = await self._discover_href(
            base, f'<d:propfind xmlns:d="{_DAV_NS}"><d:prop><d:current-user-principal/></d:prop></d:propfind>'
        )
        if principal:
            home = await self._discover_href(
                principal,
                f'<d:propfind xmlns:d="{_DAV_NS}" xmlns:c="{_CALDAV_NS}">'
                "<d:prop><c:calendar-home-set/></d:prop></d:propfind>",
            )
            if home:
                listing = await self._request(
                    "PROPFIND",
                    home,
                    body=(
                        '<?xml version="1.0" encoding="utf-8"?>'
                        f'<d:propfind xmlns:d="{_DAV_NS}"><d:prop><d:resourcetype/></d:prop></d:propfind>'
                    ),
                    headers=None,
                )
                if listing.status_code < 400:
                    for href in self._calendar_hrefs(listing.text):
                        self._collection = href
                        return href

        raise CalendarError(
            "在那个地址上找不到日历集合。很多服务商给的首页不是日历本身 —— "
            "请在「设置 → 日历」里填**日历集合**的地址（通常在账号首页下面，"
            "形如 …/calendars/你的账号/个人日历/）。"
        )

    async def _discover_href(self, url: str, body: str) -> str:
        response = await self._request("PROPFIND", url, body=body, headers=None)
        if response.status_code >= 400:
            return ""
        return self._first_href(response.text)

    @staticmethod
    def _first_href(xml_text: str) -> str:

        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return ""
        for element in root.iter():
            if element.tag.endswith("href") and (element.text or "").strip():
                return element.text.strip()
        return ""

    @staticmethod
    def _calendar_hrefs(xml_text: str) -> list[str]:

        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return []
        hrefs: list[str] = []
        for response in root.iter(f"{{{_DAV_NS}}}response"):
            is_calendar = any(
                element.tag == f"{{{_CALDAV_NS}}}calendar" for element in response.iter()
            )
            if not is_calendar:
                continue
            for element in response.iter():
                if element.tag.endswith("href") and (element.text or "").strip():
                    hrefs.append(element.text.strip())
                    break
        return hrefs

    
    async def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        collection = await self._resolve_collection()
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            f'<c:calendar-query xmlns:d="{_DAV_NS}" xmlns:c="{_CALDAV_NS}">'
            "<d:prop><d:getetag/><c:calendar-data/></d:prop>"
            "<c:filter><c:time-range "
            f'start="{start:%Y%m%dT%H%M%S}Z" end="{end:%Y%m%dT%H%M%S}Z"/></c:filter>'
            "</c:calendar-query>"
        )
        response = await self._request("REPORT", collection, body=body, headers=None)
        if response.status_code >= 400:
            raise CalendarError(
                f"日历服务返回 {response.status_code}，读不到日程。", detail=response.text[:200]
            )

        events: list[CalendarEvent] = []
        try:
            root = ElementTree.fromstring(response.text)
        except ElementTree.ParseError as exc:
            raise CalendarError("日历服务返回的内容不是合法的 XML。", detail=str(exc)) from exc

        for element in root.iter():
            if not element.tag.endswith("calendar-data"):
                continue
            events.extend(parse_events(element.text or ""))
        return events_in_range(events, start, end)

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        collection = await self._resolve_collection()
        url = f"{collection}{event.uid}.ics" if collection.endswith("/") else f"{collection}/{event.uid}.ics"
        response = await self._request(
            "PUT",
            url,
            body=build_ics([event]),
            headers={
                "Content-Type": "text/calendar; charset=utf-8",
                
                "If-None-Match": "*",
            },
        )
        if response.status_code >= 400:
            raise CalendarError(
                f"写入日历失败（HTTP {response.status_code}）。", detail=response.text[:200]
            )
        return event

    async def update_event(self, uid: str, changes: dict[str, Any]) -> CalendarEvent:
        target = await self._find_event(uid)
        
        try:
            updated = apply_changes(
                target,
                changes,
                default_duration=timedelta(minutes=self._settings.default_duration_minutes),
            )
        except ValueError as exc:
            raise CalendarError(str(exc)) from exc
        collection = await self._resolve_collection()
        url = f"{collection}{uid}.ics" if collection.endswith("/") else f"{collection}/{uid}.ics"
        response = await self._request(
            "PUT",
            url,
            body=build_ics([updated]),
            headers={"Content-Type": "text/calendar; charset=utf-8"},
        )
        if response.status_code >= 400:
            raise CalendarError(
                f"更新日程失败（HTTP {response.status_code}）。", detail=response.text[:200]
            )
        return updated

    async def delete_event(self, uid: str) -> bool:
        await self._find_event(uid)
        collection = await self._resolve_collection()
        url = f"{collection}{uid}.ics" if collection.endswith("/") else f"{collection}/{uid}.ics"
        response = await self._request("DELETE", url, headers=None)
        return response.status_code < 400

    async def _find_event(self, uid: str) -> CalendarEvent:
        
        
        now = datetime.now()
        events = await self.list_events(now - timedelta(days=365), now + timedelta(days=365))
        found = next((item for item in events if item.uid == uid), None)
        if found is None:
            raise CalendarError(f"没有找到日程：{uid}")
        return found





class CalendarService:


    def __init__(self, settings: CalendarSettings, paths: Any) -> None:
        self._settings = settings
        self._paths = paths

    def _local_backend(self) -> LocalIcsBackend:
        root = Path(getattr(self._paths, "root", Path.cwd()))
        return LocalIcsBackend(
            root / "calendar" / "local.ics",
            calendar_name=self._settings.calendar_name,
            default_duration=self.default_duration,
        )

    def _backend(self) -> CalendarBackend:
        mode = self._settings.mode
        configured = bool(self._settings.caldav_url and self._settings.caldav_username)
        if mode == "local" or (mode == "auto" and not configured):
            return self._local_backend()
        return CalDavBackend(self._settings)

    def describe_backend(self) -> str:

        return self._backend().label

    @property
    def default_duration(self) -> timedelta:
        return timedelta(minutes=self._settings.default_duration_minutes)

    async def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        return await self._backend().list_events(start, end)

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        return await self._backend().create_event(event)

    async def update_event(self, uid: str, changes: dict[str, Any]) -> CalendarEvent:
        return await self._backend().update_event(uid, changes)

    async def delete_event(self, uid: str) -> bool:
        return await self._backend().delete_event(uid)

    async def test_connection(self) -> dict[str, Any]:

        if not (self._settings.caldav_url and self._settings.caldav_username):
            raise CalendarError("还没填 CalDAV 地址或账号。")
        backend = CalDavBackend(self._settings)
        now = datetime.now()
        events = await backend.list_events(now - timedelta(days=7), now + timedelta(days=30))
        return {
            "ok": True,
            "backend": backend.label,
            "upcoming": len(events),
            "sample": [item.to_dict() for item in events[:3]],
        }
