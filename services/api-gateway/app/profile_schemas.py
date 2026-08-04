"""Validated AI-profile documents (Phase 1).

Every profile category is a strict Pydantic model: ``extra='forbid'`` rejects
unknown fields, enums bound free choices, and validators reject invalid IANA
timezones, overlapping/inverted work windows, and oversized text. The router
persists only what validates here, so the database never holds an unbounded or
malformed profile blob. None of these models carry secrets, documents, or
conversation history — only declared preferences.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

try:  # Python 3.9+; the service targets 3.11.
    from zoneinfo import available_timezones
except ImportError:  # pragma: no cover - defensive
    available_timezones = None  # type: ignore[assignment]

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
_MAX_TEXT = 2000
_MAX_SHORT = 200


class _Strict(BaseModel):
    """Base for every nested document: the API speaks camelCase at every level,
    and unknown keys are a validation error (``extra='forbid'``)."""

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)


# --- enums (allowlists) ------------------------------------------------------

class UseCase(str, Enum):
    plan_day = "plan_day"
    manage_projects = "manage_projects"
    draft_communications = "draft_communications"
    research_knowledge = "research_knowledge"
    coordinate_agents = "coordinate_agents"


class Strictness(str, Enum):
    strict = "strict"
    flexible = "flexible"


class Tone(str, Enum):
    friendly = "friendly"
    neutral = "neutral"
    formal = "formal"
    direct = "direct"


class Detail(str, Enum):
    concise = "concise"
    balanced = "balanced"
    detailed = "detailed"


class Format(str, Enum):
    bullets = "bullets"
    prose = "prose"
    mixed = "mixed"


class Uncertainty(str, Enum):
    flag_and_proceed = "flag_and_proceed"
    ask_first = "ask_first"


class Prioritization(str, Enum):
    deadlines = "deadlines"
    impact = "impact"
    quick_wins = "quick_wins"
    manual = "manual"


class BoundaryKind(str, Enum):
    """Structured user constraints. These describe *preference*, never
    authorization — approval and tool policy stay a separate enforcement layer,
    so a boundary can never weaken a permission."""

    no_schedule_before = "no_schedule_before"
    no_schedule_after = "no_schedule_after"
    never_send_automatically = "never_send_automatically"
    keep_data_local = "keep_data_local"
    no_weekend_work = "no_weekend_work"
    custom = "custom"


# --- category documents ------------------------------------------------------

class WorkingWindow(_Strict):
    days: list[int] = Field(min_length=1, max_length=7)  # ISO weekday 1=Mon..7=Sun
    start: str
    end: str

    @field_validator("days")
    @classmethod
    def _days_valid(cls, v: list[int]) -> list[int]:
        if any(d < 1 or d > 7 for d in v):
            raise ValueError("days must be ISO weekday numbers 1..7")
        return sorted(set(v))

    @field_validator("start", "end")
    @classmethod
    def _time_valid(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("time must be HH:MM (24h)")
        return v

    @model_validator(mode="after")
    def _end_after_start(self) -> "WorkingWindow":
        if self.start >= self.end:
            raise ValueError("window end must be after start")
        return self


class QuietHours(_Strict):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _time_valid(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("time must be HH:MM (24h)")
        return v


class Schedule(_Strict):
    working_windows: list[WorkingWindow] = Field(default_factory=list, max_length=7)
    strictness: Strictness = Strictness.flexible
    quiet_hours: Optional[QuietHours] = None
    lunch: Optional[QuietHours] = None

    @model_validator(mode="after")
    def _no_overlap(self) -> "Schedule":
        # Windows sharing a day must not overlap in time.
        by_day: dict[int, list[tuple[str, str]]] = {}
        for w in self.working_windows:
            for d in w.days:
                by_day.setdefault(d, []).append((w.start, w.end))
        for spans in by_day.values():
            spans.sort()
            for prev, nxt in zip(spans, spans[1:]):
                if nxt[0] < prev[1]:
                    raise ValueError("overlapping working windows on the same day")
        return self


class Planning(_Strict):
    focus_minutes: int = Field(default=60, ge=15, le=480)
    meeting_buffer_minutes: int = Field(default=10, ge=0, le=120)
    planning_horizon_days: int = Field(default=7, ge=1, le=90)
    task_chunk_minutes: int = Field(default=45, ge=10, le=240)
    prioritization: Prioritization = Prioritization.impact


class Communication(_Strict):
    tone: Tone = Tone.neutral
    detail: Detail = Detail.balanced
    format: Format = Format.mixed
    languages: list[str] = Field(default_factory=list, max_length=8)
    drafting_greeting: str = Field(default="", max_length=_MAX_SHORT)
    drafting_signoff: str = Field(default="", max_length=_MAX_SHORT)
    uncertainty: Uncertainty = Uncertainty.flag_and_proceed

    @field_validator("languages")
    @classmethod
    def _locales(cls, v: list[str]) -> list[str]:
        for code in v:
            if not _LOCALE_RE.match(code):
                raise ValueError(f"invalid BCP 47 language tag: {code!r}")
        return v


class Accessibility(_Strict):
    reduced_cognitive_load: bool = False
    notes: str = Field(default="", max_length=_MAX_TEXT)


class Boundary(_Strict):
    kind: BoundaryKind
    value: str = Field(default="", max_length=_MAX_SHORT)


class Boundaries(_Strict):
    rules: list[Boundary] = Field(default_factory=list, max_length=25)
    notes: str = Field(default="", max_length=_MAX_TEXT)


_CONSENT_CATEGORIES = {
    "identity", "schedule", "planning", "communication",
    "accessibility", "goals", "boundaries",
}


def validate_timezone(tz: Optional[str]) -> Optional[str]:
    if tz is None or tz == "":
        return None
    if available_timezones is not None and tz not in available_timezones():
        raise ValueError(f"unknown IANA timezone: {tz!r}")
    return tz


class ProfileUpdate(_Strict):
    """Full replacement payload (PUT). Every field optional so a PATCH-style
    partial can reuse the same validators; the service merges by field."""

    timezone: Optional[str] = None
    locale: Optional[str] = None
    preferred_name: Optional[str] = Field(default=None, max_length=120)
    pronouns: Optional[str] = Field(default=None, max_length=40)
    use_cases: Optional[list[UseCase]] = Field(default=None, max_length=5)
    schedule: Optional[Schedule] = None
    planning: Optional[Planning] = None
    communication: Optional[Communication] = None
    accessibility: Optional[Accessibility] = None
    boundaries: Optional[Boundaries] = None
    category_consent: Optional[dict[str, bool]] = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: Optional[str]) -> Optional[str]:
        return validate_timezone(v)

    @field_validator("locale")
    @classmethod
    def _loc(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if not _LOCALE_RE.match(v):
            raise ValueError("invalid BCP 47 locale")
        return v

    @field_validator("use_cases")
    @classmethod
    def _dedupe_use_cases(cls, v: Optional[list[UseCase]]) -> Optional[list[UseCase]]:
        if v is None:
            return None
        seen: list[UseCase] = []
        for u in v:
            if u not in seen:
                seen.append(u)
        return seen

    @field_validator("category_consent")
    @classmethod
    def _consent(cls, v: Optional[dict[str, bool]]) -> Optional[dict[str, bool]]:
        if v is None:
            return None
        bad = set(v) - _CONSENT_CATEGORIES
        if bad:
            raise ValueError(f"unknown consent categories: {sorted(bad)}")
        return v


class GoalCreate(_Strict):
    title: str = Field(min_length=1, max_length=_MAX_SHORT)
    detail: str = Field(default="", max_length=_MAX_TEXT)
    priority: int = Field(default=1, ge=1, le=3)
    review_at: Optional[str] = None  # ISO date/datetime; stored as-is when parseable


class GoalUpdate(_Strict):
    title: Optional[str] = Field(default=None, min_length=1, max_length=_MAX_SHORT)
    detail: Optional[str] = Field(default=None, max_length=_MAX_TEXT)
    status: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=3)
    review_at: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("active", "upcoming", "archived"):
            raise ValueError("status must be active|upcoming|archived")
        return v


DEFAULT_CATEGORY_CONSENT = {c: True for c in sorted(_CONSENT_CATEGORIES)}
