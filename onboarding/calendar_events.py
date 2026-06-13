"""Calendar event creation for a new hire.

Three events are created per hire from the start date:
  1. Day 1 induction
  2. Team intro meeting (same day)
  3. Probation review (start date + PROBATION_PERIOD_DAYS)

DemoCalendarClient (DEMO_MODE=true) writes each event as a text file into
`data/calendar/` so the demo is inspectable without a Google account.
GoogleCalendarClient (DEMO_MODE=false) creates real Google Calendar events.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Protocol

from onboarding.config import Settings
from onboarding.logging_conf import get_logger
from onboarding.models import Employee

logger = get_logger(__name__)


@dataclass
class OnboardingEvent:
    summary: str
    start: datetime
    end: datetime
    description: str


def build_onboarding_events(employee: Employee, settings: Settings) -> list[OnboardingEvent]:
    """Deterministic first-week schedule derived from the hire's start date."""
    duration = timedelta(minutes=settings.event_duration_minutes)
    start_date = employee.start_date
    review_date = start_date + timedelta(days=settings.probation_period_days)

    day1_start = datetime.combine(start_date, time(settings.day1_start_hour, 0))
    intro_start = datetime.combine(start_date, time(settings.team_intro_hour, 0))
    review_start = datetime.combine(review_date, time(settings.probation_review_hour, 0))

    manager = employee.manager_name or "their manager"
    return [
        OnboardingEvent(
            summary=f"Day 1 induction — {employee.name}",
            start=day1_start,
            end=day1_start + duration,
            description=(
                f"Welcome and induction for {employee.name} ({employee.role}) at "
                f"{settings.company_name}. Office tour, accounts setup, first-week plan."
            ),
        ),
        OnboardingEvent(
            summary=f"Team intro — {employee.name}",
            start=intro_start,
            end=intro_start + duration,
            description=(
                f"Introduce {employee.name} to the team. Hosted by {manager}."
            ),
        ),
        OnboardingEvent(
            summary=f"Probation review — {employee.name}",
            start=review_start,
            end=review_start + duration,
            description=(
                f"End-of-probation review for {employee.name} with {manager} "
                f"({settings.probation_period_days}-day probation)."
            ),
        ),
    ]


class CalendarClient(Protocol):
    def create_event(self, summary: str, start: datetime, end: datetime, description: str) -> str:
        ...


class DemoCalendarClient:
    """Writes each event as a text file so the demo is inspectable."""

    def __init__(self, settings: Settings) -> None:
        self._dir = Path(settings.calendar_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0

    def create_event(self, summary: str, start: datetime, end: datetime, description: str) -> str:
        self._counter += 1
        event_id = f"demo-evt-{datetime.now().strftime('%Y%m%dT%H%M%S%f')}-{self._counter}"
        body = (
            f"Event: {summary}\n"
            f"Start: {start.isoformat()}\n"
            f"End:   {end.isoformat()}\n"
            f"\n{description}\n"
        )
        (self._dir / f"{event_id}.txt").write_text(body, encoding="utf-8")
        logger.info("calendar(demo): created %s — %s", event_id, summary)
        return event_id


class GoogleCalendarClient:
    """Real Google Calendar client (DEMO_MODE=false)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._service = None

    def _client(self):
        if self._service is None:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(
                self._settings.google_token_file,
                scopes=["https://www.googleapis.com/auth/calendar"],
            )
            self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def create_event(self, summary: str, start: datetime, end: datetime, description: str) -> str:
        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
        }
        created = (
            self._client()
            .events()
            .insert(calendarId=self._settings.google_calendar_id, body=event)
            .execute()
        )
        logger.info("calendar: created event %s", created["id"])
        return created["id"]


def get_calendar_client(settings: Settings) -> CalendarClient:
    return DemoCalendarClient(settings) if settings.demo_mode else GoogleCalendarClient(settings)
