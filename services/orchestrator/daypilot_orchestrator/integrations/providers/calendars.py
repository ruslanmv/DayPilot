"""Calendar providers — Google Calendar and Microsoft 365 (Outlook).

Both expose the **same canonical capability ids**, so nothing downstream — the
planner, the meeting-context assembler, the UI — has to branch on vendor:

    events.read     READ    occurrences in a window
    event.read      READ    one event, with attendees and body
    freebusy.read   READ    availability
    events.write    WRITE   create / update / move   (approval-gated)

`microsoft_calendar` reads through Graph's ``calendarView``, which returns the
actual **occurrences** in a range — including exceptions to recurring series —
rather than series masters a planner would have to expand itself. Follow-up
syncs use ``calendarView/delta`` so a local store stays current without
refetching the calendar.

Two Graph details are load-bearing:

* ``Prefer: IdType="ImmutableId"`` — an ordinary Outlook event id changes when
  the item moves between folders, which would silently duplicate rows in the
  local store on the next sync.
* ``Prefer: outlook.timezone="UTC"`` — otherwise start/end come back in the
  mailbox's timezone with no offset, and a plan built from them is wrong by
  however far the user is from their mailbox setting.

The provider registration for Google was historically ``"calendar"``, which
asserted that Calendar means Google. It is now registered under its real name
with the old id kept as an alias so existing connections keep resolving.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..provider import Capability, CapabilityKind, IntegrationError
from ..registry import register_provider
from .extra import _BearerProvider

GOOGLE_CAL_API = "https://www.googleapis.com/calendar/v3"
MS_GRAPH_API = "https://graph.microsoft.com/v1.0"

#: Every calendar provider answers to these ids.
CALENDAR_CAPABILITIES = (
    Capability("events.read", CapabilityKind.READ, "Read calendar events."),
    Capability("event.read", CapabilityKind.READ, "Read one event with attendees."),
    Capability("freebusy.read", CapabilityKind.READ, "Read availability."),
    Capability("events.write", CapabilityKind.WRITE, "Create/move events (approval-gated)."),
)


class GoogleCalendarProvider(_BearerProvider):
    provider = "google_calendar"
    base_url = GOOGLE_CAL_API

    def _verify_path(self) -> str:
        return "/users/me/calendarList"

    def list_capabilities(self) -> list[Capability]:
        return list(CALENDAR_CAPABILITIES)

    def execute(self, action: str, payload: Any) -> Any:
        if not self._token:
            raise IntegrationError("not connected")
        payload = payload or {}
        cal = payload.get("calendarId", "primary")
        with self._client() as client:
            if action == "events.read":
                params = {"singleEvents": "true", "orderBy": "startTime"}
                if payload.get("startAt"):
                    params["timeMin"] = payload["startAt"]
                if payload.get("endAt"):
                    params["timeMax"] = payload["endAt"]
                r = client.get(f"/calendars/{cal}/events", params=params)
            elif action == "event.read":
                r = client.get(f"/calendars/{cal}/events/{payload.get('eventId', '')}")
            elif action == "freebusy.read":
                r = client.post("/freeBusy", json={
                    "timeMin": payload.get("startAt"), "timeMax": payload.get("endAt"),
                    "items": [{"id": cal}],
                })
            elif action == "events.write":
                r = client.post(f"/calendars/{cal}/events", json=payload.get("event", {}))
            else:
                raise IntegrationError(f"unknown action '{action}'")
            r.raise_for_status()
            return r.json()


class MicrosoftCalendarProvider(_BearerProvider):
    """Microsoft 365 / Outlook calendar over Microsoft Graph."""

    provider = "microsoft_calendar"
    base_url = MS_GRAPH_API

    #: Immutable ids and UTC times, for the reasons in the module docstring.
    _prefer = 'IdType="ImmutableId", outlook.timezone="UTC"'

    def _client(self) -> httpx.Client:
        client = super()._client()
        client.headers["Prefer"] = self._prefer
        return client

    def _verify_path(self) -> str:
        return "/me/calendars"

    def list_capabilities(self) -> list[Capability]:
        return list(CALENDAR_CAPABILITIES)

    def execute(self, action: str, payload: Any) -> Any:
        if not self._token:
            raise IntegrationError("not connected")
        payload = payload or {}
        with self._client() as client:
            if action == "events.read":
                # A stored deltaLink is an absolute URL and already carries the
                # window; following it is how a sync stays incremental.
                delta_link = payload.get("deltaLink")
                if delta_link:
                    r = client.get(delta_link)
                else:
                    r = client.get("/me/calendarView", params={
                        "startDateTime": payload.get("startAt", ""),
                        "endDateTime": payload.get("endAt", ""),
                        "$top": str(payload.get("limit", 100)),
                    })
            elif action == "event.read":
                r = client.get(f"/me/events/{payload.get('eventId', '')}")
            elif action == "freebusy.read":
                r = client.post("/me/calendar/getSchedule", json={
                    "schedules": payload.get("schedules", []),
                    "startTime": {"dateTime": payload.get("startAt"), "timeZone": "UTC"},
                    "endTime": {"dateTime": payload.get("endAt"), "timeZone": "UTC"},
                })
            elif action == "events.write":
                r = client.post("/me/events", json=payload.get("event", {}))
            else:
                raise IntegrationError(f"unknown action '{action}'")
            r.raise_for_status()
            return r.json()


register_provider("google_calendar", lambda: GoogleCalendarProvider())
register_provider("microsoft_calendar", lambda: MicrosoftCalendarProvider())
# Pre-rename registration: Calendar used to mean Google. Kept so existing
# IntegrationConnection rows keep resolving; new connections use the real name.
register_provider("calendar", lambda: GoogleCalendarProvider())
