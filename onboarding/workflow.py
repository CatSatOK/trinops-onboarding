"""Onboarding workflow orchestration.

Runs the per-hire steps in order, logging each one's status to the database.
The workflow is fault-tolerant: a step that raises is recorded as FAILED with
its error message — it does not abort the run or roll back earlier steps. The
remaining steps still run, and any failed step can be retried individually.

Step sequence:
  1. welcome_email       — personalised welcome email
  2. calendar_events     — Day 1, team intro, probation review
  3. welcome_pack        — welcome pack PDF
  4. slack_notification  — team channel announcement
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from onboarding.calendar_events import build_onboarding_events, get_calendar_client
from onboarding.config import Settings
from onboarding.document_generator import generate_welcome_pack_pdf
from onboarding.email_sender import render_welcome_email, welcome_subject
from onboarding.logging_conf import get_logger
from onboarding.models import (
    Employee,
    OnboardingRun,
    OnboardingStep,
    RunStatus,
    StepStatus,
    utcnow,
)
from onboarding.notifier import Notifier, get_notifier
from onboarding.slack_notifier import SlackClient, get_slack_client, render_slack_message

logger = get_logger(__name__)

STEP_SEQUENCE: tuple[str, ...] = (
    "welcome_email",
    "calendar_events",
    "welcome_pack",
    "slack_notification",
)


class TransientStepError(RuntimeError):
    """Simulated transient failure used by demo fault injection."""


@dataclass
class Clients:
    """Side-effecting collaborators, grouped so they are easy to fake in tests."""

    notifier: Notifier
    calendar: object  # CalendarClient
    slack: SlackClient
    pack_generator: Callable[[Employee, Settings], str]


def build_clients(settings: Settings) -> Clients:
    return Clients(
        notifier=get_notifier(settings),
        calendar=get_calendar_client(settings),
        slack=get_slack_client(settings),
        pack_generator=generate_welcome_pack_pdf,
    )


# --- Step handlers -----------------------------------------------------------
# Each returns an artifact reference (path, event ids, message id) or None.

def _do_welcome_email(settings: Settings, employee: Employee, clients: Clients) -> str | None:
    html = render_welcome_email(employee, settings)
    subject = welcome_subject(employee, settings)
    return clients.notifier.send(to=employee.email, subject=subject, html_body=html)


def _do_calendar_events(settings: Settings, employee: Employee, clients: Clients) -> str | None:
    event_ids = [
        clients.calendar.create_event(ev.summary, ev.start, ev.end, ev.description)
        for ev in build_onboarding_events(employee, settings)
    ]
    return ",".join(event_ids)


def _do_welcome_pack(settings: Settings, employee: Employee, clients: Clients) -> str | None:
    return clients.pack_generator(employee, settings)


def _do_slack_notification(settings: Settings, employee: Employee, clients: Clients) -> str | None:
    message = render_slack_message(employee, settings)
    return clients.slack.post(settings.slack_channel, message)


_HANDLERS: dict[str, Callable[[Settings, Employee, Clients], str | None]] = {
    "welcome_email": _do_welcome_email,
    "calendar_events": _do_calendar_events,
    "welcome_pack": _do_welcome_pack,
    "slack_notification": _do_slack_notification,
}


def _dispatch(
    name: str, settings: Settings, employee: Employee, clients: Clients, attempt: int
) -> str | None:
    # Demo fault injection: fail on the first attempt only, succeed on retry.
    if settings.demo_mode and name in settings.demo_flaky_steps and attempt == 1:
        raise TransientStepError(
            f"simulated transient failure for {name!r} (demo: succeeds on retry)"
        )
    return _HANDLERS[name](settings, employee, clients)


def _execute_step(
    session: Session,
    settings: Settings,
    employee: Employee,
    step: OnboardingStep,
    clients: Clients,
) -> None:
    step.attempts += 1
    step.status = StepStatus.RUNNING
    step.error_message = None
    session.flush()
    try:
        artifact = _dispatch(step.step_name, settings, employee, clients, step.attempts)
        step.status = StepStatus.SUCCESS
        step.artifact_path = artifact
        step.error_message = None
        logger.info("step %s succeeded (attempt %d)", step.step_name, step.attempts)
    except Exception as exc:  # fault-tolerant: log, record, keep going
        step.status = StepStatus.FAILED
        step.error_message = f"{type(exc).__name__}: {exc}"
        logger.warning("step %s failed (attempt %d): %s", step.step_name, step.attempts, exc)
    step.completed_at = utcnow()
    session.flush()


def _finalise(run: OnboardingRun) -> None:
    statuses = [s.status for s in run.steps]
    if any(s in (StepStatus.PENDING, StepStatus.RUNNING) for s in statuses):
        run.overall_status = RunStatus.IN_PROGRESS
        run.completed_at = None
        return
    succeeded = sum(s == StepStatus.SUCCESS for s in statuses)
    if succeeded == len(statuses):
        run.overall_status = RunStatus.COMPLETED
    elif succeeded == 0:
        run.overall_status = RunStatus.FAILED
    else:
        run.overall_status = RunStatus.PARTIAL
    run.completed_at = utcnow()


def start_run(
    session: Session, settings: Settings, employee: Employee, clients: Clients
) -> OnboardingRun:
    """Create a run, execute every step in order, and finalise its status."""
    run = OnboardingRun(employee_id=employee.id, overall_status=RunStatus.IN_PROGRESS)
    run.steps = [OnboardingStep(step_name=name, status=StepStatus.PENDING) for name in STEP_SEQUENCE]
    session.add(run)
    session.flush()

    for step in run.steps:
        _execute_step(session, settings, employee, step, clients)

    _finalise(run)
    session.flush()
    logger.info("run %d for %s finished: %s", run.id, employee.name, run.overall_status)
    return run


def retry_step(
    session: Session, settings: Settings, run: OnboardingRun, step_name: str, clients: Clients
) -> OnboardingStep:
    """Re-run a single step of an existing run and re-finalise the run status."""
    step = next((s for s in run.steps if s.step_name == step_name), None)
    if step is None:
        raise KeyError(f"run {run.id} has no step {step_name!r}")
    _execute_step(session, settings, run.employee, step, clients)
    _finalise(run)
    session.flush()
    return step


def get_run(session: Session, run_id: int) -> OnboardingRun | None:
    return session.scalar(select(OnboardingRun).where(OnboardingRun.id == run_id))
