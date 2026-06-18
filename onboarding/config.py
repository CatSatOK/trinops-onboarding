"""Application settings.

Every company-specific or environment-specific value lives in `.env`
(see `.env.example`). Nothing client-identifying is hardcoded.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    demo_mode: bool = True

    # Protects staff/admin endpoints when demo_mode is false (sent as X-API-Key).
    admin_api_key: str = ""

    database_url: str = "sqlite:///./data/onboarding.db"

    # --- Google APIs (only used when DEMO_MODE=false) ---
    google_credentials_file: str = "credentials.json"
    google_token_file: str = "token.json"
    google_calendar_id: str = "primary"

    # --- Slack (only used when DEMO_MODE=false) ---
    slack_bot_token: str = ""
    slack_channel: str = "#team-general"

    # --- Company details (appear on emails, the welcome pack and calendar invites) ---
    company_name: str = "Company A"
    company_email: str = "people@example.com"
    company_address: str = "1 Example Street, Example Town, EX1 2MP"
    handbook_url: str = "https://example.com/handbook"
    it_contact: str = "it-support@example.com"
    people_contact: str = "people@example.com"

    # --- First-week schedule (calendar events created per hire) ---
    day1_start_hour: int = 9       # Day 1 induction
    team_intro_hour: int = 11      # team intro meeting on the start date
    probation_review_hour: int = 10
    event_duration_minutes: int = 60
    probation_period_days: int = 90

    # --- Demo fault injection -------------------------------------------------
    # In demo mode these steps fail on their *first* attempt only, then succeed
    # on retry. This makes the failed -> retry -> success path visible in the
    # tracker without needing real outages. Set to [] for clean demo runs.
    demo_flaky_steps: list[str] = ["slack_notification"]

    # --- Paths ----------------------------------------------------------------
    pack_dir: str = "data/welcome_packs"   # generated welcome pack PDFs
    outbox_dir: str = "data/outbox"        # demo email output
    calendar_dir: str = "data/calendar"    # demo calendar event output
    seed_employees_file: str = "seed/employees.json"

    # Tracker -> API base (overridden to http://app:8000 inside docker-compose)
    api_base_url: str = "http://localhost:8000"

    def ensure_dirs(self) -> None:
        for d in (self.pack_dir, self.outbox_dir, self.calendar_dir):
            Path(d).mkdir(parents=True, exist_ok=True)
        db_path = self.database_url.removeprefix("sqlite:///")
        if db_path != self.database_url:  # only for sqlite URLs
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
