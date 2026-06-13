"""Demo seed: load new hires and run the onboarding workflow on first start.

Seed records use `start_in_days` offsets rather than fixed dates so the demo's
calendar events always sit in the near future regardless of when it is run.
With the default `DEMO_FLAKY_STEPS=["slack_notification"]`, each seeded run
ends PARTIAL with the Slack step failed — ready to demonstrate retry.
"""

import json
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from onboarding.config import Settings
from onboarding.logging_conf import get_logger
from onboarding.models import Employee, OnboardingRun
from onboarding.workflow import Clients, start_run

logger = get_logger(__name__)


def seed_and_run(session: Session, settings: Settings, clients: Clients) -> int:
    """Insert seed employees and trigger a run each, if none exist. Returns runs created."""
    if not settings.demo_mode:
        return 0
    if session.scalar(select(OnboardingRun).limit(1)) is not None:
        return 0

    path = settings.seed_employees_file
    try:
        records = json.loads(open(path, encoding="utf-8").read())
    except FileNotFoundError:
        logger.warning("seed file %s not found", path)
        return 0

    today = date.today()
    runs = 0
    for r in records:
        employee = Employee(
            name=r["name"],
            role=r["role"],
            email=r["email"],
            slack_handle=r.get("slack_handle"),
            manager_name=r.get("manager_name"),
            start_date=today + timedelta(days=r["start_in_days"]),
        )
        session.add(employee)
        session.flush()
        start_run(session, settings, employee, clients)
        runs += 1

    logger.info("seeded %d employee(s) and ran onboarding for each", runs)
    return runs
